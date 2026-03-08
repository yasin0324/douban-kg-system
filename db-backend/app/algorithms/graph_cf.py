"""
基于图拓扑的协同过滤 (Graph-Collaborative-Filtering)
"""
import asyncio
from typing import Any, Dict, List

from app.algorithms.common import (
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    run_query,
    score_movie_against_user_profile,
)
from app.db.neo4j import Neo4jConnection

POSITIVE_RATING = 3.5
SHRINKAGE = 2.0
NEIGHBOR_LIMIT = 40
DEFAULT_TIMEOUT_MS = 800

CF_QUERY = """
WITH $positive_movie_ids AS positive_movie_ids
UNWIND positive_movie_ids AS positive_movie_id
MATCH (:Movie {mid: positive_movie_id})<-[shared_rel:RATED]-(neighbor:User)
WHERE neighbor.id <> $user_id
  AND shared_rel.rating >= $positive_rating
  AND (NOT $exclude_mock_users OR coalesce(neighbor.is_mock, false) = false)
WITH neighbor,
     count(DISTINCT positive_movie_id) AS positive_overlap,
     avg(shared_rel.rating) AS shared_positive_avg
WHERE positive_overlap >= $min_overlap
OPTIONAL MATCH (neighbor)-[conflict_rel:RATED]->(negative_movie:Movie)
WHERE negative_movie.mid IN $negative_movie_ids
  AND conflict_rel.rating >= $positive_rating
WITH neighbor,
     positive_overlap,
     shared_positive_avg,
     count(DISTINCT negative_movie) AS negative_conflict_count
MATCH (neighbor)-[liked_rel:RATED]->(:Movie)
WHERE liked_rel.rating >= $positive_rating
WITH neighbor,
     positive_overlap,
     shared_positive_avg,
     negative_conflict_count,
     count(liked_rel) AS neighbor_positive_count
WITH neighbor,
     positive_overlap,
     shared_positive_avg,
     negative_conflict_count,
     (
       (toFloat(positive_overlap) / sqrt(toFloat($positive_count) * toFloat(neighbor_positive_count))) *
       (toFloat(positive_overlap) / (toFloat(positive_overlap) + $shrinkage))
     ) * (1.0 + 0.04 * (shared_positive_avg - $positive_rating)) -
     (0.10 * toFloat(negative_conflict_count)) AS similarity
WHERE similarity > 0
ORDER BY similarity DESC
LIMIT $neighbor_limit
MATCH (neighbor)-[candidate_rel:RATED]->(candidate:Movie)
WHERE candidate_rel.rating >= $positive_rating
  AND NOT candidate.mid IN $seen_movie_ids
RETURN candidate.mid AS movie_id,
       candidate.title AS title,
       sum(similarity * (candidate_rel.rating - 2.5)) AS cf_score,
       count(DISTINCT neighbor) AS similar_user_count,
       max(similarity) AS strongest_similarity,
       avg(candidate_rel.rating) AS avg_neighbor_rating
ORDER BY cf_score DESC, similar_user_count DESC, movie_id ASC
LIMIT $limit
"""


def _format_cf_base_reason(record: Dict[str, Any]) -> str:
    similar_user_count = int(record["similar_user_count"] or 0)
    strongest_similarity = float(record["strongest_similarity"] or 0.0)
    base_reason = f"{similar_user_count} 位相似用户也明显偏好这部电影"
    if strongest_similarity > 0.2:
        base_reason += f"，近邻强度 {strongest_similarity:.2f}"
    return base_reason


def _normalize_recall_candidates(
    records,
    score_key: str,
    source: str,
) -> List[Dict[str, Any]]:
    if not records:
        return []

    scores = [float(record.get(score_key) or 0.0) for record in records]
    min_score = min(scores)
    max_score = max(scores)
    scale = max(max_score - min_score, 1e-8)

    normalized = []
    for record in records:
        movie_id = record["movie_id"]
        raw_score = float(record.get(score_key) or 0.0)
        normalized_score = (raw_score - min_score) / scale if max_score > min_score else 1.0
        normalized.append({
            "movie_id": movie_id,
            "title": record.get("title", ""),
            "score": normalized_score,
            "recall_score": normalized_score,
            "reasons": [_format_cf_base_reason(record)],
            "negative_signals": [],
            "source": source,
            "source_algorithms": [source],
        })
    normalized.sort(key=lambda item: (-item["recall_score"], item["movie_id"]))
    return normalized


