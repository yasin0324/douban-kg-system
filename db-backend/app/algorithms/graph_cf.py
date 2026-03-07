"""
基于图拓扑的协同过滤 (Graph-Collaborative-Filtering)
"""
import asyncio
from typing import Any, Dict, List

from app.algorithms.common import dedupe_preserve_order, run_query
from app.db.neo4j import Neo4jConnection

POSITIVE_RATING = 4.0
MIN_OVERLAP = 2
SHRINKAGE = 2.0
NEIGHBOR_LIMIT = 30
DEFAULT_TIMEOUT_MS = 800

CF_QUERY = """
WITH $seed_ids AS seed_ids
UNWIND seed_ids AS seed_id
MATCH (seed:Movie {mid: seed_id})<-[shared_rel:RATED]-(neighbor:User)
WHERE neighbor.id <> $user_id
  AND shared_rel.rating >= $positive_rating
  AND (NOT $exclude_mock_users OR coalesce(neighbor.is_mock, false) = false)
WITH seed_ids, neighbor, count(DISTINCT seed_id) AS overlap
WHERE overlap >= $min_overlap
MATCH (neighbor)-[liked_rel:RATED]->(:Movie)
WHERE liked_rel.rating >= $positive_rating
WITH seed_ids, neighbor, overlap, count(liked_rel) AS neighbor_like_count
WITH seed_ids, neighbor, overlap,
     (toFloat(overlap) / sqrt(toFloat(size(seed_ids)) * toFloat(neighbor_like_count))) *
     (toFloat(overlap) / (toFloat(overlap) + $shrinkage)) AS similarity
WHERE similarity > 0
ORDER BY similarity DESC
LIMIT $neighbor_limit
MATCH (neighbor)-[candidate_rel:RATED]->(candidate:Movie)
WHERE candidate_rel.rating >= $positive_rating
  AND NOT candidate.mid IN $seed_ids
  AND NOT candidate.mid IN $seen_movie_ids
RETURN candidate.mid AS movie_id,
       candidate.title AS title,
       sum(similarity * candidate_rel.rating) AS cf_score,
       count(DISTINCT neighbor) AS similar_user_count,
       max(similarity) AS strongest_similarity
ORDER BY cf_score DESC, similar_user_count DESC, movie_id ASC
LIMIT $limit
"""


def _get_graph_cf_recommendations_sync(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    seed_ids = dedupe_preserve_order(seed_movie_ids)
    if not seed_ids:
        return []

    seen_ids = dedupe_preserve_order(seen_movie_ids)
    driver = Neo4jConnection.get_driver()

    with driver.session() as session:
        records = run_query(
            session,
            CF_QUERY,
            timeout_ms=timeout_ms,
            user_id=user_id,
            seed_ids=seed_ids,
            seen_movie_ids=seen_ids,
            exclude_mock_users=exclude_mock_users,
            positive_rating=POSITIVE_RATING,
            min_overlap=MIN_OVERLAP,
            shrinkage=SHRINKAGE,
            neighbor_limit=NEIGHBOR_LIMIT,
            limit=limit,
        )

    results = []
    for record in records:
        user_count = int(record["similar_user_count"])
        strongest_similarity = float(record["strongest_similarity"] or 0.0)
        reason = f"有 {user_count} 位相似用户给它打了高分"
        if strongest_similarity > 0:
            reason += f"，最强近邻相似度 {strongest_similarity:.2f}"
        results.append({
            "movie_id": record["movie_id"],
            "title": record.get("title", ""),
            "score": float(record["cf_score"]),
            "reasons": [reason],
            "source": "graph_cf",
        })

    return results


async def get_graph_cf_recommendations(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    """
    基于显式种子电影构建邻域，避免直接读取目标用户的完整评分边造成评估泄漏。
    """
    return await asyncio.to_thread(
        _get_graph_cf_recommendations_sync,
        user_id,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )
