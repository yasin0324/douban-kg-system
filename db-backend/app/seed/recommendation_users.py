"""
重建推荐训练型用户数据的公共逻辑。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import math
import os
from statistics import mean
from typing import Any, Dict, Sequence

import requests

from app.algorithms.common import split_multi_value
from app.config import settings
from app.services.auth_service import hash_password

REFERENCE_DATE = date(2026, 3, 8)
REFERENCE_TIME = datetime(2026, 3, 8, 12, 0, 0)
DEFAULT_PASSWORD = "seed-cfkg-pass"
DEFAULT_USER_COUNT = 200
DEFAULT_MOVIE_POOL_LIMIT = 30000
DEFAULT_REPORT_PATH = "tmp/cfkg/reseed_report.json"
KIMI_API_URL = "https://api.moonshot.cn/v1/chat/completions"
LLM_BATCH_SIZE = 4
LLM_MAX_RETRIES = 2


@dataclass(frozen=True)
class PersonaSpec:
    slug: str
    label: str
    strong_genres: tuple[str, ...]
    weak_genres: tuple[str, ...]
    avoid_genres: tuple[str, ...]
    preferred_regions: tuple[str, ...] = ()
    avoid_regions: tuple[str, ...] = ()
    preferred_year_min: int | None = None
    preferred_year_max: int | None = None
    rating_bias: float = 0.0
    behavior_density: str = "medium"
    description: str = ""


@dataclass(frozen=True)
class MovieCandidate:
    mid: str
    title: str
    genres: tuple[str, ...]
    regions: tuple[str, ...]
    languages: tuple[str, ...]
    year: int | None
    release_date: str | None
    douban_score: float
    douban_votes: int


@dataclass
class GeneratedRating:
    mid: str
    rating: float
    rationale_tag: str
    rated_at: str


@dataclass
class GeneratedUserData:
    username: str
    nickname: str
    persona: str
    persona_slug: str
    ratings: list[GeneratedRating]
    likes: list[str]
    wants: list[str]
    generation_mode: str
    validation_failures: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "nickname": self.nickname,
            "persona": self.persona,
            "persona_slug": self.persona_slug,
            "generation_mode": self.generation_mode,
            "validation_failures": list(self.validation_failures),
            "rating_count": len(self.ratings),
            "like_count": len(self.likes),
            "want_count": len(self.wants),
            "ratings": [
                {
                    "mid": item.mid,
                    "rating": item.rating,
                    "rationale_tag": item.rationale_tag,
                    "rated_at": item.rated_at,
                }
                for item in self.ratings
            ],
            "likes": list(self.likes),
            "wants": list(self.wants),
        }


DEFAULT_PERSONAS: tuple[PersonaSpec, ...] = (
    PersonaSpec(
        slug="drama_romance",
        label="剧情爱情派",
        strong_genres=("剧情", "爱情"),
        weak_genres=("音乐", "传记", "家庭"),
        avoid_genres=("恐怖", "惊悚", "战争"),
        preferred_regions=("中国大陆", "中国香港", "法国"),
        preferred_year_min=1990,
        preferred_year_max=2025,
        rating_bias=0.2,
        description="偏爱剧情、爱情和人物情感浓度高的电影，通常给情绪真挚的作品更高分。",
    ),
    PersonaSpec(
        slug="scifi_thriller",
        label="科幻悬疑派",
        strong_genres=("科幻", "悬疑"),
        weak_genres=("冒险", "动作", "剧情"),
        avoid_genres=("儿童", "家庭", "纪录片"),
        preferred_regions=("美国", "英国", "日本"),
        preferred_year_min=1995,
        preferred_year_max=2025,
        rating_bias=0.25,
        description="偏爱科幻设定、悬疑推理和脑洞型电影，对类型混搭作品接受度较高。",
    ),
    PersonaSpec(
        slug="action_crime",
        label="动作犯罪派",
        strong_genres=("动作", "犯罪"),
        weak_genres=("悬疑", "冒险", "战争"),
        avoid_genres=("爱情", "儿童", "歌舞"),
        preferred_regions=("美国", "中国香港", "韩国"),
        preferred_year_min=1985,
        preferred_year_max=2025,
        rating_bias=0.15,
        description="偏爱节奏快、冲突强的动作犯罪电影，对经典港片和现代商业片都较友好。",
    ),
    PersonaSpec(
        slug="animation_fantasy",
        label="动画奇幻派",
        strong_genres=("动画", "奇幻"),
        weak_genres=("冒险", "喜剧", "家庭"),
        avoid_genres=("纪录片", "历史", "战争"),
        preferred_regions=("日本", "美国"),
        preferred_year_min=1995,
        preferred_year_max=2025,
        rating_bias=0.3,
        description="偏爱动画、奇幻与冒险题材，对想象力和美术风格表现敏感。",
    ),
    PersonaSpec(
        slug="comedy_healing",
        label="喜剧治愈派",
        strong_genres=("喜剧", "家庭"),
        weak_genres=("爱情", "动画", "剧情"),
        avoid_genres=("恐怖", "惊悚", "战争"),
        preferred_regions=("中国大陆", "中国香港", "美国"),
        preferred_year_min=1990,
        preferred_year_max=2025,
        rating_bias=0.1,
        description="偏爱轻松、温暖、适合放松的电影，对压抑和惊悚题材普遍低分。",
    ),
    PersonaSpec(
        slug="documentary_history",
        label="纪录历史派",
        strong_genres=("纪录片", "历史"),
        weak_genres=("传记", "战争", "剧情"),
        avoid_genres=("儿童", "奇幻", "真人秀"),
        preferred_regions=("中国大陆", "英国", "法国"),
        preferred_year_min=1980,
        preferred_year_max=2025,
        rating_bias=0.15,
        description="偏爱纪录片、历史与传记，对真实质感和信息密度要求更高。",
    ),
    PersonaSpec(
        slug="arthouse_literary",
        label="作者文艺派",
        strong_genres=("剧情",),
        weak_genres=("爱情", "音乐", "传记"),
        avoid_genres=("恐怖", "动作", "儿童"),
        preferred_regions=("法国", "日本", "意大利", "中国大陆"),
        preferred_year_min=1970,
        preferred_year_max=2025,
        rating_bias=0.05,
        description="偏爱作者表达、节奏克制和人物内心戏，对工业套路片打分保守。",
    ),
    PersonaSpec(
        slug="family_warm",
        label="家庭温情派",
        strong_genres=("家庭", "剧情"),
        weak_genres=("动画", "喜剧", "爱情"),
        avoid_genres=("恐怖", "惊悚", "犯罪"),
        preferred_regions=("中国大陆", "美国", "日本"),
        preferred_year_min=1990,
        preferred_year_max=2025,
        rating_bias=0.12,
        description="偏爱家庭、成长和温情题材，重视情感共鸣和人物关系的可信度。",
    ),
)


def normalize_rating(value: Any) -> float:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        rating = 3.0
    rating = min(5.0, max(1.0, rating))
    return round(rating * 2) / 2


def coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_release_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def is_released_movie(row: dict[str, Any], reference_date: date = REFERENCE_DATE) -> bool:
    release_dt = parse_release_date(row.get("release_date"))
    year = coerce_int(row.get("year"))

    if release_dt:
        return release_dt <= reference_date
    if year is not None:
        return year < reference_date.year
    return False


def resolve_personas(persona_set: str | None = None) -> list[PersonaSpec]:
    if not persona_set or persona_set == "default":
        return list(DEFAULT_PERSONAS)

    selected = []
    seen = set()
    wanted = []
    for item in persona_set.split(","):
        slug = item.strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        wanted.append(slug)
    persona_map = {item.slug: item for item in DEFAULT_PERSONAS}
    for slug in wanted:
        if slug not in persona_map:
            raise ValueError(f"未知 persona: {slug}")
        selected.append(persona_map[slug])
    if not selected:
        raise ValueError("persona_set 不能为空")
    return selected


def persona_count_plan(user_count: int, personas: Sequence[PersonaSpec]) -> list[tuple[PersonaSpec, int, int]]:
    if user_count <= 0:
        raise ValueError("user_count 必须大于 0")
    if not personas:
        raise ValueError("至少需要一个 persona")

    base = user_count // len(personas)
    remainder = user_count % len(personas)
    planned = []
    offset = 0
    for index, persona in enumerate(personas):
        count = base + (1 if index < remainder else 0)
        planned.append((persona, offset, count))
        offset += count
    return planned


def movie_from_row(row: dict[str, Any]) -> MovieCandidate | None:
    if not is_released_movie(row):
        return None
    genres = tuple(sorted(split_multi_value(row.get("genres"))))
    if not genres:
        return None

    score = coerce_float(row.get("douban_score"))
    votes = coerce_int(row.get("douban_votes"))
    if score is None or votes is None:
        return None

    return MovieCandidate(
        mid=str(row["douban_id"]),
        title=str(row.get("name") or row["douban_id"]),
        genres=genres,
        regions=tuple(sorted(split_multi_value(row.get("regions")))),
        languages=tuple(sorted(split_multi_value(row.get("languages")))),
        year=coerce_int(row.get("year")),
        release_date=str(row.get("release_date"))[:10] if row.get("release_date") else None,
        douban_score=round(score, 2),
        douban_votes=votes,
    )


def load_high_quality_movie_pool(
    conn,
    limit: int = DEFAULT_MOVIE_POOL_LIMIT,
    reference_date: date = REFERENCE_DATE,
) -> list[MovieCandidate]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT douban_id, name, genres, regions, languages, year, release_date,
                   douban_score, douban_votes
            FROM movies
            WHERE type = 'movie'
              AND genres IS NOT NULL AND genres != ''
              AND douban_score IS NOT NULL
              AND douban_votes IS NOT NULL
              AND (
                    year < %s
                    OR (
                        year = %s
                        AND release_date IS NOT NULL
                        AND LEFT(release_date, 10) <= %s
                    )
                  )
            ORDER BY douban_votes DESC, douban_score DESC, douban_id ASC
            LIMIT %s
            """,
            (reference_date.year, reference_date.year, reference_date.isoformat(), limit),
        )
        rows = cursor.fetchall()

    movies = []
    for row in rows:
        movie = movie_from_row(row)
        if movie is not None:
            movies.append(movie)
    return movies


