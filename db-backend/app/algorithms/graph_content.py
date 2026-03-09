"""
图原生内容推荐算法 (Graph-Content-Based)
"""
import asyncio
import logging
from typing import Any, Dict, List

from app.algorithms.common import (
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    top_weighted_items,
    run_query,
    score_movie_against_user_profile,
)
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 800
CONTENT_BRANCH_CANDIDATE_MAX = 100
CONTENT_GENRE_FEATURE_LIMIT = 6
CONTENT_DIRECTOR_FEATURE_LIMIT = 4
CONTENT_ACTOR_FEATURE_LIMIT = 6
GENERIC_CONTENT_GENRES = {
    "剧情",
    "喜剧",
    "动作",
    "爱情",
    "动画",
    "家庭",
    "短片",
    "纪录片",
}

CONTENT_QUERY = """
WITH $seen_movie_ids AS seen_movie_ids,
     $genre_names AS genre_names,
     $director_ids AS director_ids,
     $actor_ids AS actor_ids
CALL {
    WITH seen_movie_ids, genre_names, director_ids, actor_ids
    UNWIND genre_names AS genre_name
    MATCH (g:Genre {name: genre_name})<-[:HAS_GENRE]-(target:Movie)
    WHERE NOT target.mid IN seen_movie_ids
    WITH target, collect(DISTINCT genre_name) AS matched_genres
    ORDER BY size(matched_genres) DESC,
             coalesce(target.rating, 0.0) DESC,
             target.mid ASC
    LIMIT $branch_limit
    RETURN target.mid AS movie_id,
           coalesce(target.title, target.name) AS title,
           matched_genres,
           [] AS matched_directors,
           [] AS matched_actors
    UNION ALL
    WITH seen_movie_ids, genre_names, director_ids, actor_ids
    UNWIND director_ids AS director_id
    MATCH (director:Person {pid: director_id})-[:DIRECTED]->(target:Movie)
    WHERE NOT target.mid IN seen_movie_ids
    WITH target, collect(DISTINCT {
        pid: director.pid,
        name: coalesce(director.name_zh, director.name)
    }) AS matched_directors
    ORDER BY size(matched_directors) DESC,
             coalesce(target.rating, 0.0) DESC,
             target.mid ASC
    LIMIT $branch_limit
    RETURN target.mid AS movie_id,
           coalesce(target.title, target.name) AS title,
           [] AS matched_genres,
           matched_directors,
           [] AS matched_actors
    UNION ALL
    WITH seen_movie_ids, genre_names, director_ids, actor_ids
    UNWIND actor_ids AS actor_id
    MATCH (actor:Person {pid: actor_id})-[:ACTED_IN]->(target:Movie)
    WHERE NOT target.mid IN seen_movie_ids
    WITH target, collect(DISTINCT {
        pid: actor.pid,
        name: coalesce(actor.name_zh, actor.name)
    })[..10] AS matched_actors
    ORDER BY size(matched_actors) DESC,
             coalesce(target.rating, 0.0) DESC,
             target.mid ASC
    LIMIT $branch_limit
    RETURN target.mid AS movie_id,
           coalesce(target.title, target.name) AS title,
           [] AS matched_genres,
           [] AS matched_directors,
           matched_actors
}
WITH movie_id,
     title,
     reduce(flattened = [], items IN collect(matched_genres) | flattened + items) AS raw_genres,
     reduce(flattened = [], items IN collect(matched_directors) | flattened + items) AS raw_directors,
     reduce(flattened = [], items IN collect(matched_actors) | flattened + items) AS raw_actors
WITH movie_id,
     title,
     reduce(unique = [], genre IN raw_genres |
        CASE
            WHEN genre IS NULL OR genre IN unique THEN unique
            ELSE unique + genre
        END
     ) AS matched_genres,
     reduce(unique = [], director IN raw_directors |
        CASE
            WHEN director.pid IS NULL OR any(item IN unique WHERE item.pid = director.pid) THEN unique
            ELSE unique + director
        END
     ) AS matched_directors,
     reduce(unique = [], actor IN raw_actors |
        CASE
            WHEN actor.pid IS NULL OR any(item IN unique WHERE item.pid = actor.pid) THEN unique
            ELSE unique + actor
        END
     )[..10] AS matched_actors
WHERE size(matched_genres) + size(matched_directors) + size(matched_actors) > 0
RETURN movie_id,
       title,
       matched_genres,
       matched_directors,
       matched_actors
ORDER BY size(matched_directors) DESC,
         size(matched_genres) DESC,
         size(matched_actors) DESC,
         movie_id ASC
LIMIT $limit
"""


def _normalize_content_recall_candidates(
    records,
    user_profile: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    if not records:
        return []

    scored_records = []
    for record in records:
        base_score = (
            _base_match_score(record, user_profile)
            if user_profile
            else float(
                len(record.get("matched_genres") or [])
                + len(record.get("matched_directors") or [])
                + len(record.get("matched_actors") or [])
            )
        )
        scored_records.append((record, base_score))

    scores = [score for _, score in scored_records]
    min_score = min(scores)
    max_score = max(scores)
    scale = max(max_score - min_score, 1e-8)

    normalized = []
    for record, raw_score in scored_records:
        normalized_score = (raw_score - min_score) / scale if max_score > min_score else 1.0
        normalized.append({
            "movie_id": record["movie_id"],
            "title": record.get("title", ""),
            "score": normalized_score,
            "recall_score": normalized_score,
            "reasons": _format_content_reasons(
                record.get("matched_genres") or [],
                record.get("matched_directors") or [],
                record.get("matched_actors") or [],
                [],
            ),
            "negative_signals": [],
            "source": "graph_content",
            "source_algorithms": ["graph_content"],
        })
    normalized.sort(key=lambda item: (-item["recall_score"], item["movie_id"]))
    return normalized


def _resolve_feature_context(
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
) -> Dict[str, List[str]]:
    if not user_profile:
        seed_ids = dedupe_preserve_order(seed_movie_ids)
        return {
            "genre_names": [],
            "director_ids": [],
            "actor_ids": [],
            "context_movie_ids": seed_ids,
        }

    positive_features = user_profile.get("positive_features", {})
    ordered_genres = top_weighted_items(positive_features.get("genres", {}), 10)
    prioritized_genres = (
        [genre for genre in ordered_genres if genre not in GENERIC_CONTENT_GENRES]
        + [genre for genre in ordered_genres if genre in GENERIC_CONTENT_GENRES]
    )[:CONTENT_GENRE_FEATURE_LIMIT]
    return {
        "genre_names": prioritized_genres,
        "director_ids": top_weighted_items(
            positive_features.get("directors", {}),
            CONTENT_DIRECTOR_FEATURE_LIMIT,
        ),
        "actor_ids": top_weighted_items(
            positive_features.get("actors", {}),
            CONTENT_ACTOR_FEATURE_LIMIT,
        ),
        "context_movie_ids": dedupe_preserve_order(
            user_profile.get("context_movie_ids")
            or user_profile.get("positive_movie_ids")
            or [],
        ),
    }


def _format_content_reasons(
    matched_genres: List[str],
    matched_directors: List[Dict[str, Any]],
    matched_actors: List[Dict[str, Any]],
    profile_reasons: List[str],
) -> List[str]:
    reasons = []
    if matched_directors:
        reasons.append(
            "命中偏好导演 " + " / ".join(
                item["name"]
                for item in matched_directors[:2]
                if item.get("name")
            ),
        )
    if matched_genres:
        reasons.append("命中偏好类型 " + " / ".join(matched_genres[:2]))
    if not reasons and matched_actors:
        reasons.append(
            "命中偏好演员 " + " / ".join(
                item["name"]
                for item in matched_actors[:2]
                if item.get("name")
            ),
        )
    reasons.extend(profile_reasons[:1])
    deduped = []
    seen = set()
    for reason in reasons:
        if not reason or reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped[:3]


def _base_match_score(
    record: Dict[str, Any],
    user_profile: Dict[str, Any],
) -> float:
    positive_features = user_profile.get("positive_features", {})
    matched_genres = record.get("matched_genres") or []
    matched_directors = record.get("matched_directors") or []
    matched_actors = record.get("matched_actors") or []

    genre_score = sum(
        positive_features.get("genres", {}).get(name, 0.0)
        for name in matched_genres[:4]
    ) * 0.18
    director_score = sum(
        positive_features.get("directors", {}).get(item.get("pid"), 0.0)
        for item in matched_directors[:3]
        if item.get("pid")
    ) * 0.24
    actor_score = sum(
        positive_features.get("actors", {}).get(item.get("pid"), 0.0)
        for item in matched_actors[:5]
        if item.get("pid")
    ) * 0.08
    return genre_score + director_score + actor_score


def _rerank_content_records(
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

    reranked = []
    for record in records:
        movie_id = record["movie_id"]
        profile_score, profile_reasons, negative_signals = (
            score_movie_against_user_profile(
                feature_map.get(movie_id),
                user_profile,
            )
            if user_profile
            else (0.0, [], [])
        )
        base_score = (
            _base_match_score(record, user_profile)
            if user_profile
            else float(
                len(record.get("matched_genres") or [])
                + len(record.get("matched_directors") or [])
                + len(record.get("matched_actors") or [])
            )
        )
        reranked.append({
            "movie_id": movie_id,
            "title": record.get("title", ""),
            "score": base_score + 0.72 * profile_score,
            "reasons": _format_content_reasons(
                record.get("matched_genres") or [],
                record.get("matched_directors") or [],
                record.get("matched_actors") or [],
                profile_reasons,
            ),
            "negative_signals": negative_signals[:2],
            "source": "graph_content",
        })

    reranked.sort(key=lambda item: (-item["score"], item["movie_id"]))
    return reranked


def _fetch_graph_content_candidate_records(
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
):
    feature_context = _resolve_feature_context(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
    )
    if (
        not feature_context["genre_names"]
        and not feature_context["director_ids"]
        and not feature_context["actor_ids"]
    ):
        return []

    seen_ids = dedupe_preserve_order(seen_movie_ids)
    driver = Neo4jConnection.get_driver()
    branch_limit = min(max(limit, 40), CONTENT_BRANCH_CANDIDATE_MAX)

    with driver.session() as session:
        try:
            return run_query(
                session,
                CONTENT_QUERY,
                timeout_ms=timeout_ms,
                seen_movie_ids=seen_ids,
                genre_names=feature_context["genre_names"],
                director_ids=feature_context["director_ids"],
                actor_ids=feature_context["actor_ids"],
                branch_limit=branch_limit,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("图内容推荐执行失败，已自动降级: %s", exc)
            return []


def _get_graph_content_recommendations_sync(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    del user_id, exclude_mock_users
    candidate_limit = min(max(limit * 6, 120), 220)
    records = _fetch_graph_content_candidate_records(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_movie_ids,
        limit=candidate_limit,
        timeout_ms=timeout_ms,
    )
    if not records:
        return []
    driver = Neo4jConnection.get_driver()

    return _rerank_content_records(
        driver,
        user_profile,
        records,
        timeout_ms=timeout_ms,
    )[:limit]


def _get_graph_content_recall_candidates_sync(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    del user_id, exclude_mock_users
    records = _fetch_graph_content_candidate_records(
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_movie_ids,
        limit=limit,
        timeout_ms=timeout_ms,
    )
    return _normalize_content_recall_candidates(records, user_profile=user_profile)[:limit]


async def get_graph_content_recommendations(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    """
    根据用户画像在知识图谱中的导演、演员、类型特征进行内容推荐。
    """
    return await asyncio.to_thread(
        _get_graph_content_recommendations_sync,
        user_id,
        user_profile,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )


async def get_graph_content_recall_candidates(
    user_id: int,
    user_profile: Dict[str, Any] | None = None,
    seed_movie_ids: List[str] | None = None,
    seen_movie_ids: List[str] | None = None,
    exclude_mock_users: bool = True,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(
        _get_graph_content_recall_candidates_sync,
        user_id,
        user_profile,
        seed_movie_ids,
        seen_movie_ids,
        exclude_mock_users,
        limit,
        timeout_ms,
    )
