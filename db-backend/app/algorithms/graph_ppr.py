"""
隐性关系挖掘 (Personalized PageRank)
"""
import asyncio
import logging
from typing import Any, Dict, List

from app.algorithms.common import (
    build_seed_profile,
    dedupe_preserve_order,
    fetch_movie_feature_map,
    run_query,
    score_metadata_alignment,
)
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 1200
FALLBACK_GRAPH_NAME = "recommendation_ppr_graph"
LOCAL_GRAPH_NAME_TEMPLATE = "recommendation_ppr_local_graph_{user_id}"

GRAPH_EXISTS_QUERY = "RETURN gds.graph.exists($graph_name) AS exists"
DROP_GRAPH_QUERY = "CALL gds.graph.drop($graph_name, false) YIELD graphName RETURN graphName"

LOCAL_CANDIDATE_QUERY = """
MATCH (source:Movie)-[source_rel:DIRECTED|ACTED_IN|HAS_GENRE]-(shared_node)-[target_rel:DIRECTED|ACTED_IN|HAS_GENRE]-(target:Movie)
WHERE source.mid IN $seed_ids
  AND NOT target.mid IN $seed_ids
  AND NOT target.mid IN $seen_movie_ids
  AND type(source_rel) = type(target_rel)
WITH target,
     type(source_rel) AS rel_type,
     count(DISTINCT shared_node) AS shared_node_count,
     count(DISTINCT source) AS shared_seed_count
WITH target,
     sum(
       CASE rel_type
         WHEN 'DIRECTED' THEN 4.2 * CASE WHEN shared_node_count > 0 THEN 1.0 ELSE 0.0 END
         WHEN 'ACTED_IN' THEN 1.4 * toFloat(CASE WHEN shared_node_count > 3 THEN 3 ELSE shared_node_count END)
         ELSE 0.55 * toFloat(CASE WHEN shared_node_count > 2 THEN 2 ELSE shared_node_count END)
       END +
       0.45 * toFloat(CASE WHEN shared_seed_count > 1 THEN shared_seed_count - 1 ELSE 0 END)
     ) AS local_score
RETURN target.mid AS movie_id,
       local_score
ORDER BY local_score DESC, movie_id ASC
LIMIT $limit
"""

PROJECT_LOCAL_MOVIE_QUERY = """
CALL gds.graph.project.cypher(
  $graph_name,
  'MATCH (m:Movie) WHERE m.mid IN $projection_ids RETURN id(m) AS id',
  '
  MATCH (m1:Movie)-[:DIRECTED]-(shared:Person)-[:DIRECTED]-(m2:Movie)
  WHERE m1.mid IN $projection_ids
    AND m2.mid IN $projection_ids
    AND id(m1) < id(m2)
  WITH m1, m2, 4.8 AS weight
  RETURN id(m1) AS source, id(m2) AS target, weight
  UNION ALL
  MATCH (m1:Movie)-[:DIRECTED]-(shared:Person)-[:DIRECTED]-(m2:Movie)
  WHERE m1.mid IN $projection_ids
    AND m2.mid IN $projection_ids
    AND id(m1) < id(m2)
  WITH m1, m2, 4.8 AS weight
  RETURN id(m2) AS source, id(m1) AS target, weight
  UNION ALL
  MATCH (m1:Movie)-[:ACTED_IN]-(shared:Person)-[:ACTED_IN]-(m2:Movie)
  WHERE m1.mid IN $projection_ids
    AND m2.mid IN $projection_ids
    AND id(m1) < id(m2)
  WITH m1, m2, count(DISTINCT shared) AS overlap
  WITH m1, m2, 1.55 * toFloat(CASE WHEN overlap > 3 THEN 3 ELSE overlap END) AS weight
  WHERE weight > 0
  RETURN id(m1) AS source, id(m2) AS target, weight
  UNION ALL
  MATCH (m1:Movie)-[:ACTED_IN]-(shared:Person)-[:ACTED_IN]-(m2:Movie)
  WHERE m1.mid IN $projection_ids
    AND m2.mid IN $projection_ids
    AND id(m1) < id(m2)
  WITH m1, m2, count(DISTINCT shared) AS overlap
  WITH m1, m2, 1.55 * toFloat(CASE WHEN overlap > 3 THEN 3 ELSE overlap END) AS weight
  WHERE weight > 0
  RETURN id(m2) AS source, id(m1) AS target, weight
  UNION ALL
  MATCH (m1:Movie)-[:HAS_GENRE]-(shared:Genre)-[:HAS_GENRE]-(m2:Movie)
  WHERE m1.mid IN $projection_ids
    AND m2.mid IN $projection_ids
    AND id(m1) < id(m2)
  WITH m1, m2, count(DISTINCT shared) AS overlap
  WITH m1, m2, 0.4 * toFloat(CASE WHEN overlap > 2 THEN 2 ELSE overlap END) AS weight
  WHERE weight > 0
  RETURN id(m1) AS source, id(m2) AS target, weight
  UNION ALL
  MATCH (m1:Movie)-[:HAS_GENRE]-(shared:Genre)-[:HAS_GENRE]-(m2:Movie)
  WHERE m1.mid IN $projection_ids
    AND m2.mid IN $projection_ids
    AND id(m1) < id(m2)
  WITH m1, m2, count(DISTINCT shared) AS overlap
  WITH m1, m2, 0.4 * toFloat(CASE WHEN overlap > 2 THEN 2 ELSE overlap END) AS weight
  WHERE weight > 0
  RETURN id(m2) AS source, id(m1) AS target, weight
  ',
  {
    validateRelationships: false,
    parameters: {
      projection_ids: $projection_ids
    }
  }
)
YIELD graphName
RETURN graphName
"""