def _resolve_profile_context(
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
) -> tuple[List[str], List[str]]:
    if user_profile:
        positive_movie_ids = dedupe_preserve_order(
            user_profile.get("context_movie_ids")
            or user_profile.get("positive_movie_ids")
            or [],
        )
        negative_movie_ids = dedupe_preserve_order(
            user_profile.get("negative_movie_ids") or [],
        )
        return positive_movie_ids[:24], negative_movie_ids[:12]

    return dedupe_preserve_order(seed_movie_ids), []


def _fetch_graph_cf_candidate_records(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
):
    positive_movie_ids, negative_movie_ids = _resolve_profile_context(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
    )
    if not positive_movie_ids:
        return []

    seen_ids = dedupe_preserve_order(seen_movie_ids)
    min_overlap = 1 if len(positive_movie_ids) < 4 else 2
    driver = Neo4jConnection.get_driver()

    with driver.session() as session:
        return run_query(
            session,
            CF_QUERY,
            timeout_ms=timeout_ms,
            user_id=user_id,
            positive_movie_ids=positive_movie_ids,
            negative_movie_ids=negative_movie_ids,
            positive_count=max(len(positive_movie_ids), 1),
            seen_movie_ids=seen_ids,
            exclude_mock_users=exclude_mock_users,
            positive_rating=POSITIVE_RATING,
            min_overlap=min_overlap,
            shrinkage=SHRINKAGE,
            neighbor_limit=NEIGHBOR_LIMIT,
            limit=limit,
        )


def _rerank_cf_records(
    driver,
    user_profile: Dict[str, Any] | None,
    records,
    timeout_ms: int | None,
) -> List[Dict[str, Any]]:
    if not records:
        return []

    candidate_ids = [record["movie_id"] for record in records]
    feature_map = fetch_movie_graph_profile_map(
        driver,
        candidate_ids,
        timeout_ms=timeout_ms,
        )
    max_score = max(float(record["cf_score"]) for record in records) or 1.0

    reranked = []
    for record in records:
        movie_id = record["movie_id"]
        base_score = float(record["cf_score"]) / max_score
        profile_score, profile_reasons, negative_signals = (
            score_movie_against_user_profile(
                feature_map.get(movie_id),
                user_profile,
            )
            if user_profile
            else (0.0, [], [])
        )
        reasons = [_format_cf_base_reason(record), *profile_reasons[:1]]
        reranked.append({
            "movie_id": movie_id,
            "title": record.get("title", ""),
            "score": 1.05 * base_score + 0.40 * profile_score,
            "reasons": reasons[:3],
            "negative_signals": negative_signals[:2],
            "source": "graph_cf",
        })

    reranked.sort(key=lambda item: (-item["score"], item["movie_id"]))
    return reranked


def _get_graph_cf_recommendations_sync(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    candidate_limit = min(max(limit * 4, 80), 180)
    records = _fetch_graph_cf_candidate_records(
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_movie_ids,
        exclude_mock_users=exclude_mock_users,
        limit=candidate_limit,
        timeout_ms=timeout_ms,
    )
    if not records:
        return []
    driver = Neo4jConnection.get_driver()

    return _rerank_cf_records(
        driver,
        user_profile,
        records,
        timeout_ms=timeout_ms,
    )[:limit]


def _get_graph_cf_recall_candidates_sync(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    records = _fetch_graph_cf_candidate_records(
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_movie_ids,
        exclude_mock_users=exclude_mock_users,
        limit=limit,
        timeout_ms=timeout_ms,
    )
    return _normalize_recall_candidates(records, score_key="cf_score", source="graph_cf")[:limit]


async def get_graph_cf_recommendations(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    """
    基于用户画像中的正向电影上下文构建邻域，再用正负反馈做重排。
    """
    return await asyncio.to_thread(
        _get_graph_cf_recommendations_sync,
        user_id,
        user_profile,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )


async def get_graph_cf_recall_candidates(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(
        _get_graph_cf_recall_candidates_sync,
        user_id,
        user_profile,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )
