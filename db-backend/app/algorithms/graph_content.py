"""
图原生内容推荐算法 (Graph-Content-Based)
"""
import asyncio
from typing import Any, Dict, List

from app.algorithms.common import dedupe_preserve_order, run_query
from app.db.neo4j import Neo4jConnection

DEFAULT_TIMEOUT_MS = 800
RELATION_REASON_LABELS = {
    "DIRECTED": "共享导演",
    "ACTED_IN": "共享演员",
    "HAS_GENRE": "共享类型",
}

CONTENT_QUERY = """
MATCH (source:Movie)-[source_rel:DIRECTED|ACTED_IN|HAS_GENRE]-(shared_node)-[target_rel:DIRECTED|ACTED_IN|HAS_GENRE]-(target:Movie)
WHERE source.mid IN $seed_ids
  AND NOT target.mid IN $seed_ids
  AND NOT target.mid IN $seen_movie_ids
  AND type(source_rel) = type(target_rel)
WITH target, shared_node, type(source_rel) AS rel_type
CALL {
  WITH shared_node
  MATCH (shared_node)--(linked_movie:Movie)
  RETURN count(DISTINCT linked_movie) AS shared_frequency
}
WITH target, rel_type, shared_node, shared_frequency,
     CASE rel_type
       WHEN 'DIRECTED' THEN 3.0
       WHEN 'ACTED_IN' THEN 1.5
       ELSE 1.0
     END / log10(toFloat(shared_frequency) + 10.0) AS weighted_score
ORDER BY target.mid, weighted_score DESC
WITH target,
     sum(weighted_score) AS content_score,
     collect(DISTINCT {
       rel_type: rel_type,
       name: coalesce(shared_node.name, shared_node.title)
     }) AS shared_reasons
RETURN target.mid AS movie_id,
       target.title AS title,
       content_score,
       shared_reasons
ORDER BY content_score DESC, movie_id ASC
LIMIT $limit
"""


def _format_content_reasons(reason_items: List[Dict[str, str]]) -> List[str]:
    if not reason_items:
        return []

    fragments = []
    for item in reason_items[:3]:
        rel_type = item.get("rel_type", "")
        name = item.get("name", "")
        label = RELATION_REASON_LABELS.get(rel_type, "共享特征")
        if name:
            fragments.append(f"{label} {name}")

    if not fragments:
        return []

    reason_text = "，".join(fragments)
    if len(reason_items) > 3:
        reason_text += f" 等 {len(reason_items)} 个图谱共性"
    return [reason_text]


def _get_graph_content_recommendations_sync(
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

    with driver.session() as session:
        records = run_query(
            session,
            CONTENT_QUERY,
            timeout_ms=timeout_ms,
            seed_ids=seed_ids,
            seen_movie_ids=seen_ids,
            limit=limit,
        )

    results = []
    for record in records:
        results.append({
            "movie_id": record["movie_id"],
            "title": record.get("title", ""),
            "score": float(record["content_score"]),
            "reasons": _format_content_reasons(record.get("shared_reasons", [])),
            "source": "graph_content",
        })

    return results


async def get_graph_content_recommendations(
    user_id: int,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    """
    通过知识图谱中导演、演员、类型的共享路径做内容相似推荐。
    """
    return await asyncio.to_thread(
        _get_graph_content_recommendations_sync,
        user_id,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )
