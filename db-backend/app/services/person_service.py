"""
影人查询服务
"""
from typing import Optional


ROLE_PRIORITY = ("director", "actor")


def _merge_person_movies(*movie_groups: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in movie_groups:
        for item in group:
            mid = item.get("mid")
            if not mid:
                continue
            movie = merged.setdefault(
                mid,
                {
                    "mid": mid,
                    "title": item.get("title"),
                    "rating": item.get("rating"),
                    "year": item.get("year"),
                    "role": item.get("role"),
                    "roles": [],
                },
            )
            for field in ("title", "rating", "year"):
                if movie.get(field) is None and item.get(field) is not None:
                    movie[field] = item.get(field)
            role = item.get("role")
            if role and role not in movie["roles"]:
                movie["roles"].append(role)

    movies = []
    for movie in merged.values():
        ordered_roles = [role for role in ROLE_PRIORITY if role in movie["roles"]]
        extra_roles = [role for role in movie["roles"] if role not in ROLE_PRIORITY]
        movie["roles"] = ordered_roles + extra_roles
        movie["role"] = movie["roles"][0] if len(movie["roles"]) == 1 else None
        movies.append(movie)
    movies.sort(key=lambda x: x.get("year") or 0, reverse=True)
    return movies


def search_persons(conn, q: str, page: int = 1, size: int = 20) -> dict:
    """关键词搜索影人（MySQL LIKE，支持忽略分隔符·）"""
    offset = (page - 1) * size
    like_q = f"%{q}%"
    # 去掉常见的分隔符用于模糊匹配
    clean_q = q.replace("·", "").replace("・", "").replace(".", "").replace(" ", "")
    like_clean = f"%{clean_q}%"
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as total FROM person WHERE name LIKE %s "
            "OR REPLACE(REPLACE(REPLACE(REPLACE(name, '·', ''), '・', ''), '.', ''), ' ', '') LIKE %s",
            (like_q, like_clean),
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT person_id as pid, name, profession FROM person "
            "WHERE name LIKE %s "
            "OR REPLACE(REPLACE(REPLACE(REPLACE(name, '·', ''), '・', ''), '.', ''), ' ', '') LIKE %s "
            "ORDER BY person_id LIMIT %s OFFSET %s",
            (like_q, like_clean, size, offset),
        )
        items = cursor.fetchall()
    return {"items": items, "total": total, "page": page, "size": size}


def get_person_detail(session, pid: str) -> Optional[dict]:
    """从 Neo4j 获取影人详情"""
    result = session.run(
        """
        MATCH (p:Person {pid: $pid})
        OPTIONAL MATCH (p)-[:DIRECTED]->(dm:Movie)
        OPTIONAL MATCH (p)-[:ACTED_IN]->(am:Movie)
        RETURN p,
               count(DISTINCT dm) AS directed_count,
               count(DISTINCT am) AS acted_count
        """,
        pid=pid,
    )
    record = result.single()
    if not record:
        return None
    p = record["p"]
    return {
        "pid": p.get("pid"),
        "name": p.get("name"),
        "sex": p.get("sex"),
        "birth": p.get("birth"),
        "birthplace": p.get("birthplace"),
        "profession": p.get("profession"),
        "biography": p.get("biography"),
        "movie_count": record["directed_count"] + record["acted_count"],
        "directed_count": record["directed_count"],
    }


def get_person_movies(session, pid: str) -> Optional[dict]:
    """获取影人参演/执导的电影"""
    result = session.run(
        """
        MATCH (p:Person {pid: $pid})
        OPTIONAL MATCH (p)-[:DIRECTED]->(dm:Movie)
        OPTIONAL MATCH (p)-[:ACTED_IN]->(am:Movie)
        WITH p, 
             collect(DISTINCT {mid: dm.mid, title: dm.title, rating: dm.rating, year: dm.year, role: 'director'}) AS directed,
             collect(DISTINCT {mid: am.mid, title: am.title, rating: am.rating, year: am.year, role: 'actor'}) AS acted
        RETURN p.pid AS pid, p.name AS name, directed, acted
        """,
        pid=pid,
    )
    record = result.single()
    if not record:
        return None
    directed = [d for d in record["directed"] if d["mid"] is not None]
    acted = [a for a in record["acted"] if a["mid"] is not None]
    movies = _merge_person_movies(directed, acted)
    return {"pid": record["pid"], "name": record["name"], "movies": movies}


def get_collaborators(session, pid: str, limit: int = 10) -> list:
    """获取影人合作者"""
    result = session.run(
        """
        MATCH (p:Person {pid: $pid})-[:ACTED_IN|DIRECTED]->(m:Movie)<-[:ACTED_IN|DIRECTED]-(co:Person)
        WHERE co.pid <> $pid
        RETURN co.pid AS pid, co.name AS name, count(DISTINCT m) AS collaboration_count
        ORDER BY collaboration_count DESC
        LIMIT $limit
        """,
        pid=pid, limit=limit,
    )
    return [dict(r) for r in result]
