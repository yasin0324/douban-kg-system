"""
用户行为服务 — 偏好（喜欢/想看）+ 评分 CRUD
"""
from typing import Any, Dict, List, Optional
import logging
from app.db.neo4j import Neo4jConnection
from app.recommendation_cache import invalidate_user_profile_cache

logger = logging.getLogger(__name__)

STRONG_POSITIVE_RATING_THRESHOLD = 4.0
WEAK_POSITIVE_RATING_THRESHOLD = 3.5
WEAK_NEGATIVE_RATING_THRESHOLD = 3.0
STRONG_POSITIVE_RATING_BASE = 2.6
STRONG_POSITIVE_RATING_STEP = 1.2
WEAK_POSITIVE_RATING_WEIGHT = 1.15
LIKE_WEIGHT = 1.9
WANT_WEIGHT = 0.8
WANT_EXPLORATION_WEIGHT = 0.35
WEAK_NEGATIVE_BASE = 0.45
WEAK_NEGATIVE_STEP = 0.28
POSITIVE_CONTEXT_THRESHOLD = 0.15


# ---------- 偏好 ----------

def add_preference(conn, user_id: int, mid: str, pref_type: str) -> dict:
    with conn.cursor() as cursor:
        # UPSERT
        cursor.execute(
            "INSERT INTO user_movie_prefs (user_id, mid, pref_type) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE pref_type = VALUES(pref_type), updated_at = NOW()",
            (user_id, mid, pref_type),
        )
        conn.commit()
        invalidate_user_profile_cache(user_id)
        cursor.execute(
            "SELECT id, mid, pref_type, created_at FROM user_movie_prefs WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        return cursor.fetchone()


def remove_preference(conn, user_id: int, mid: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM user_movie_prefs WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        conn.commit()
        if cursor.rowcount > 0:
            invalidate_user_profile_cache(user_id)
        return cursor.rowcount > 0


def list_preferences(conn, user_id: int, pref_type: Optional[str] = None, page: int = 1, size: int = 20) -> dict:
    offset = (page - 1) * size
    with conn.cursor() as cursor:
        where = "WHERE user_id = %s"
        params: list = [user_id]
        if pref_type:
            where += " AND pref_type = %s"
            params.append(pref_type)

        cursor.execute(f"SELECT COUNT(*) as total FROM user_movie_prefs {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"SELECT id, mid, pref_type, created_at FROM user_movie_prefs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params + [size, offset],
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "page": page, "size": size}


def check_preference(conn, user_id: int, mid: str) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT pref_type FROM user_movie_prefs WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        row = cursor.fetchone()
    return {
        "mid": mid,
        "is_liked": row is not None and row["pref_type"] == "like",
        "is_want_to_watch": row is not None and row["pref_type"] == "want_to_watch",
    }


# ---------- 评分 ----------

def check_movie_released(conn, mid: str):
    with conn.cursor() as cursor:
        cursor.execute("SELECT name, year, release_date FROM movies WHERE douban_id = %s", (mid,))
        movie = cursor.fetchone()
        
    if not movie:
        raise ValueError("电影不存在")
        
    year = movie.get('year')
    release_date_str = movie.get('release_date')
    if release_date_str:
        release_date_str = release_date_str[:10]
        
    current_date = "2026-03-20" # based on user requirement
    
    is_unreleased = False
    if year and year > 2026:
        is_unreleased = True
    elif year == 2026:
        if not release_date_str:
            # 2026年但未定档，视为未上映
            is_unreleased = True
        elif release_date_str > current_date:
            is_unreleased = True
            
    if is_unreleased:
        raise ValueError("按理来说未上映的电影或剧集不能进行评分")

def add_rating(conn, user_id: int, mid: str, rating: float, comment_short: str = None) -> dict:
    check_movie_released(conn, mid)
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO user_movie_ratings (user_id, mid, rating, comment_short) VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE rating = VALUES(rating), comment_short = VALUES(comment_short), updated_at = NOW()",
            (user_id, mid, rating, comment_short),
        )
        conn.commit()
        invalidate_user_profile_cache(user_id)
        
        # === Dual Write to Neo4j ===
        try:
            driver = Neo4jConnection.get_driver()
            with driver.session() as session:
                # 必须确保 user 节点存在
                session.run(
                    "MERGE (u:User {id: $uid}) "
                    "WITH u MATCH (m:Movie {mid: $mid}) "
                    "MERGE (u)-[rel:RATED]->(m) "
                    "SET rel.rating = $rating, rel.timestamp = datetime()",
                    uid=user_id, mid=mid, rating=rating
                )
        except Exception as e:
            logger.error("双写 Neo4j 评分失败: %s", e)

        cursor.execute(
            "SELECT id, mid, rating, comment_short, rated_at FROM user_movie_ratings WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        return cursor.fetchone()


def remove_rating(conn, user_id: int, mid: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM user_movie_ratings WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        conn.commit()
        deleted = cursor.rowcount > 0

    if deleted:
        invalidate_user_profile_cache(user_id)
        # 删除评分时同步清理 Neo4j 关系，避免推荐系统持续把该电影当作“已看过”
        try:
            driver = Neo4jConnection.get_driver()
            with driver.session() as session:
                session.run(
                    "MATCH (u:User {id: $uid})-[rel:RATED]->(m:Movie {mid: $mid}) DELETE rel",
                    uid=user_id, mid=mid
                )
        except Exception as e:
            logger.error("双写 Neo4j 删除评分失败: %s", e)

    return deleted


def list_ratings(conn, user_id: int, page: int = 1, size: int = 20) -> dict:
    offset = (page - 1) * size
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total FROM user_movie_ratings WHERE user_id = %s", (user_id,))
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT id, mid, rating, comment_short, rated_at FROM user_movie_ratings "
            "WHERE user_id = %s ORDER BY rated_at DESC LIMIT %s OFFSET %s",
            (user_id, size, offset),
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "page": page, "size": size}


def get_rating(conn, user_id: int, mid: str) -> Optional[dict]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, mid, rating, comment_short, rated_at FROM user_movie_ratings WHERE user_id = %s AND mid = %s",
            (user_id, mid),
        )
        return cursor.fetchone()


def _get_or_create_behavior(movie_behaviors: Dict[str, Dict[str, Any]], mid: str) -> Dict[str, Any]:
    if mid not in movie_behaviors:
        movie_behaviors[mid] = {
            "mid": mid,
            "rating": None,
            "is_liked": False,
            "is_want_to_watch": False,
            "positive_weight": 0.0,
            "negative_weight": 0.0,
            "exploration_weight": 0.0,
            "signals": [],
        }
    return movie_behaviors[mid]


def _build_recommendation_movie_behaviors(conn, user_id: int) -> Dict[str, Dict[str, Any]]:
    movie_behaviors: Dict[str, Dict[str, Any]] = {}

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT mid, rating FROM user_movie_ratings WHERE user_id = %s",
            (user_id,),
        )
        rating_rows = cursor.fetchall()

        cursor.execute(
            "SELECT mid, pref_type FROM user_movie_prefs WHERE user_id = %s",
            (user_id,),
        )
        pref_rows = cursor.fetchall()

    for row in rating_rows:
        mid = row["mid"]
        rating = float(row["rating"])
        behavior = _get_or_create_behavior(movie_behaviors, mid)
        behavior["rating"] = rating
        if rating >= STRONG_POSITIVE_RATING_THRESHOLD:
            behavior["positive_weight"] += STRONG_POSITIVE_RATING_BASE + (
                rating - STRONG_POSITIVE_RATING_THRESHOLD
            ) * STRONG_POSITIVE_RATING_STEP
            behavior["signals"].append("strong_positive_rating")
        elif rating >= WEAK_POSITIVE_RATING_THRESHOLD:
            behavior["positive_weight"] += WEAK_POSITIVE_RATING_WEIGHT
            behavior["signals"].append("weak_positive_rating")
        elif rating <= WEAK_NEGATIVE_RATING_THRESHOLD:
            behavior["negative_weight"] += WEAK_NEGATIVE_BASE + max(
                0.0,
                WEAK_NEGATIVE_RATING_THRESHOLD - rating,
            ) * WEAK_NEGATIVE_STEP
            behavior["signals"].append("weak_negative_rating")

    for row in pref_rows:
        mid = row["mid"]
        pref_type = row["pref_type"]
        behavior = _get_or_create_behavior(movie_behaviors, mid)
        if pref_type == "like":
            behavior["is_liked"] = True
            behavior["positive_weight"] += LIKE_WEIGHT
            behavior["signals"].append("like")
        elif pref_type == "want_to_watch":
            behavior["is_want_to_watch"] = True
            behavior["positive_weight"] += WANT_WEIGHT
            behavior["exploration_weight"] += WANT_EXPLORATION_WEIGHT
            behavior["signals"].append("want_to_watch")

    for behavior in movie_behaviors.values():
        behavior["positive_weight"] = round(float(behavior["positive_weight"]), 6)
        behavior["negative_weight"] = round(float(behavior["negative_weight"]), 6)
        behavior["exploration_weight"] = round(float(behavior["exploration_weight"]), 6)
        behavior["context_weight"] = round(
            behavior["positive_weight"] - behavior["negative_weight"],
            6,
        )

    return movie_behaviors


def build_user_recommendation_profile(conn, user_id: int) -> Dict[str, Any]:
    movie_behaviors = _build_recommendation_movie_behaviors(conn, user_id)
    ordered_behaviors = sorted(
        movie_behaviors.values(),
        key=lambda item: (
            -item["context_weight"],
            -item["positive_weight"],
            item["mid"],
        ),
    )

    positive_movie_ids = [
        item["mid"]
        for item in ordered_behaviors
        if item["context_weight"] > POSITIVE_CONTEXT_THRESHOLD
    ]
    negative_movie_ids = [
        item["mid"]
        for item in ordered_behaviors
        if item["negative_weight"] > 0
    ]
    representative_movie_ids = [
        item["mid"]
        for item in ordered_behaviors
        if item["positive_weight"] > 0
    ][:6]
    context_movie_ids = positive_movie_ids[:24]
    graph_context_movie_ids = positive_movie_ids[:18]
    hard_exclude_movie_ids = [
        item["mid"]
        for item in ordered_behaviors
        if item["rating"] is not None or item["is_liked"]
    ]

    summary = {
        "rating_count": sum(1 for item in ordered_behaviors if item["rating"] is not None),
        "strong_positive_ratings": sum(
            1
            for item in ordered_behaviors
            if item["rating"] is not None and item["rating"] >= STRONG_POSITIVE_RATING_THRESHOLD
        ),
        "weak_positive_ratings": sum(
            1
            for item in ordered_behaviors
            if item["rating"] is not None
            and WEAK_POSITIVE_RATING_THRESHOLD <= item["rating"] < STRONG_POSITIVE_RATING_THRESHOLD
        ),
        "weak_negative_ratings": sum(
            1
            for item in ordered_behaviors
            if item["rating"] is not None and item["rating"] <= WEAK_NEGATIVE_RATING_THRESHOLD
        ),
        "likes": sum(1 for item in ordered_behaviors if item["is_liked"]),
        "wants": sum(1 for item in ordered_behaviors if item["is_want_to_watch"]),
        "positive_movie_count": len(positive_movie_ids),
        "behavior_movie_count": len(ordered_behaviors),
    }
    summary["cold_start"] = (
        summary["strong_positive_ratings"]
        + summary["weak_positive_ratings"]
        + summary["likes"]
        + summary["wants"]
    ) < 4 or summary["positive_movie_count"] < 3

    return {
        "movie_feedback": {item["mid"]: item for item in ordered_behaviors},
        "positive_movie_ids": positive_movie_ids,
        "negative_movie_ids": negative_movie_ids,
        "representative_movie_ids": representative_movie_ids,
        "context_movie_ids": context_movie_ids,
        "graph_context_movie_ids": graph_context_movie_ids,
        "hard_exclude_movie_ids": hard_exclude_movie_ids,
        "summary": summary,
    }


