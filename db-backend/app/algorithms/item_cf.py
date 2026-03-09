"""
传统 ItemCF 基线推荐。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from math import sqrt
from threading import RLock
from typing import Any, Dict, List

from cachetools import TTLCache

from app.algorithms.common import dedupe_preserve_order

POSITIVE_RATING_THRESHOLD = 3.5
SIMILARITY_SHRINKAGE = 2.0
DEFAULT_TIMEOUT_MS = 1200
SIMILARITY_CACHE_LIMIT = 120
SIMILARITY_CACHE_TTL_SECONDS = 900
SIMILARITY_CACHE_MAXSIZE = 2048
EXPLAIN_SUPPORT_LIMIT = 3

_CACHE_LOCK = RLock()
_SIMILARITY_CACHE: TTLCache[str, list[dict[str, Any]]] = TTLCache(
    maxsize=SIMILARITY_CACHE_MAXSIZE,
    ttl=SIMILARITY_CACHE_TTL_SECONDS,
)

SIMILARITY_QUERY = """
WITH positive_interactions AS (
    SELECT DISTINCT user_id, mid
    FROM (
        SELECT user_id, mid
        FROM user_movie_ratings
        WHERE rating >= %s
        UNION ALL
        SELECT user_id, mid
        FROM user_movie_prefs
        WHERE pref_type IN ('like', 'want_to_watch')
    ) AS positive_rows
),
source_users AS (
    SELECT DISTINCT user_id
    FROM positive_interactions
    WHERE mid = %s
),
source_stats AS (
    SELECT COUNT(*) AS source_user_count
    FROM source_users
),
candidate_overlap AS (
    SELECT target.mid AS movie_id,
           COUNT(DISTINCT target.user_id) AS overlap_count
    FROM positive_interactions AS target
    JOIN source_users AS source_user
      ON source_user.user_id = target.user_id
    WHERE target.mid <> %s
    GROUP BY target.mid
),
target_popularity AS (
    SELECT mid AS movie_id,
           COUNT(DISTINCT user_id) AS target_user_count
    FROM positive_interactions
    GROUP BY mid
)
SELECT candidate_overlap.movie_id,
       candidate_overlap.overlap_count,
       source_stats.source_user_count,
       target_popularity.target_user_count,
       (
           (
               candidate_overlap.overlap_count
               / SQRT(source_stats.source_user_count * target_popularity.target_user_count)
           ) * (
               candidate_overlap.overlap_count
               / (candidate_overlap.overlap_count + %s)
           )
       ) AS similarity
FROM candidate_overlap
JOIN target_popularity
  ON target_popularity.movie_id = candidate_overlap.movie_id
CROSS JOIN source_stats
WHERE source_stats.source_user_count > 0
  AND candidate_overlap.overlap_count >= %s
ORDER BY similarity DESC,
         candidate_overlap.overlap_count DESC,
         candidate_overlap.movie_id ASC