def movie_affinity(persona: PersonaSpec, movie: MovieCandidate) -> float:
    score = 0.0
    strong_hits = len(set(movie.genres) & set(persona.strong_genres))
    weak_hits = len(set(movie.genres) & set(persona.weak_genres))
    avoid_hits = len(set(movie.genres) & set(persona.avoid_genres))
    preferred_region_hit = bool(set(movie.regions) & set(persona.preferred_regions))
    avoid_region_hit = bool(set(movie.regions) & set(persona.avoid_regions))

    score += strong_hits * 2.8
    score += weak_hits * 1.4
    score -= avoid_hits * 2.5

    if preferred_region_hit:
        score += 0.8
    if avoid_region_hit:
        score -= 0.7

    if movie.year is not None and persona.preferred_year_min is not None and persona.preferred_year_max is not None:
        if persona.preferred_year_min <= movie.year <= persona.preferred_year_max:
            score += 0.55
        elif movie.year < persona.preferred_year_min - 15 or movie.year > persona.preferred_year_max + 5:
            score -= 0.3

    score += min(movie.douban_score, 9.7) * 0.18
    score += min(math.log10(max(movie.douban_votes, 10)), 6.0) * 0.42
    score += persona.rating_bias
    return round(score, 4)


def bucket_name_for_movie(persona: PersonaSpec, movie: MovieCandidate, affinity: float) -> str:
    strong_match = bool(set(movie.genres) & set(persona.strong_genres))
    weak_match = bool(set(movie.genres) & set(persona.weak_genres))
    avoid_match = bool(set(movie.genres) & set(persona.avoid_genres))
    if strong_match and affinity >= 4.0:
        return "strong"
    if avoid_match and not strong_match:
        return "avoid"
    if strong_match or weak_match or affinity >= 2.8:
        return "weak"
    if affinity >= 1.6:
        return "explore"
    if affinity <= 0.8:
        return "avoid"
    return "neutral"


