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
