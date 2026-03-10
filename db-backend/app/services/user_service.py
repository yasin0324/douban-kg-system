"""
用户行为服务 — 偏好（喜欢/想看）+ 评分 CRUD
"""
from datetime import date
from typing import Optional


def add_preference(conn, user_id: int, mid: str, pref_type: str) -> dict:
    with conn.cursor() as cursor:
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

        cursor.execute(
            f"SELECT COUNT(*) as total FROM user_movie_prefs {where}",
            params,
        )
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


def check_movie_released(conn, mid: str):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT name, year, release_date FROM movies WHERE douban_id = %s",
            (mid,),
        )
        movie = cursor.fetchone()

    if not movie:
        raise ValueError("电影不存在")

    year = movie.get("year")
    release_date_str = movie.get("release_date")
    if release_date_str:
        release_date_str = release_date_str[:10]

    today = date.today()
    current_date = today.isoformat()
    current_year = today.year
    is_unreleased = False
    if year and year > current_year:
        is_unreleased = True
    elif year == current_year:
        if not release_date_str:
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
        return cursor.rowcount > 0


def list_ratings(conn, user_id: int, page: int = 1, size: int = 20) -> dict:
    offset = (page - 1) * size
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as total FROM user_movie_ratings WHERE user_id = %s",
            (user_id,),
        )
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