def build_persona_movie_buckets(
    movies: Sequence[MovieCandidate],
    persona: PersonaSpec,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "strong": [],
        "weak": [],
        "explore": [],
        "neutral": [],
        "avoid": [],
    }
    ranked = []
    for movie in movies:
        affinity = movie_affinity(persona, movie)
        bucket = bucket_name_for_movie(persona, movie, affinity)
        item = {"movie": movie, "affinity": affinity, "bucket": bucket}
        buckets[bucket].append(item)
        ranked.append(item)

    def _sort_key(item: dict[str, Any]):
        movie = item["movie"]
        return (-item["affinity"], -movie.douban_votes, -movie.douban_score, movie.mid)

    for key in buckets:
        buckets[key].sort(key=_sort_key)

    ranked.sort(key=_sort_key)
    buckets["all_ranked"] = ranked
    return buckets


def make_username(prefix: str, persona: PersonaSpec, index: int) -> str:
    return f"{prefix}_{persona.slug}_{index + 1:03d}"


def make_nickname(persona: PersonaSpec, index: int) -> str:
    return f"{persona.label}{index + 1}"


def take_unique_movies(
    pool: Sequence[dict[str, Any]],
    count: int,
    used_ids: set[str],
    offset: int = 0,
    step: int = 1,
) -> list[dict[str, Any]]:
    selected = []
    total = len(pool)
    if total == 0 or count <= 0:
        return selected

    for index in range(total * 2):
        item = pool[(offset + index * max(step, 1)) % total]
        movie_id = item["movie"].mid
        if movie_id in used_ids:
            continue
        used_ids.add(movie_id)
        selected.append(item)
        if len(selected) >= count:
            break
    return selected


def deterministic_counts(persona: PersonaSpec, global_index: int) -> tuple[int, int, int]:
    base_ratings = 15 + (global_index % 16)
    density_bonus = 2 if persona.behavior_density == "dense" else 0
    rating_count = min(30, base_ratings + density_bonus)
    like_count = min(8, 4 + (global_index % 5))
    want_count = min(6, 3 + (global_index % 4))
    return rating_count, like_count, want_count


def rating_from_affinity(
    persona: PersonaSpec,
    movie: MovieCandidate,
    affinity: float,
    bucket: str,
    global_index: int,
    position: int,
) -> tuple[float, str]:
    jitter = (((global_index + 1) * 17 + (position + 3) * 11 + len(movie.mid)) % 5 - 2) * 0.15
    raw = 2.9 + affinity * 0.32 + jitter + persona.rating_bias

    if bucket == "strong":
        raw = max(raw, 4.0)
        tag = "strong_match"
    elif bucket == "weak":
        raw = max(3.5, raw)
        tag = "secondary_match"
    elif bucket == "explore":
        raw = min(4.0, max(3.0, raw - 0.3))
        tag = "exploration"
    elif bucket == "neutral":
        raw = min(3.5, max(2.5, raw - 0.55))
        tag = "neutral_reference"
    else:
        raw = min(3.0, max(1.0, raw - 1.4))
        tag = "avoidance_signal"

    if movie.douban_score >= 8.8 and bucket in {"strong", "weak"}:
        raw += 0.2
    if movie.douban_score <= 6.8 and bucket in {"neutral", "avoid"}:
        raw -= 0.1

    return normalize_rating(raw), tag