LIMIT %s
"""


def _clone_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def _resolve_positive_context(
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
) -> tuple[List[str], Dict[str, float]]:
    if not user_profile:
        movie_ids = dedupe_preserve_order(seed_movie_ids)
        return movie_ids[:24], {movie_id: 1.0 for movie_id in movie_ids[:24]}

    movie_feedback = user_profile.get("movie_feedback", {})
    positive_movie_ids = dedupe_preserve_order(
        user_profile.get("context_movie_ids")
        or user_profile.get("positive_movie_ids")
        or [],
    )[:24]
    positive_weights = {
        movie_id: float(movie_feedback.get(movie_id, {}).get("positive_weight") or 1.0)
        for movie_id in positive_movie_ids
    }
    return positive_movie_ids, positive_weights


def _fetch_movie_title_map(conn, movie_ids: List[str]) -> Dict[str, str]:
    movie_ids = dedupe_preserve_order(movie_ids)
    if not movie_ids:
        return {}

    placeholders = ",".join(["%s"] * len(movie_ids))
    query = f"""
        SELECT douban_id AS movie_id,
               name AS title
        FROM movies
        WHERE douban_id IN ({placeholders})
    """
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(movie_ids))
        rows = cursor.fetchall()
    return {
        str(row["movie_id"]): row.get("title") or str(row["movie_id"])
        for row in rows
    }


def _fetch_similar_movies_from_mysql(
    conn,
    source_movie_id: str,
    limit: int = SIMILARITY_CACHE_LIMIT,
    min_overlap: int = 1,
) -> List[Dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            SIMILARITY_QUERY,
            (
                POSITIVE_RATING_THRESHOLD,
                source_movie_id,
                source_movie_id,
                SIMILARITY_SHRINKAGE,
                min_overlap,
                limit,
            ),
        )
        rows = cursor.fetchall()

    normalized = []
    for row in rows:
        source_user_count = int(row.get("source_user_count") or 0)
        target_user_count = int(row.get("target_user_count") or 0)
        similarity = float(row.get("similarity") or 0.0)
        if source_user_count <= 0 or target_user_count <= 0 or similarity <= 0:
            continue
        normalized.append({
            "movie_id": str(row["movie_id"]),
            "overlap_count": int(row.get("overlap_count") or 0),
            "source_user_count": source_user_count,
            "target_user_count": target_user_count,
            "similarity": similarity,
        })
    return normalized


def _get_similar_movies(
    conn,
    source_movie_id: str,
    limit: int = SIMILARITY_CACHE_LIMIT,
) -> List[Dict[str, Any]]:
    cache_key = str(source_movie_id)
    with _CACHE_LOCK:
        cached = _SIMILARITY_CACHE.get(cache_key)
        if cached is not None and len(cached) >= limit:
            return _clone_rows(cached[:limit])

    rows = _fetch_similar_movies_from_mysql(
        conn=conn,
        source_movie_id=source_movie_id,
        limit=max(limit, SIMILARITY_CACHE_LIMIT),
    )
    with _CACHE_LOCK:
        _SIMILARITY_CACHE[cache_key] = _clone_rows(rows)
    return _clone_rows(rows[:limit])


def _format_itemcf_reason(
    support_movies: List[Dict[str, Any]],
) -> List[str]:
    if not support_movies:
        return ["与你历史正向反馈电影的用户群存在明显重合"]

    titles = [item.get("title") for item in support_movies if item.get("title")]
    overlap_count = max(int(item.get("overlap_count") or 0) for item in support_movies)
    if titles:
        return [
            f"与《{'》《'.join(titles[:2])}》的正向用户群高度重合",
            f"共同正向反馈用户最多 {overlap_count} 人",
        ]
    return [f"与你历史正向反馈电影存在协同相似信号，共同正向反馈用户最多 {overlap_count} 人"]


def _score_candidate_pool(
    conn,
    positive_movie_ids: List[str],
    positive_weights: Dict[str, float],
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if not positive_movie_ids:
        return []

    seen_set = set(dedupe_preserve_order(seen_movie_ids))
    candidate_scores: Dict[str, float] = defaultdict(float)
    support_rows: Dict[str, list[dict[str, Any]]] = defaultdict(list)
    popularity_map: Dict[str, int] = defaultdict(int)

    for movie_id in positive_movie_ids:
        seed_weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if seed_weight <= 0:
            continue
        for neighbor in _get_similar_movies(conn, movie_id):
            candidate_id = neighbor["movie_id"]
            if candidate_id in seen_set:
                continue
            contribution = seed_weight * float(neighbor["similarity"])
            if contribution <= 0:
                continue
            candidate_scores[candidate_id] += contribution
            popularity_map[candidate_id] = max(
                popularity_map[candidate_id],
                int(neighbor.get("target_user_count") or 0),
            )
            support_rows[candidate_id].append({
                "movie_id": movie_id,
                "similarity": float(neighbor["similarity"]),
                "overlap_count": int(neighbor.get("overlap_count") or 0),
                "contribution": contribution,
            })

    if not candidate_scores:
        return []

    source_title_map = _fetch_movie_title_map(conn, positive_movie_ids)
    total_positive_weight = max(sum(positive_weights.values()), 1e-8)
    ranked_items = []
    for candidate_id, raw_score in candidate_scores.items():
        sorted_support = sorted(
            support_rows[candidate_id],
            key=lambda item: (
                -float(item["contribution"]),
                -float(item["similarity"]),
                item["movie_id"],
            ),
        )
        support_details = []
        for support in sorted_support[:EXPLAIN_SUPPORT_LIMIT]:
            support_details.append({
                **support,
                "title": source_title_map.get(support["movie_id"], support["movie_id"]),
            })
        normalized_score = raw_score / total_positive_weight
        popularity_bonus = min(0.08, sqrt(max(popularity_map[candidate_id], 0)) * 0.004)
        ranked_items.append({
            "movie_id": candidate_id,
            "score": normalized_score + popularity_bonus,
            "reasons": _format_itemcf_reason(support_details),
            "negative_signals": [],
            "support_movies": support_details,
            "source": "itemcf",
        })

    ranked_items.sort(key=lambda item: (-float(item["score"]), item["movie_id"]))
    return ranked_items[:limit]


def _get_itemcf_recommendations_sync(
    conn,
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    del user_id, timeout_ms
    positive_movie_ids, positive_weights = _resolve_positive_context(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
    )
    if not positive_movie_ids:
        return []
    candidate_limit = min(max(limit * 6, 120), 220)
    return _score_candidate_pool(
        conn=conn,
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
        seen_movie_ids=seen_movie_ids,
        limit=candidate_limit,
    )[:limit]


def build_itemcf_explain_signals(
    conn,
    user_profile: Dict[str, Any] | None,
    target_mid: str,
    seed_movie_ids: List[str] | None = None,
) -> Dict[str, Any]:
    positive_movie_ids, positive_weights = _resolve_positive_context(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
    )
    support_details = []
    for movie_id in positive_movie_ids:
        seed_weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if seed_weight <= 0:
            continue
        neighbors = _get_similar_movies(conn, movie_id)
        match = next(
            (item for item in neighbors if item["movie_id"] == str(target_mid)),
            None,
        )
        if not match:
            continue
        support_details.append({
            "movie_id": movie_id,
            "similarity": float(match["similarity"]),
            "overlap_count": int(match.get("overlap_count") or 0),
            "contribution": seed_weight * float(match["similarity"]),
        })

    if not support_details:
        return {
            "support_movies": [],
            "signal_items": [],
        }

    title_map = _fetch_movie_title_map(conn, [item["movie_id"] for item in support_details])
    sorted_support = sorted(
        support_details,
        key=lambda item: (-float(item["contribution"]), -float(item["similarity"]), item["movie_id"]),
    )[:EXPLAIN_SUPPORT_LIMIT]
    signal_items = [
        f"共同正向反馈用户 {int(item['overlap_count'])} 人"
        for item in sorted_support
    ]
    for item in sorted_support:
        item["title"] = title_map.get(item["movie_id"], item["movie_id"])
    return {
        "support_movies": sorted_support,
        "signal_items": dedupe_preserve_order(signal_items),
    }


async def get_itemcf_recommendations(
    conn,
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(
        _get_itemcf_recommendations_sync,
        conn,
        user_id,
        user_profile,
        seed_movie_ids,
        seen_movie_ids,
        limit,
        timeout_ms,
    )