PROJECT_FALLBACK_QUERY = """
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

WEIGHTED_PPR_QUERY = """
MATCH (m:Movie)
WHERE m.mid IN $seed_ids
WITH collect(m) AS source_nodes
CALL gds.pageRank.stream($graph_name, {
  sourceNodes: source_nodes,
  relationshipWeightProperty: 'weight',
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

FALLBACK_PPR_QUERY = """
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


def _ensure_projection(
    session,
    graph_name: str,
    project_query: str,
    timeout_ms: int | None = None,
):
    exists_records = run_query(
        session,
        GRAPH_EXISTS_QUERY,
        timeout_ms=timeout_ms,
        graph_name=graph_name,
    )
    if exists_records and exists_records[0]["exists"]:
        return

    run_query(
        session,
        project_query,
        timeout_ms=max(timeout_ms or 0, 12000),
        graph_name=graph_name,
    )


def _drop_projection(session, graph_name: str, timeout_ms: int | None = None):
    run_query(
        session,
        DROP_GRAPH_QUERY,
        timeout_ms=timeout_ms,
        graph_name=graph_name,
    )


def _format_ppr_reasons(
    base_reason: str,
    metadata_reasons: List[str] | None = None,
) -> List[str]:
    if metadata_reasons:
        return [f"{base_reason}，{metadata_reasons[0]}"]
    return [base_reason]


def _rerank_ppr_records(
    driver,
    seed_ids: List[str],
    records,
    timeout_ms: int | None,
    base_reason: str,
) -> List[Dict[str, Any]]:
    if not records:
        return []

    candidate_ids = [record["movie_id"] for record in records]
    feature_map = fetch_movie_feature_map(
        driver,
        seed_ids + candidate_ids,
        timeout_ms=timeout_ms,
    )
    seed_profile = build_seed_profile(feature_map, seed_ids)
    max_score = max(float(record["ppr_score"]) for record in records) or 1.0

    reranked = []
    for record in records:
        movie_id = record["movie_id"]
        normalized_graph_score = float(record["ppr_score"]) / max_score
        metadata_bonus, metadata_reasons = score_metadata_alignment(
            feature_map.get(movie_id),
            seed_profile,
        )
        reranked.append({
            "movie_id": movie_id,
            "title": record.get("title", ""),
            "score": 0.9 * normalized_graph_score + 0.55 * metadata_bonus,
            "reasons": _format_ppr_reasons(base_reason, metadata_reasons),
            "source": "graph_ppr",
        })

    reranked.sort(key=lambda item: (-item["score"], item["movie_id"]))
    return reranked


def _get_graph_ppr_recommendations_sync(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    del exclude_mock_users

    seed_ids = dedupe_preserve_order(seed_movie_ids)
    if not seed_ids:
        return []

    seen_ids = dedupe_preserve_order(seen_movie_ids)
    driver = Neo4jConnection.get_driver()
    candidate_limit = min(max(limit * 4, 120), 180)
    local_graph_name = LOCAL_GRAPH_NAME_TEMPLATE.format(user_id=user_id)

    with driver.session() as session:
        try:
            candidate_records = run_query(
                session,
                LOCAL_CANDIDATE_QUERY,
                timeout_ms=timeout_ms,
                seed_ids=seed_ids,
                seen_movie_ids=seen_ids,
                limit=candidate_limit,
            )
            candidate_ids = [record["movie_id"] for record in candidate_records]
            projection_ids = dedupe_preserve_order(seed_ids + candidate_ids)
            if not candidate_ids:
                return []

            _drop_projection(
                session,
                local_graph_name,
                timeout_ms=timeout_ms,
            )
            run_query(
                session,
                PROJECT_LOCAL_MOVIE_QUERY,
                timeout_ms=max(timeout_ms or 0, 6000),
                graph_name=local_graph_name,
                projection_ids=projection_ids,
            )
            records = run_query(
                session,
                WEIGHTED_PPR_QUERY,
                timeout_ms=timeout_ms,
                graph_name=local_graph_name,
                seed_ids=seed_ids,
                seen_movie_ids=seen_ids,
                damping_factor=0.76,
                max_iterations=30,
                limit=candidate_limit,
            )
            return _rerank_ppr_records(
                driver,
                seed_ids,
                records,
                timeout_ms=timeout_ms,
                base_reason="通过种子电影周边的导演、演员与类型局部图游走发现",
            )[:limit]
        except Exception as exc:
            logger.warning("局部电影投影 PPR 执行失败，回退异构图版本: %s", exc)
        finally:
            try:
                _drop_projection(
                    session,
                    local_graph_name,
                    timeout_ms=timeout_ms,
                )
            except Exception:
                logger.debug("局部 PPR 图释放失败: %s", local_graph_name, exc_info=True)

        try:
            _ensure_projection(
                session,
                FALLBACK_GRAPH_NAME,
                PROJECT_FALLBACK_QUERY,
                timeout_ms=timeout_ms,
            )
            records = run_query(
                session,
                FALLBACK_PPR_QUERY,
                timeout_ms=timeout_ms,
                graph_name=FALLBACK_GRAPH_NAME,
                seed_ids=seed_ids,
                seen_movie_ids=seen_ids,
                damping_factor=0.7,
                max_iterations=25,
                limit=candidate_limit,
            )
        except Exception as exc:
            logger.warning("Neo4j GDS PPR 执行失败，已自动降级: %s", exc)
            return []

    return _rerank_ppr_records(
        driver,
        seed_ids,
        records,
        timeout_ms=timeout_ms,
        base_reason="通过图谱随机游走发现的隐性关联",
    )[:limit]


async def get_graph_ppr_recommendations(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    """
    基于 Neo4j GDS 的 Personalized PageRank，在种子电影局部子图中做稀疏图游走。
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
