"""
图原生内容推荐算法 (Graph-Content-Based)
"""
import asyncio
import logging
from typing import Any, Dict, List

from app.algorithms.common import dedupe_preserve_order, run_query
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

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
WITH target,
     type(source_rel) AS rel_type,
     count(DISTINCT shared_node) AS shared_node_count,
     count(DISTINCT source) AS shared_seed_count,
     collect(DISTINCT coalesce(shared_node.name, shared_node.title))[..3] AS reason_names
WITH target,
     rel_type,
     shared_node_count,
     shared_seed_count,
     reason_names,
     CASE rel_type
       WHEN 'DIRECTED' THEN 3
       WHEN 'ACTED_IN' THEN 2
       ELSE 1
     END AS reason_priority
ORDER BY target.mid, reason_priority DESC, shared_seed_count DESC, shared_node_count DESC
WITH target,
     collect({
       rel_type: rel_type,
       reason_names: reason_names,
       shared_node_count: shared_node_count,
       shared_seed_count: shared_seed_count
     }) AS relation_groups
WITH target,
     relation_groups,
     reduce(score = 0.0, group IN relation_groups |
       score +
       CASE group.rel_type
         WHEN 'DIRECTED' THEN 4.0 * CASE WHEN group.shared_node_count > 0 THEN 1.0 ELSE 0.0 END
         WHEN 'ACTED_IN' THEN 1.4 * toFloat(CASE WHEN group.shared_node_count > 3 THEN 3 ELSE group.shared_node_count END)
         ELSE 0.8 * toFloat(CASE WHEN group.shared_node_count > 2 THEN 2 ELSE group.shared_node_count END)
       END +
       0.7 * toFloat(CASE WHEN group.shared_seed_count > 1 THEN group.shared_seed_count - 1 ELSE 0 END)
     ) AS base_score,
     size(relation_groups) AS relation_diversity,
     reduce(seed_cov = 0, group IN relation_groups | seed_cov + group.shared_seed_count) AS seed_overlap_total
RETURN target.mid AS movie_id,
       target.title AS title,
       base_score + 0.9 * toFloat(relation_diversity) + 0.12 * toFloat(seed_overlap_total) AS content_score,
       relation_groups AS shared_reasons
ORDER BY content_score DESC, movie_id ASC
LIMIT $limit
"""


def _format_content_reasons(reason_items: List[Dict[str, Any]]) -> List[str]:
    if not reason_items:
        return []

    fragments = []
    for item in reason_items[:3]:
        rel_type = item.get("rel_type", "")
        names = [name for name in item.get("reason_names", []) if name]
        label = RELATION_REASON_LABELS.get(rel_type, "共享特征")
        if names:
            fragments.append(f"{label} {' / '.join(names[:2])}")

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
        try:
            records = run_query(
                session,
                CONTENT_QUERY,
                timeout_ms=timeout_ms,
                seed_ids=seed_ids,
                seen_movie_ids=seen_ids,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("图内容推荐执行失败，已自动降级: %s", exc)
            return []

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