def get_recommendation_excluded_movie_ids(conn, user_id: int, limit: int | None = None) -> List[str]:
    profile = build_user_recommendation_profile(conn, user_id)
    movie_ids = profile["hard_exclude_movie_ids"]
    if limit is None:
        return movie_ids
    return movie_ids[:limit]


def get_high_rated_movie_ids(conn, user_id: int, limit: int = 5) -> List[str]:
    """ 获取用户最近打高分的电影ID列表，作为推荐引擎的种子节点 """
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT mid FROM user_movie_ratings WHERE user_id = %s AND rating >= 4.0 "
            "ORDER BY updated_at DESC, rated_at DESC LIMIT %s",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        return [r["mid"] for r in rows]


def get_recommendation_seed_movie_ids(conn, user_id: int, limit: int = 5) -> List[str]:
    """组合高分、喜欢和想看，生成推荐种子电影列表。"""
    seed_ids: List[str] = []
    seen = set()

    def extend_from_rows(rows):
        for row in rows:
            mid = row["mid"]
            if mid in seen:
                continue
            seen.add(mid)
            seed_ids.append(mid)
            if len(seed_ids) >= limit:
                break

    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT mid FROM user_movie_ratings WHERE user_id = %s AND rating >= 4.0 "
            "ORDER BY updated_at DESC, rated_at DESC LIMIT %s",
            (user_id, limit),
        )
        extend_from_rows(cursor.fetchall())

        if len(seed_ids) < limit:
            cursor.execute(
                "SELECT mid FROM user_movie_prefs WHERE user_id = %s AND pref_type = 'like' "
                "ORDER BY updated_at DESC, created_at DESC LIMIT %s",
                (user_id, limit),
            )
            extend_from_rows(cursor.fetchall())

        if len(seed_ids) < limit:
            cursor.execute(
                "SELECT mid FROM user_movie_prefs WHERE user_id = %s AND pref_type = 'want_to_watch' "
                "ORDER BY updated_at DESC, created_at DESC LIMIT %s",
                (user_id, limit),
            )
            extend_from_rows(cursor.fetchall())

    return seed_ids[:limit]


def get_seen_movie_ids(conn, user_id: int, limit: int | None = None) -> List[str]:
    """获取用户已交互过的电影，作为推荐过滤集合。"""
    sql = """
        SELECT mid
        FROM (
            SELECT mid, updated_at AS sort_time
            FROM user_movie_ratings
            WHERE user_id = %s
            UNION ALL
            SELECT mid, updated_at AS sort_time
            FROM user_movie_prefs
            WHERE user_id = %s
        ) AS interacted
        GROUP BY mid
        ORDER BY MAX(sort_time) DESC
    """
    params: list = [user_id, user_id]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [r["mid"] for r in rows]