def assign_rated_at(global_index: int, position: int) -> str:
    start_time = REFERENCE_TIME - timedelta(days=520 - (global_index % 20) * 9)
    rated_at = start_time + timedelta(days=position * (6 + (global_index % 4)))
    return rated_at.isoformat(sep=" ", timespec="seconds")


def build_deterministic_user(
    persona: PersonaSpec,
    persona_pool: dict[str, list[dict[str, Any]]],
    global_index: int,
    persona_index: int,
    username_prefix: str,
) -> GeneratedUserData:
    rating_count, like_count, want_count = deterministic_counts(persona, global_index)
    used_ids: set[str] = set()

    strong_count = max(6, round(rating_count * 0.42))
    weak_count = max(4, round(rating_count * 0.22))
    explore_count = max(2, round(rating_count * 0.18))
    avoid_count = max(3, rating_count - strong_count - weak_count - explore_count)

    strong_items = take_unique_movies(persona_pool["strong"], strong_count, used_ids, offset=global_index * 3)
    weak_items = take_unique_movies(persona_pool["weak"], weak_count, used_ids, offset=global_index * 5)
    explore_items = take_unique_movies(persona_pool["explore"], explore_count, used_ids, offset=global_index * 7)
    avoid_items = take_unique_movies(persona_pool["avoid"], avoid_count, used_ids, offset=global_index * 11)

    if len(strong_items) < strong_count:
        strong_items += take_unique_movies(
            persona_pool["all_ranked"],
            strong_count - len(strong_items),
            used_ids,
            offset=global_index * 13,
        )
    if len(weak_items) < weak_count:
        weak_items += take_unique_movies(
            persona_pool["neutral"],
            weak_count - len(weak_items),
            used_ids,
            offset=global_index * 17,
        )
    if len(explore_items) < explore_count:
        explore_items += take_unique_movies(
            persona_pool["all_ranked"],
            explore_count - len(explore_items),
            used_ids,
            offset=global_index * 19,
        )
    if len(avoid_items) < avoid_count:
        avoid_items += take_unique_movies(
            persona_pool["neutral"],
            avoid_count - len(avoid_items),
            used_ids,
            offset=global_index * 23,
        )

    ordered_items = []
    while strong_items or weak_items or explore_items or avoid_items:
        if strong_items:
            ordered_items.append(strong_items.pop(0))
        if weak_items:
            ordered_items.append(weak_items.pop(0))
        if explore_items:
            ordered_items.append(explore_items.pop(0))
        if avoid_items:
            ordered_items.append(avoid_items.pop(0))

    ratings = []
    for position, item in enumerate(ordered_items[:rating_count]):
        movie = item["movie"]
        rating, tag = rating_from_affinity(persona, movie, item["affinity"], item["bucket"], global_index, position)
        ratings.append(
            GeneratedRating(
                mid=movie.mid,
                rating=rating,
                rationale_tag=tag,
                rated_at=assign_rated_at(global_index, position),
            )
        )

    positive_ratings = [item.mid for item in ratings if item.rating >= 4.0]
    strongest_positive = [item.mid for item in ratings if item.rating >= 4.5]
    likes = strongest_positive[:like_count]
    if len(likes) < like_count:
        likes.extend(mid for mid in positive_ratings if mid not in likes)
    likes = likes[:like_count]

    wants_used = set(item.mid for item in ratings) | set(likes)
    want_candidates = take_unique_movies(
        persona_pool["explore"] + persona_pool["weak"] + persona_pool["strong"],
        want_count * 2,
        wants_used,
        offset=global_index * 29,
    )
    wants = [item["movie"].mid for item in want_candidates[:want_count]]

    return GeneratedUserData(
        username=make_username(username_prefix, persona, persona_index),
        nickname=make_nickname(persona, persona_index),
        persona=persona.label,
        persona_slug=persona.slug,
        ratings=ratings,
        likes=likes,
        wants=wants,
        generation_mode="deterministic",
    )


def build_llm_candidate_pool(
    persona_pool: dict[str, list[dict[str, Any]]],
    global_offset: int,
) -> list[MovieCandidate]:
    used_ids: set[str] = set()
    selected = []
    for bucket_name, count, step in (
        ("strong", 22, 3),
        ("weak", 18, 5),
        ("explore", 12, 7),
        ("avoid", 8, 11),
    ):
        for item in take_unique_movies(
            persona_pool[bucket_name],
            count,
            used_ids,
            offset=global_offset * (step + 1),
            step=step,
        ):
            selected.append(item["movie"])
    return selected


def build_llm_prompt(persona: PersonaSpec, usernames: Sequence[str], candidates: Sequence[MovieCandidate]) -> str:
    movie_lines = []
    for movie in candidates:
        movie_lines.append(
            f"- ID:{movie.mid} | 名称:{movie.title} | 类型:{'/'.join(movie.genres)} | "
            f"地区:{'/'.join(movie.regions) or '未知'} | 年份:{movie.year or '未知'} | "
            f"豆瓣分:{movie.douban_score} | 票数:{movie.douban_votes}"
        )

    return f"""
你是一个严格遵守约束的电影用户行为生成器。

目标 persona：{persona.label}
人设说明：{persona.description}
强偏好类型：{", ".join(persona.strong_genres)}
弱偏好类型：{", ".join(persona.weak_genres)}
回避类型：{", ".join(persona.avoid_genres)}
偏好地区：{", ".join(persona.preferred_regions) or "不限"}

必须为以下用户名分别生成数据：
{json.dumps(list(usernames), ensure_ascii=False)}

候选电影只能从下面列表中选择：
{os.linesep.join(movie_lines)}

输出要求：
1. 每个用户评分 15-30 部电影。
2. likes 必须全部来自评分列表中 rating >= 4.0 的电影，数量 4-8。
3. wants 必须是未评分电影，且不能与 likes 重复，数量 3-6。
4. 评分必须体现明显偏好差异，不能全部高分，也不能全部集中在一个区间。
5. ratings 只允许使用 1.0 到 5.0 且步长为 0.5。
6. 只输出 JSON，不要解释。

JSON 格式固定如下：
{{
  "users": [
    {{
      "username": "seed_cfkg_xxx_001",
      "persona": "{persona.label}",
      "ratings": [
        {{"mid": "1292052", "rating": 4.5, "rationale_tag": "strong_match"}}
      ],
      "likes": ["1292052"],
      "wants": ["1291546"]
    }}
  ]
}}
"""


def parse_llm_users(payload: dict[str, Any]) -> list[dict[str, Any]]:
    users = payload.get("users")
    if not isinstance(users, list):
        raise ValueError("LLM payload 缺少 users 数组")
    return users


def normalize_llm_user(
    raw_user: dict[str, Any],
    persona: PersonaSpec,
    expected_username: str,
    global_index: int,
    persona_index: int,
) -> GeneratedUserData:
    raw_ratings = raw_user.get("ratings") or []
    ratings = []
    for position, item in enumerate(raw_ratings):
        if not isinstance(item, dict) or "mid" not in item:
            continue
        ratings.append(
            GeneratedRating(
                mid=str(item["mid"]),
                rating=normalize_rating(item.get("rating")),
                rationale_tag=str(item.get("rationale_tag") or "llm_generated"),
                rated_at=assign_rated_at(global_index, position),
            )
        )

    likes = [str(item) for item in (raw_user.get("likes") or [])]
    wants = [str(item) for item in (raw_user.get("wants") or [])]
    return GeneratedUserData(
        username=expected_username,
        nickname=make_nickname(persona, persona_index),
        persona=persona.label,
        persona_slug=persona.slug,
        ratings=ratings,
        likes=likes,
        wants=wants,
        generation_mode="llm",
    )


def validate_generated_user(
    user: GeneratedUserData,
    persona: PersonaSpec,
    allowed_movies: Dict[str, MovieCandidate],
) -> list[str]:
    failures = []
    rating_ids = [item.mid for item in user.ratings]
    if len(user.ratings) < 15 or len(user.ratings) > 30:
        failures.append("rating_count_out_of_range")
    if len(set(rating_ids)) != len(rating_ids):
        failures.append("duplicate_ratings")
    if any(mid not in allowed_movies for mid in rating_ids):
        failures.append("rating_outside_candidate_pool")

    likes = list(user.likes)
    wants = list(user.wants)
    if len(likes) < 4 or len(likes) > 8:
        failures.append("like_count_out_of_range")
    if len(wants) < 3 or len(wants) > 6:
        failures.append("want_count_out_of_range")
    if len(set(likes)) != len(likes):
        failures.append("duplicate_likes")
    if len(set(wants)) != len(wants):
        failures.append("duplicate_wants")
    if any(mid not in allowed_movies for mid in likes + wants):
        failures.append("preference_outside_candidate_pool")

    rating_map = {item.mid: item for item in user.ratings}
    if set(likes) & set(wants):
        failures.append("like_want_overlap")
    if set(wants) & set(rating_ids):
        failures.append("want_rating_overlap")
    invalid_likes = [mid for mid in likes if mid not in rating_map or rating_map[mid].rating < 4.0]
    if invalid_likes:
        failures.append("likes_not_backed_by_positive_ratings")

    unique_buckets = {item.rating for item in user.ratings}
    if len(unique_buckets) < 4:
        failures.append("ratings_too_concentrated")

    positive_count = sum(1 for item in user.ratings if item.rating >= 4.0)
    negative_count = sum(1 for item in user.ratings if item.rating <= 3.0)
    if positive_count < 4 or negative_count < 2:
        failures.append("positive_negative_imbalance")

    preferred_scores = []
    avoided_scores = []
    for item in user.ratings:
        movie = allowed_movies.get(item.mid)
        if movie is None:
            continue
        if set(movie.genres) & set(persona.strong_genres):
            preferred_scores.append(item.rating)
        if set(movie.genres) & set(persona.avoid_genres):
            avoided_scores.append(item.rating)

    if preferred_scores and avoided_scores:
        if mean(preferred_scores) <= mean(avoided_scores) + 0.6:
            failures.append("persona_preference_not_clear")
    elif not preferred_scores:
        failures.append("missing_preferred_genre_signal")

    rated_genres = Counter()
    for item in user.ratings:
        movie = allowed_movies.get(item.mid)
        if movie is None:
            continue
        rated_genres.update(movie.genres)
    if len(rated_genres) < 4:
        failures.append("movie_coverage_too_narrow")

    return failures


