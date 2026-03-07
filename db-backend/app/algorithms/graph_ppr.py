"""
隐性关系挖掘 (Personalized PageRank)
"""
import asyncio
import logging
from typing import Any, Dict, List

from app.algorithms.common import dedupe_preserve_order, run_query
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 1200
GRAPH_NAME = "recommendation_ppr_graph"

GRAPH_EXISTS_QUERY = "RETURN gds.graph.exists($graph_name) AS exists"

PROJECT_QUERY = """
CALL gds.graph.project(
  $graph_name,
  ['Movie', 'Person', 'Genre'],
  {
    ACTED_IN: {type: 'ACTED_IN', orientation: 'UNDIRECTED'},
    DIRECTED: {type: 'DIRECTED', orientation: 'UNDIRECTED'},
    HAS_GENRE: {type: 'HAS_GENRE', orientation: 'UNDIRECTED'}
  }
)
YIELD graphName
RETURN graphName
"""

PPR_QUERY = """
MATCH (m:Movie)
WHERE m.mid IN $seed_ids
WITH collect(m) AS source_nodes
CALL gds.pageRank.stream($graph_name, {
  sourceNodes: source_nodes,
  dampingFactor: $damping_factor,
  maxIterations: $max_iterations
})
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
WHERE 'Movie' IN labels(node)
  AND NOT node.mid IN $seed_ids
  AND NOT node.mid IN $seen_movie_ids
RETURN node.mid AS movie_id,
       node.title AS title,
       score AS ppr_score
ORDER BY ppr_score DESC, movie_id ASC
LIMIT $limit
"""


def _ensure_projection(session, timeout_ms: int | None = None):
    exists_records = run_query(
        session,
        GRAPH_EXISTS_QUERY,
        timeout_ms=timeout_ms,
        graph_name=GRAPH_NAME,
    )
    if exists_records and exists_records[0]["exists"]:
        return

    run_query(
        session,
        PROJECT_QUERY,
        timeout_ms=max(timeout_ms or 0, 5000),
        graph_name=GRAPH_NAME,
    )


def _get_graph_ppr_recommendations_sync(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    del user_id, exclude_mock_users

    seed_ids = dedupe_preserve_order(seed_movie_ids)
    if not seed_ids:
        return []

    seen_ids = dedupe_preserve_order(seen_movie_ids)
    driver = Neo4jConnection.get_driver()
    results = []

    with driver.session() as session:
        try:
            _ensure_projection(session, timeout_ms=timeout_ms)
            records = run_query(
                session,
                PPR_QUERY,
                timeout_ms=timeout_ms,
                graph_name=GRAPH_NAME,
                seed_ids=seed_ids,
                seen_movie_ids=seen_ids,
                damping_factor=0.7,
                max_iterations=25,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("Neo4j GDS PPR 执行失败，已自动降级: %s", exc)
            return []

    for record in records:
        results.append({
            "movie_id": record["movie_id"],
            "title": record.get("title", ""),
            "score": float(record["ppr_score"]),
            "reasons": ["通过图谱随机游走发现的隐性关联"],
            "source": "graph_ppr",
        })

    return results


async def get_graph_ppr_recommendations(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    """
    基于 Neo4j GDS 的 Personalized PageRank，优先复用常驻投影图。
    """
    return await asyncio.to_thread(
        _get_graph_ppr_recommendations_sync,
        user_id,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )
