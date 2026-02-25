"""
影人查询服务
"""
from typing import Optional


def search_persons(conn, q: str, page: int = 1, size: int = 20) -> dict:
    """关键词搜索影人（MySQL LIKE）"""
    offset = (page - 1) * size
    like_q = f"%{q}%"
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as total FROM person WHERE name LIKE %s",
            (like_q,),
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT person_id as pid, name, profession FROM person "
            "WHERE name LIKE %s ORDER BY person_id LIMIT %s OFFSET %s",
            (like_q, size, offset),
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
    movies = directed + acted
    movies.sort(key=lambda x: x.get("year") or 0, reverse=True)
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
