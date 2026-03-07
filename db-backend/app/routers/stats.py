"""
统计路由 — /api/stats
"""
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_neo4j_session

router = APIRouter(prefix="/api/stats", tags=["统计"])


@router.get("/overview", summary="图谱总体统计")
def overview(session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (m:Movie) WITH count(m) AS movie_count
        MATCH (p:Person) WITH movie_count, count(p) AS person_count
        MATCH (g:Genre) WITH movie_count, person_count, count(g) AS genre_count
        MATCH ()-[r]->() WITH movie_count, person_count, genre_count, count(r) AS rel_count
        RETURN movie_count, person_count, genre_count, rel_count
        """
    )
    record = result.single()
    return {
        "movie_count": record["movie_count"],
        "person_count": record["person_count"],
        "genre_count": record["genre_count"],
        "relationship_count": record["rel_count"],
    }


@router.get("/genre-distribution", summary="类型分布")
def genre_distribution(session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (g:Genre)<-[:HAS_GENRE]-(m:Movie)
        RETURN g.name AS genre, count(m) AS count
        ORDER BY count DESC
        """
    )
    return [dict(r) for r in result]


@router.get("/year-distribution", summary="年代分布")
def year_distribution(session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (m:Movie)
        WHERE m.year IS NOT NULL
        RETURN m.year AS year, count(m) AS count
        ORDER BY year
        """
    )
    return [dict(r) for r in result]


@router.get("/top-actors", summary="参演最多的演员")
def top_actors(limit: int = Query(20, ge=1, le=100), session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN p.pid AS pid, p.name AS name, count(m) AS movie_count
        ORDER BY movie_count DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return [dict(r) for r in result]


@router.get("/top-directors", summary="执导最多的导演")
def top_directors(limit: int = Query(20, ge=1, le=100), session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (p:Person)-[:DIRECTED]->(m:Movie)
        RETURN p.pid AS pid, p.name AS name, count(m) AS movie_count
        ORDER BY movie_count DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return [dict(r) for r in result]


@router.get("/rating-distribution", summary="评分分布")
def rating_distribution(session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (m:Movie)
        WHERE m.rating IS NOT NULL
        WITH toInteger(m.rating) AS rating_int, count(m) AS count
        RETURN rating_int AS rating, count
        ORDER BY rating
        """
    )
    return [dict(r) for r in result]


@router.get("/collaborations", summary="黄金搭档网络图")
def collaborations(limit: int = Query(50, ge=1, le=200), session=Depends(get_neo4j_session)):
    try:
        # 这个版本：强迫 Neo4j 执行计划变小
        query = """
        MATCH (m:Movie)
        WITH m LIMIT 20
        MATCH (p1:Person)-[:DIRECTED|ACTED_IN]->(m)<-[:DIRECTED|ACTED_IN]-(p2:Person)
        WHERE id(p1) < id(p2)
        RETURN p1.pid AS source_id, p1.name AS source_name, 
               p2.pid AS target_id, p2.name AS target_name, 
               count(m) AS value
        """
        result = session.run(query)
        # 手动去重和排序
        items = [dict(r) for r in result]
        items.sort(key=lambda x: x["value"], reverse=True)
        return items[:limit]
    except Exception as e:
        import traceback
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
        raise e

@router.get("/genre-co-occurrence", summary="类型关联和弦图")
def genre_co_occurrence(limit: int = Query(50, ge=1, le=200), session=Depends(get_neo4j_session)):
    try:
        # 强制小样本
        query = """
        MATCH (m:Movie)
        WITH m LIMIT 100
        MATCH (g1:Genre)<-[:HAS_GENRE]-(m)-[:HAS_GENRE]->(g2:Genre)
        WHERE id(g1) < id(g2)
        RETURN g1.name AS source, g2.name AS target, count(m) AS value
        """
        result = session.run(query)
        items = [dict(r) for r in result]
        items.sort(key=lambda x: x["value"], reverse=True)
        return items[:limit]
    except Exception as e:
        import traceback
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
        raise e


