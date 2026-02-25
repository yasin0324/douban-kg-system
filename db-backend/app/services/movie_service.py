"""
电影查询服务
"""
from typing import Optional, List


# ---------- MySQL 搜索 ----------

def search_movies(conn, q: str, page: int = 1, size: int = 20) -> dict:
    """关键词搜索电影（MySQL LIKE）"""
    offset = (page - 1) * size
    like_q = f"%{q}%"
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as total FROM movies WHERE name LIKE %s OR alias LIKE %s",
            (like_q, like_q),
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT douban_id as mid, name as title, douban_score as rating, year, cover, genres "
            "FROM movies WHERE name LIKE %s OR alias LIKE %s "
            "ORDER BY douban_score DESC LIMIT %s OFFSET %s",
            (like_q, like_q, size, offset),
        )
        items = cursor.fetchall()
    # 将 genres 字段从 "剧情/犯罪" 转换为列表
    for item in items:
        if item.get("genres"):
            item["genres"] = item["genres"].split("/")
        else:
            item["genres"] = []
    return {"items": items, "total": total, "page": page, "size": size}


# ---------- Neo4j 详情 ----------

def get_movie_detail(session, mid: str) -> Optional[dict]:
    """从 Neo4j 获取电影详情 + 导演 + 演员 + 类型"""
    result = session.run(
        """
        MATCH (m:Movie {mid: $mid})
        OPTIONAL MATCH (m)<-[:DIRECTED]-(d:Person)
        OPTIONAL MATCH (m)<-[act:ACTED_IN]-(a:Person)
        OPTIONAL MATCH (m)-[:HAS_GENRE]->(g:Genre)
        RETURN m, 
               collect(DISTINCT {pid: d.pid, name: d.name}) AS directors,
               collect(DISTINCT {pid: a.pid, name: a.name, order: act.order}) AS actors,
               collect(DISTINCT g.name) AS genres
        """,
        mid=mid,
    )
    record = result.single()
    if not record:
        return None

    m = record["m"]
    directors = [d for d in record["directors"] if d["pid"] is not None]
    actors = [a for a in record["actors"] if a["pid"] is not None]
    # 按 order 排序演员
    actors.sort(key=lambda x: x.get("order") or 999)

    return {
        "mid": m.get("mid"),
        "title": m.get("title") or m.get("name"),
        "rating": m.get("rating"),
        "year": m.get("year"),
        "content_type": m.get("content_type") or m.get("type"),
        "genres": record["genres"],
        "regions": m.get("regions"),
        "cover": m.get("cover"),
        "storyline": m.get("storyline"),
        "url": f"https://movie.douban.com/subject/{m.get('mid')}/",
        "directors": directors,
        "actors": actors,
    }


def get_movie_credits(session, mid: str) -> Optional[dict]:
    """获取电影演职人员"""
    result = session.run(
        """
        MATCH (m:Movie {mid: $mid})
        OPTIONAL MATCH (m)<-[:DIRECTED]-(d:Person)
        OPTIONAL MATCH (m)<-[act:ACTED_IN]-(a:Person)
        RETURN m.mid AS mid,
               collect(DISTINCT {pid: d.pid, name: d.name}) AS directors,
               collect(DISTINCT {pid: a.pid, name: a.name, order: act.order}) AS actors
        """,
        mid=mid,
    )
    record = result.single()
    if not record:
        return None
    directors = [d for d in record["directors"] if d["pid"] is not None]
    actors = [a for a in record["actors"] if a["pid"] is not None]
    actors.sort(key=lambda x: x.get("order") or 999)
    return {"mid": record["mid"], "directors": directors, "actors": actors}


def get_top_movies(session, genre: str = None, limit: int = 20) -> list:
    """高分电影排行"""
    if genre:
        result = session.run(
            """
            MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre {name: $genre})
            WHERE m.rating IS NOT NULL
            RETURN m.mid AS mid, m.title AS title, m.rating AS rating, m.year AS year, m.cover AS cover
            ORDER BY m.rating DESC
            LIMIT $limit
            """,
            genre=genre, limit=limit,
        )
    else:
        result = session.run(
            """
            MATCH (m:Movie)
            WHERE m.rating IS NOT NULL
            RETURN m.mid AS mid, m.title AS title, m.rating AS rating, m.year AS year, m.cover AS cover
            ORDER BY m.rating DESC
            LIMIT $limit
            """,
            limit=limit,
        )
    return [dict(record) for record in result]


def get_genres(session) -> list:
    """获取所有类型"""
    result = session.run("MATCH (g:Genre) RETURN g.name AS name ORDER BY g.name")
    return [record["name"] for record in result]


def filter_movies(
    session,
    genre: str = None,
    year_from: int = None,
    year_to: int = None,
    rating_min: float = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """多条件筛选电影"""
    conditions = ["m.rating IS NOT NULL"]
    params: dict = {"skip": (page - 1) * size, "limit": size}

    match_clause = "MATCH (m:Movie)"
    if genre:
        match_clause = "MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre {name: $genre})"
        params["genre"] = genre
    if year_from:
        conditions.append("m.year >= $year_from")
        params["year_from"] = year_from
    if year_to:
        conditions.append("m.year <= $year_to")
        params["year_to"] = year_to
    if rating_min:
        conditions.append("m.rating >= $rating_min")
        params["rating_min"] = rating_min

    where = " AND ".join(conditions)

    # 获取总数
    count_q = f"{match_clause} WHERE {where} RETURN count(m) AS total"
    total = session.run(count_q, **params).single()["total"]

    # 获取分页数据
    data_q = (
        f"{match_clause} WHERE {where} "
        "RETURN m.mid AS mid, m.title AS title, m.rating AS rating, m.year AS year, m.cover AS cover "
        "ORDER BY m.rating DESC SKIP $skip LIMIT $limit"
    )
    items = [dict(r) for r in session.run(data_q, **params)]

    return {"items": items, "total": total, "page": page, "size": size}
