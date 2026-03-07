"""
用户行为服务 — 偏好（喜欢/想看）+ 评分 CRUD
"""
from typing import List, Optional
import logging
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)


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


def get_seen_movie_ids(conn, user_id: int, limit: int | None = None) -> List[str]:
    """获取用户历史评分过的电影，作为推荐过滤集合。"""
    sql = (
        "SELECT mid FROM user_movie_ratings WHERE user_id = %s "
        "ORDER BY updated_at DESC, rated_at DESC"
    )
    params: list = [user_id]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [r["mid"] for r in rows]