def run_kimi_generation(
    persona: PersonaSpec,
    usernames: Sequence[str],
    candidates: Sequence[MovieCandidate],
    llm_api_key: str,
    seed_offset: int,
    persona_start_index: int,
) -> list[GeneratedUserData] | None:
    if not llm_api_key:
        return None

    prompt = build_llm_prompt(persona, usernames, candidates)
    headers = {
        "Authorization": f"Bearer {llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": "你是一个只输出 JSON 的电影用户生成引擎。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(KIMI_API_URL, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = parse_llm_users(json.loads(content))

    username_map = {item.get("username"): item for item in parsed if isinstance(item, dict)}
    generated = []
    for local_index, username in enumerate(usernames):
        raw_user = username_map.get(username)
        if raw_user is None:
            raise ValueError(f"LLM 缺少用户 {username}")
        generated.append(
            normalize_llm_user(
                raw_user,
                persona=persona,
                expected_username=username,
                global_index=seed_offset + local_index,
                persona_index=persona_start_index + local_index,
            )
        )
    return generated


def llm_mode_enabled(llm_provider: str) -> bool:
    if llm_provider == "none":
        return False
    if llm_provider not in {"auto", "kimi"}:
        raise ValueError("llm_provider 仅支持 auto、kimi、none")
    return bool(settings.KIMI_API_KEY)


def generate_persona_users(
    persona: PersonaSpec,
    persona_pool: dict[str, list[dict[str, Any]]],
    start_index: int,
    count: int,
    username_prefix: str,
    llm_provider: str,
    seed: int,
) -> list[GeneratedUserData]:
    generated = []
    llm_enabled = llm_mode_enabled(llm_provider)

    for batch_start in range(0, count, LLM_BATCH_SIZE):
        batch_count = min(LLM_BATCH_SIZE, count - batch_start)
        batch_global_offset = start_index + batch_start
        usernames = [
            make_username(username_prefix, persona, batch_start + item_index)
            for item_index in range(batch_count)
        ]
        candidate_pool = build_llm_candidate_pool(persona_pool, batch_global_offset + seed)
        candidate_lookup = {movie.mid: movie for movie in candidate_pool}

        llm_users = None
        llm_errors: list[str] = []
        if llm_enabled:
            for _ in range(LLM_MAX_RETRIES):
                try:
                    llm_users = run_kimi_generation(
                        persona,
                        usernames=usernames,
                        candidates=candidate_pool,
                        llm_api_key=settings.KIMI_API_KEY,
                        seed_offset=batch_global_offset,
                        persona_start_index=batch_start,
                    )
                except Exception as exc:  # noqa: BLE001
                    llm_errors.append(str(exc))
                    llm_users = None
                    continue

                batch_valid = True
                for user in llm_users:
                    failures = validate_generated_user(user, persona, candidate_lookup)
                    if failures:
                        user.validation_failures.extend(failures)
                        batch_valid = False
                if batch_valid:
                    break
                llm_errors.append("validation_failed")
                llm_users = None

        if llm_users:
            generated.extend(llm_users)
            continue

        for local_index in range(batch_count):
            user = build_deterministic_user(
                persona=persona,
                persona_pool=persona_pool,
                global_index=batch_global_offset + local_index + seed,
                persona_index=batch_start + local_index,
                username_prefix=username_prefix,
            )
            user.validation_failures.extend(llm_errors)
            generated.append(user)

    return generated


def build_preference_rows(user: GeneratedUserData) -> list[dict[str, Any]]:
    rating_time_map = {
        item.mid: datetime.fromisoformat(item.rated_at.replace("T", " "))
        for item in user.ratings
    }
    rows = []
    latest_rating_time = max(rating_time_map.values()) if rating_time_map else REFERENCE_TIME - timedelta(days=90)

    for index, mid in enumerate(user.likes):
        created_at = rating_time_map[mid] + timedelta(days=1 + (index % 3))
        rows.append(
            {
                "mid": mid,
                "pref_type": "like",
                "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    for index, mid in enumerate(user.wants):
        created_at = latest_rating_time + timedelta(days=10 + index * 4)
        rows.append(
            {
                "mid": mid,
                "pref_type": "want_to_watch",
                "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return rows


def has_time_split_sequence(user: GeneratedUserData) -> bool:
    holdout_index = None
    for index, item in enumerate(user.ratings):
        if item.rating >= 4.0:
            holdout_index = index

    if holdout_index is None or holdout_index == 0:
        return False
    history = user.ratings[:holdout_index]
    return any(item.rating >= 4.0 for item in history)


def has_clear_positive_preference(
    user: GeneratedUserData,
    movie_lookup: Dict[str, MovieCandidate],
    persona: PersonaSpec,
) -> bool:
    preferred_scores = []
    avoided_scores = []
    for item in user.ratings:
        movie = movie_lookup.get(item.mid)
        if movie is None:
            continue
        if set(movie.genres) & set(persona.strong_genres):
            preferred_scores.append(item.rating)
        if set(movie.genres) & set(persona.avoid_genres):
            avoided_scores.append(item.rating)
    if not preferred_scores:
        return False
    if not avoided_scores:
        return mean(preferred_scores) >= 4.0
    return mean(preferred_scores) >= mean(avoided_scores) + 0.8


def build_quality_report(
    users: Sequence[GeneratedUserData],
    movie_lookup: Dict[str, MovieCandidate],
    persona_lookup: Dict[str, PersonaSpec],
    dry_run: bool,
    clear_existing: bool,
    is_mock: bool,
) -> dict[str, Any]:
    rating_counts = [len(user.ratings) for user in users]
    total_ratings = sum(rating_counts)
    total_likes = sum(len(user.likes) for user in users)
    total_wants = sum(len(user.wants) for user in users)
    positive_ratings = 0
    negative_ratings = 0
    rating_movie_ids = []
    genres = Counter()
    regions = Counter()
    generation_modes = Counter()
    validation_failures = Counter()

    users_with_clear_preference = 0
    users_with_complete_profile = 0
    users_with_time_split = 0

    for user in users:
        generation_modes.update([user.generation_mode])
        validation_failures.update(user.validation_failures)
        persona = persona_lookup[user.persona_slug]

        if user.likes and user.wants:
            users_with_complete_profile += 1
        if has_time_split_sequence(user):
            users_with_time_split += 1
        if has_clear_positive_preference(user, movie_lookup, persona):
            users_with_clear_preference += 1

        for item in user.ratings:
            rating_movie_ids.append(item.mid)
            if item.rating >= 4.0:
                positive_ratings += 1
            if item.rating <= 3.0:
                negative_ratings += 1

            movie = movie_lookup.get(item.mid)
            if movie is None:
                continue
            genres.update(movie.genres)
            regions.update(movie.regions)

    top_movie_share = 0.0
    if rating_movie_ids:
        movie_counter = Counter(rating_movie_ids)
        top_movie_share = round(movie_counter.most_common(1)[0][1] / len(rating_movie_ids), 4)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": dry_run,
        "clear_existing": clear_existing,
        "is_mock": is_mock,
        "user_count": len(users),
        "rating_count": total_ratings,
        "like_count": total_likes,
        "want_count": total_wants,
        "persona_distribution": dict(Counter(user.persona_slug for user in users)),
        "generation_modes": dict(generation_modes),
        "validation_failures": dict(validation_failures),
        "rating_count_stats": {
            "min": min(rating_counts) if rating_counts else 0,
            "max": max(rating_counts) if rating_counts else 0,
            "avg": round(mean(rating_counts), 2) if rating_counts else 0.0,
        },
        "positive_ratio": round(positive_ratings / total_ratings, 4) if total_ratings else 0.0,
        "negative_ratio": round(negative_ratings / total_ratings, 4) if total_ratings else 0.0,
        "genre_coverage": len(genres),
        "region_coverage": len(regions),
        "movie_coverage": len(set(rating_movie_ids)),
        "top_movie_share": top_movie_share,
        "profile_usability": {
            "clear_positive_preference_users": users_with_clear_preference,
            "complete_like_want_users": users_with_complete_profile,
            "time_split_ready_users": users_with_time_split,
            "clear_positive_preference_ratio": round(users_with_clear_preference / len(users), 4) if users else 0.0,
            "complete_like_want_ratio": round(users_with_complete_profile / len(users), 4) if users else 0.0,
            "time_split_ready_ratio": round(users_with_time_split / len(users), 4) if users else 0.0,
        },
        "users": [user.to_report_dict() for user in users],
    }


def write_report(report: dict[str, Any], report_path: str | None) -> None:
    if not report_path:
        return
    directory = os.path.dirname(report_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)


def fetch_all_ordinary_user_ids(conn) -> list[int]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users ORDER BY id ASC")
        return [int(row["id"]) for row in cursor.fetchall()]


def clear_ordinary_users(conn, driver) -> dict[str, Any]:
    user_ids = fetch_all_ordinary_user_ids(conn)
    if not user_ids:
        return {"deleted_user_count": 0, "deleted_user_ids": []}

    placeholders = ", ".join(["%s"] * len(user_ids))
    with conn.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM admin_user_actions WHERE target_user_id IN ({placeholders})",
            user_ids,
        )
        cursor.execute(f"DELETE FROM users WHERE id IN ({placeholders})", user_ids)
    conn.commit()

    with driver.session() as session:
        session.run(
            """
            UNWIND $user_ids AS uid
            MATCH (u:User {id: uid})
            DETACH DELETE u
            """,
            user_ids=user_ids,
        ).consume()

    return {"deleted_user_count": len(user_ids), "deleted_user_ids": user_ids}


def upsert_seed_user(conn, username: str, nickname: str, is_mock: bool) -> int:
    password_hash = hash_password(DEFAULT_PASSWORD)
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing = cursor.fetchone()
        if existing:
            user_id = int(existing["id"])
            cursor.execute(
                "UPDATE users SET nickname = %s, status = 'active', is_mock = %s WHERE id = %s",
                (nickname, int(is_mock), user_id),
            )
            cursor.execute("DELETE FROM user_movie_prefs WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM user_movie_ratings WHERE user_id = %s", (user_id,))
        else:
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, nickname, status, is_mock)
                VALUES (%s, %s, %s, 'active', %s)
                """,
                (username, password_hash, nickname, int(is_mock)),
            )
            user_id = int(cursor.lastrowid)
    conn.commit()
    return user_id


def reset_neo4j_user(driver, user_id: int, username: str, nickname: str, is_mock: bool) -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (u:User {id: $uid})
            SET u.username = $username,
                u.nickname = $nickname,
                u.is_mock = $is_mock
            """,
            uid=user_id,
            username=username,
            nickname=nickname,
            is_mock=bool(is_mock),
        ).consume()
        session.run(
            """
            MATCH (u:User {id: $uid})-[rel:RATED]->()
            DELETE rel
            """,
            uid=user_id,
        ).consume()


def persist_generated_users(
    conn,
    driver,
    users: Sequence[GeneratedUserData],
    is_mock: bool,
) -> dict[str, int]:
    inserted_users = 0
    inserted_ratings = 0
    inserted_prefs = 0

    for user in users:
        user_id = upsert_seed_user(conn, user.username, user.nickname, is_mock=is_mock)
        inserted_users += 1
        reset_neo4j_user(driver, user_id, user.username, user.nickname, is_mock=is_mock)

        with driver.session() as session:
            for rating in user.ratings:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO user_movie_ratings (
                            user_id, mid, rating, comment_short, rated_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            rating = VALUES(rating),
                            comment_short = VALUES(comment_short),
                            rated_at = VALUES(rated_at),
                            updated_at = VALUES(updated_at)
                        """,
                        (
                            user_id,
                            rating.mid,
                            rating.rating,
                            f"seed:{user.persona_slug}:{rating.rationale_tag}",
                            rating.rated_at,
                            rating.rated_at,
                        ),
                    )
                session.run(
                    """
                    MATCH (u:User {id: $uid}), (m:Movie {mid: $mid})
                    MERGE (u)-[rel:RATED]->(m)
                    SET rel.rating = $rating,
                        rel.timestamp = datetime($timestamp)
                    """,
                    uid=user_id,
                    mid=rating.mid,
                    rating=rating.rating,
                    timestamp=rating.rated_at.replace(" ", "T"),
                ).consume()
                inserted_ratings += 1

            for pref in build_preference_rows(user):
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO user_movie_prefs (user_id, mid, pref_type, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            pref_type = VALUES(pref_type),
                            created_at = VALUES(created_at),
                            updated_at = VALUES(updated_at)
                        """,
                        (
                            user_id,
                            pref["mid"],
                            pref["pref_type"],
                            pref["created_at"],
                            pref["created_at"],
                        ),
                    )
                inserted_prefs += 1
        conn.commit()

    return {
        "inserted_users": inserted_users,
        "inserted_ratings": inserted_ratings,
        "inserted_preferences": inserted_prefs,
    }


def generate_recommendation_seed_users(
    movies: Sequence[MovieCandidate],
    user_count: int = DEFAULT_USER_COUNT,
    persona_set: str | None = None,
    username_prefix: str = "seed_cfkg",
    llm_provider: str = "auto",
    seed: int = 20260308,
) -> tuple[list[GeneratedUserData], dict[str, MovieCandidate], dict[str, PersonaSpec]]:
    personas = resolve_personas(persona_set)
    persona_lookup = {persona.slug: persona for persona in personas}
    movie_lookup = {movie.mid: movie for movie in movies}

    users: list[GeneratedUserData] = []
    for persona, offset, count in persona_count_plan(user_count, personas):
        persona_pool = build_persona_movie_buckets(movies, persona)
        users.extend(
            generate_persona_users(
                persona=persona,
                persona_pool=persona_pool,
                start_index=offset,
                count=count,
                username_prefix=username_prefix,
                llm_provider=llm_provider,
                seed=seed,
            )
        )
    for user in users:
        failures = validate_generated_user(user, persona_lookup[user.persona_slug], movie_lookup)
        for failure in failures:
            if failure not in user.validation_failures:
                user.validation_failures.append(failure)
    return users, movie_lookup, persona_lookup


def reseed_recommendation_users(
    conn,
    driver,
    *,
    dry_run: bool,
    user_count: int,
    persona_set: str | None,
    llm_provider: str,
    report_path: str | None,
    clear_existing: bool,
    is_mock: bool,
    username_prefix: str,
    seed: int,
) -> dict[str, Any]:
    movies = load_high_quality_movie_pool(conn)
    if not movies:
        raise RuntimeError("电影候选池为空，请先确保 movies 表中存在已上映影片数据")

    users, movie_lookup, persona_lookup = generate_recommendation_seed_users(
        movies=movies,
        user_count=user_count,
        persona_set=persona_set,
        username_prefix=username_prefix,
        llm_provider=llm_provider,
        seed=seed,
    )

    delete_summary = {"deleted_user_count": 0, "deleted_user_ids": []}
    write_summary = {"inserted_users": 0, "inserted_ratings": 0, "inserted_preferences": 0}
    if not dry_run:
        if clear_existing:
            delete_summary = clear_ordinary_users(conn, driver)
        write_summary = persist_generated_users(conn, driver, users, is_mock=is_mock)

    report = build_quality_report(
        users=users,
        movie_lookup=movie_lookup,
        persona_lookup=persona_lookup,
        dry_run=dry_run,
        clear_existing=clear_existing,
        is_mock=is_mock,
    )
    report["movie_pool_size"] = len(movies)
    report["delete_summary"] = delete_summary
    report["write_summary"] = write_summary

    write_report(report, report_path or DEFAULT_REPORT_PATH)
    return report