@router.get("/genre-year-trends", summary="主要流派年代演变")
def genre_year_trends(session=Depends(get_neo4j_session)):
    # 取排名前 8 的类型
    top_genres_res = session.run(
        """
        MATCH (g:Genre)<-[:HAS_GENRE]-(:Movie)
        RETURN g.name AS genre, count(*) AS total
        ORDER BY total DESC
        LIMIT 8
        """
    )
    top_genres = [r["genre"] for r in top_genres_res]

    result = session.run(
        """
        MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre)
        WHERE m.year IS NOT NULL AND g.name IN $top_genres AND m.year >= 1980 AND m.year <= 2030
        WITH m.year AS year, g.name AS genre, count(m) AS count
        RETURN year, genre, count
        ORDER BY year, genre
        """,
        top_genres=top_genres,
    )
    return {"genres": top_genres, "trends": [dict(r) for r in result]}


@router.get("/rating-year-trends", summary="评分年代变化")
def rating_year_trends(session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (m:Movie)
        WHERE m.year IS NOT NULL AND m.rating IS NOT NULL AND m.year >= 1950 AND m.year <= 2030
        WITH m.year AS year, avg(m.rating) AS avg_rating, count(m) AS count
        WHERE count >= 10
        RETURN year, round(avg_rating * 10) / 10.0 AS avg_rating, count
        ORDER BY year
        """
    )
    return [dict(r) for r in result]


@router.get("/top-rated-actors", summary="参演高分电影最多的演员")
def top_rated_actors(limit: int = Query(20, ge=1, le=100), session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE m.rating IS NOT NULL
        WITH p, count(m) AS movie_count, avg(m.rating) AS avg_rating
        WHERE movie_count >= 10
        RETURN p.pid AS pid, p.name AS name, movie_count, round(avg_rating * 100) / 100.0 AS avg_rating
        ORDER BY avg_rating DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return [dict(r) for r in result]


@router.get("/top-rated-directors", summary="执导高分电影最多的导演")
def top_rated_directors(limit: int = Query(20, ge=1, le=100), session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (p:Person)-[:DIRECTED]->(m:Movie)
        WHERE m.rating IS NOT NULL
        WITH p, count(m) AS movie_count, avg(m.rating) AS avg_rating
        WHERE movie_count >= 5
        RETURN p.pid AS pid, p.name AS name, movie_count, round(avg_rating * 100) / 100.0 AS avg_rating
        ORDER BY avg_rating DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    return [dict(r) for r in result]


@router.get("/actor-rating-distribution", summary="Top演员参演质量分布")
def actor_rating_distribution(session=Depends(get_neo4j_session)):
    # 取参演最多前 10 名演员的所有电影评分
    top_res = session.run(
        """
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WITH p, count(m) AS total
        ORDER BY total DESC
        LIMIT 10
        RETURN p.pid AS pid, p.name AS name
        """
    )
    top_actors = [{"pid": r["pid"], "name": r["name"]} for r in top_res]
    pids = [actor["pid"] for actor in top_actors]
    
    result = session.run(
        """
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE p.pid IN $pids AND m.rating IS NOT NULL
        RETURN p.name AS name, m.rating AS rating
        """,
        pids=pids
    )
    data = {}
    for r in result:
        name = r["name"]
        if name not in data:
            data[name] = []
        data[name].append(r["rating"])
        
    return [{"name": name, "ratings": ratings} for name, ratings in data.items()]


@router.get("/rating-vote-scatter", summary="评分与评论人数散点图")
def rating_vote_scatter(limit: int = Query(500), session=Depends(get_neo4j_session)):
    result = session.run(
        """
        MATCH (m:Movie)
        WHERE m.rating IS NOT NULL AND m.votes IS NOT NULL AND m.votes > 0
        RETURN m.title AS title, m.rating AS rating, m.votes AS votes
        ORDER BY m.votes DESC
        LIMIT $limit
        """,
        limit=limit
    )
    return [dict(r) for r in result]
