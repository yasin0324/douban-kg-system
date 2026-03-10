"""
CFKG inference helpers and API-facing recommendation entry.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import time
from typing import Any

from app.algorithms.common import (
    build_weighted_user_profile,
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    score_movie_against_user_profile,
)
from app.algorithms.cfkg.artifacts import resolve_model_path
from app.algorithms.cfkg.model import TransEModel, require_torch
from app.algorithms.cfkg.reranker import (
    build_reranker_feature_map,
    load_reranker_bundle,
    score_reranker_features,
)
from app.algorithms.graph_cf import get_graph_cf_recall_candidates
from app.algorithms.graph_content import get_graph_content_recall_candidates
from app.algorithms.item_cf import get_itemcf_recommendations
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT_MS = 800
DEFAULT_RECALL_TARGET_MIN = 120
DEFAULT_RECALL_TARGET_MAX = 160
CONTENT_RECALL_TIMEOUT_MS = 600
CONTENT_RECALL_MIN_GAP = 12
CF_RECALL_WEIGHT = 0.50
CFKG_RERANK_WEIGHT = 0.35
PROFILE_WEIGHT = 0.15
_MODEL_CACHE: dict[str, Any] = {
    "path": None,
    "mtime": None,
    "bundle": None,
}


def clear_model_cache() -> None:
    _MODEL_CACHE.update({
        "path": None,
        "mtime": None,
        "bundle": None,
    })


def _load_model_bundle(model_path: str | Path | None = None) -> dict[str, Any] | None:
    torch_module, _, _ = require_torch()
    resolved_path = resolve_model_path(model_path)
    if not resolved_path.exists():
        return None

    current_mtime = resolved_path.stat().st_mtime
    if (
        _MODEL_CACHE["path"] == str(resolved_path)
        and _MODEL_CACHE["mtime"] == current_mtime
        and _MODEL_CACHE["bundle"] is not None
    ):
        return _MODEL_CACHE["bundle"]

    artifact = torch_module.load(resolved_path, map_location="cpu")
    config = artifact["config"]
    model = TransEModel(
        entity_count=int(config["entity_count"]),
        relation_count=int(config["relation_count"]),
        embedding_dim=int(config["embedding_dim"]),
    )
    model.load_state_dict(artifact["model_state"])
    model.eval()

    bundle = {
        "path": str(resolved_path),
        "model": model,
        "config": config,
        "entity_key_to_id": artifact["entity_key_to_id"],
        "entity_id_to_key": {int(key): value for key, value in artifact["entity_id_to_key"].items()},
        "entity_id_to_type": {int(key): value for key, value in artifact["entity_id_to_type"].items()},
        "entity_id_to_label": {int(key): value for key, value in artifact["entity_id_to_label"].items()},
        "relation_name_to_id": artifact["relation_name_to_id"],
        "relation_id_to_name": {int(key): value for key, value in artifact["relation_id_to_name"].items()},
        "movie_entity_ids": [int(item) for item in artifact["movie_entity_ids"]],
        "movie_entity_id_to_mid": {
            int(key): value for key, value in artifact["movie_entity_id_to_mid"].items()
        },
        "user_entity_to_user_id": {
            int(key): int(value) for key, value in artifact["user_entity_to_user_id"].items()
        },
        "metrics": artifact.get("metrics", {}),
    }
    _MODEL_CACHE.update({
        "path": str(resolved_path),
        "mtime": current_mtime,
        "bundle": bundle,
    })
    return bundle


async def prewarm_cfkg_model(model_path: str | Path | None = None) -> bool:
    try:
        bundle = await asyncio.to_thread(_load_model_bundle, model_path)
    except RuntimeError as exc:
        logger.warning("CFKG 模型预热失败: %s", exc)
        return False
    except Exception:
        logger.warning("CFKG 模型预热失败", exc_info=True)
        return False

    resolved_path = resolve_model_path(model_path)
    if bundle is None:
        logger.warning("CFKG 模型文件不存在，跳过预热: %s", resolved_path)
        return False

    reranker_bundle = load_reranker_bundle()
    if reranker_bundle is not None:
        logger.info("CFKG reranker 预热完成: %s", reranker_bundle["path"])
    logger.info("CFKG 模型预热完成: %s", bundle["path"])
    return True


def _normalize_score_map(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}

    scores = list(score_map.values())
    min_score = min(scores)
    max_score = max(scores)
    scale = max(max_score - min_score, 1e-8)
    if max_score == min_score:
        return {movie_id: 1.0 for movie_id in score_map}
    return {
        movie_id: (score - min_score) / scale
        for movie_id, score in score_map.items()
    }


def _build_seed_only_profile(
    seed_movie_ids: list[str] | None,
    timeout_ms: int | None,
) -> dict[str, Any] | None:
    seed_ids = dedupe_preserve_order(seed_movie_ids)
    if not seed_ids:
        return None

    feature_map = fetch_movie_graph_profile_map(
        Neo4jConnection.get_driver(),
        seed_ids,
        timeout_ms=timeout_ms,
    )
    feedback_map = {
        movie_id: {
            "positive_weight": 1.0,
            "negative_weight": 0.0,
            "exploration_weight": 0.0,
        }
        for movie_id in seed_ids
    }
    profile = build_weighted_user_profile(feature_map, feedback_map)
    profile["context_movie_ids"] = seed_ids
    profile["positive_movie_ids"] = seed_ids
    profile["negative_movie_ids"] = []
    profile["hard_exclude_movie_ids"] = []
    return profile


def _normalized_rank_score(index: int, total_count: int) -> float:
    if total_count <= 1:
        return 1.0
    return 1.0 - (index / max(total_count - 1, 1))


def _build_overlap_feature_counts(
    candidate_features: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> dict[str, float]:
    if not candidate_features or not profile:
        return {
            "genre_overlap_count": 0.0,
            "director_overlap_count": 0.0,
            "actor_overlap_count": 0.0,
            "negative_overlap_count": 0.0,
        }

    positive_features = profile.get("positive_features", {})
    negative_features = profile.get("negative_features", {})
    genre_overlap_count = len(
        candidate_features.get("genres", set())
        & set(positive_features.get("genres", {}).keys())
    )
    director_overlap_count = len(
        candidate_features.get("director_ids", set())
        & set(positive_features.get("directors", {}).keys())
    )
    actor_overlap_count = len(
        candidate_features.get("actor_ids", set())
        & set(positive_features.get("actors", {}).keys())
    )
    negative_overlap_count = (
        len(candidate_features.get("genres", set()) & set(negative_features.get("genres", {}).keys()))
        + len(candidate_features.get("director_ids", set()) & set(negative_features.get("directors", {}).keys()))
        + len(candidate_features.get("actor_ids", set()) & set(negative_features.get("actors", {}).keys()))
    )
    return {
        "genre_overlap_count": float(genre_overlap_count),
        "director_overlap_count": float(director_overlap_count),
        "actor_overlap_count": float(actor_overlap_count),
        "negative_overlap_count": float(negative_overlap_count),
    }


def _has_sufficient_content_signal(user_profile: dict[str, Any] | None) -> bool:
    if not user_profile:
        return False

    positive_features = user_profile.get("positive_features", {})
    genres = positive_features.get("genres", {})
    directors = positive_features.get("directors", {})
    actors = positive_features.get("actors", {})
    return len(genres) >= 2 or len(directors) >= 1 or len(actors) >= 2


def _combine_recall_support_scores(scores: list[float]) -> float:
    bounded_scores = [
        min(max(float(score), 0.0), 1.0)
        for score in scores
        if float(score) > 0.0
    ]
    if not bounded_scores:
        return 0.0
    missing_probability = 1.0
    for score in bounded_scores:
        missing_probability *= (1.0 - score)
    return 1.0 - missing_probability


def _merge_recall_candidate_lists(
    *candidate_lists: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    merged_items: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []

    for candidate_list in candidate_lists:
        for item in candidate_list or []:
            movie_id = str(item["movie_id"])
            item_recall_score = float(item.get("recall_score", item.get("score", 0.0)))
            if movie_id not in merged_items:
                merged_items[movie_id] = {
                    **item,
                    "movie_id": movie_id,
                    "recall_score": item_recall_score,
                    "reasons": dedupe_preserve_order(list(item.get("reasons") or []))[:3],
                    "source_algorithms": dedupe_preserve_order(
                        list(item.get("source_algorithms") or [item.get("source", "graph_cf")])
                    ),
                }
                ordered_ids.append(movie_id)
                continue

            merged = merged_items[movie_id]
            merged["recall_score"] = _combine_recall_support_scores(
                [
                    float(merged.get("recall_score", merged.get("score", 0.0))),
                    item_recall_score,
                ]
            )
            merged["score"] = max(
                float(merged.get("score", merged.get("recall_score", 0.0))),
                float(item.get("score", item_recall_score)),
            )
            merged["reasons"] = dedupe_preserve_order(
                list(merged.get("reasons") or []) + list(item.get("reasons") or [])
            )[:3]
            merged["source_algorithms"] = dedupe_preserve_order(
                list(merged.get("source_algorithms") or [])
                + list(item.get("source_algorithms") or [item.get("source", "graph_cf")])
            )

    merged_list = [merged_items[movie_id] for movie_id in ordered_ids]
    if limit is not None:
        return merged_list[:limit]
    return merged_list


def _score_user_candidates(
    bundle: dict[str, Any],
    user_id: int,
    seen_movie_ids: list[str],
    limit: int,
    candidate_movie_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    torch_module, _, _ = require_torch()
    user_key = f"user:{user_id}"
    user_entity_id = bundle["entity_key_to_id"].get(user_key)
    if user_entity_id is None:
        return []

    interact_relation_id = int(bundle["relation_name_to_id"]["interact"])
    seen_set = set(dedupe_preserve_order(seen_movie_ids))
    if candidate_movie_ids is not None:
        allowed_ids = set(dedupe_preserve_order(candidate_movie_ids))
        candidate_pairs = [
            (movie_entity_id, bundle["movie_entity_id_to_mid"][movie_entity_id])
            for movie_entity_id in bundle["movie_entity_ids"]
            if bundle["movie_entity_id_to_mid"][movie_entity_id] in allowed_ids
            and bundle["movie_entity_id_to_mid"][movie_entity_id] not in seen_set
        ]
    else:
        candidate_pairs = [
            (movie_entity_id, bundle["movie_entity_id_to_mid"][movie_entity_id])
            for movie_entity_id in bundle["movie_entity_ids"]
            if bundle["movie_entity_id_to_mid"][movie_entity_id] not in seen_set
        ]
    if not candidate_pairs:
        return []

    candidate_entity_ids = [item[0] for item in candidate_pairs]
    user_tensor = torch_module.full(
        (len(candidate_entity_ids),),
        fill_value=user_entity_id,
        dtype=torch_module.long,
    )
    relation_tensor = torch_module.full(
        (len(candidate_entity_ids),),
        fill_value=interact_relation_id,
        dtype=torch_module.long,
    )
    movie_tensor = torch_module.tensor(candidate_entity_ids, dtype=torch_module.long)

    with torch_module.no_grad():
        scores = bundle["model"].score(user_tensor, relation_tensor, movie_tensor).tolist()

    ranked = sorted(
        (
            {
                "movie_id": movie_mid,
                "title": bundle["entity_id_to_label"].get(movie_entity_id, movie_mid),
                "score": float(score),
                "source": "cfkg",
            }
            for (movie_entity_id, movie_mid), score in zip(candidate_pairs, scores)
        ),
        key=lambda item: (-item["score"], item["movie_id"]),
    )
    return ranked[:limit]


async def _collect_recall_candidates(
    user_id: int,
    user_profile: dict[str, Any] | None,
    seed_movie_ids: list[str] | None,
    seen_movie_ids: list[str],
    limit: int,
    timeout_ms: int | None,
    stage_metrics: dict[str, Any] | None = None,
    conn=None,
) -> list[dict[str, Any]]:
    recall_target = min(max(limit * 6, DEFAULT_RECALL_TARGET_MIN), DEFAULT_RECALL_TARGET_MAX)
    minimum_viable_candidates = max(limit * 2, 40)
    seen_ids = dedupe_preserve_order(seen_movie_ids)
    metrics = stage_metrics if stage_metrics is not None else {}

    cf_started_at = time.perf_counter()
    cf_candidates = await get_graph_cf_recall_candidates(
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_ids,
        exclude_mock_users=True,
        limit=recall_target,
        timeout_ms=max(timeout_ms or DEFAULT_TIMEOUT_MS, 1500),
    )
    metrics["cf_recall_ms"] = (time.perf_counter() - cf_started_at) * 1000
    metrics["cf_candidate_count"] = len(cf_candidates)
    metrics["itemcf_recall_ms"] = 0.0
    metrics["itemcf_candidate_count"] = 0
    itemcf_candidates: list[dict[str, Any]] = []
    if conn is not None:
        itemcf_started_at = time.perf_counter()
        itemcf_candidates = await get_itemcf_recommendations(
            conn=conn,
            user_id=user_id,
            user_profile=user_profile,
            seed_movie_ids=seed_movie_ids,
            seen_movie_ids=seen_ids,
            limit=recall_target,
            timeout_ms=max(timeout_ms or DEFAULT_TIMEOUT_MS, 1200),
        )
        metrics["itemcf_recall_ms"] = (time.perf_counter() - itemcf_started_at) * 1000
        metrics["itemcf_candidate_count"] = len(itemcf_candidates)
    merged_candidates = _merge_recall_candidate_lists(
        cf_candidates,
        itemcf_candidates,
        limit=recall_target,
    )
    metrics["content_triggered"] = False
    metrics["content_recall_ms"] = 0.0
    metrics["content_candidate_count"] = 0
    metrics["content_timed_out"] = False

    if len(merged_candidates) >= minimum_viable_candidates:
        metrics["content_skip_reason"] = "cf_sufficient"
        return merged_candidates[:recall_target]

    if not _has_sufficient_content_signal(user_profile):
        metrics["content_skip_reason"] = "weak_profile"
        return merged_candidates[:recall_target]

    missing_count = max(minimum_viable_candidates - len(merged_candidates), 0)
    if missing_count < CONTENT_RECALL_MIN_GAP:
        metrics["content_skip_reason"] = "small_gap"
        return merged_candidates[:recall_target]

    metrics["content_triggered"] = True
    content_seen_ids = dedupe_preserve_order(
        seen_ids + [item["movie_id"] for item in merged_candidates]
    )
    content_started_at = time.perf_counter()
    content_request_limit = min(missing_count + 20, 80)
    try:
        content_candidates = await get_graph_content_recall_candidates(
            user_id=user_id,
            user_profile=user_profile,
            seed_movie_ids=seed_movie_ids,
            seen_movie_ids=content_seen_ids,
            exclude_mock_users=True,
            limit=content_request_limit,
            timeout_ms=CONTENT_RECALL_TIMEOUT_MS,
        )
    except asyncio.TimeoutError:
        metrics["content_timed_out"] = True
        metrics["content_skip_reason"] = "timeout"
        logger.warning(
            "CFKG content recall timed out user_id=%s missing_count=%s timeout_ms=%s",
            user_id,
            missing_count,
            CONTENT_RECALL_TIMEOUT_MS,
        )
        content_candidates = []
    except Exception:
        metrics["content_skip_reason"] = "error"
        logger.warning("CFKG content recall failed for user_id=%s", user_id, exc_info=True)
        content_candidates = []
    metrics["content_recall_ms"] = (time.perf_counter() - content_started_at) * 1000
    metrics["content_candidate_count"] = len(content_candidates)
    return _merge_recall_candidate_lists(
        merged_candidates,
        content_candidates,
        limit=recall_target,
    )


def _rank_candidate_pool(
    bundle: dict[str, Any],
    user_id: int,
    candidate_items: list[dict[str, Any]],
    seen_movie_ids: list[str],
    user_profile: dict[str, Any] | None,
    seed_movie_ids: list[str] | None,
    timeout_ms: int | None,
    ranking_mode: str,
    limit: int,
    disable_learned_rerank: bool = False,
) -> list[dict[str, Any]]:
    if not candidate_items:
        return []

    candidate_movie_ids = [item["movie_id"] for item in candidate_items]
    cfkg_raw_items = _score_user_candidates(
        bundle=bundle,
        user_id=user_id,
        seen_movie_ids=seen_movie_ids,
        limit=len(candidate_movie_ids),
        candidate_movie_ids=candidate_movie_ids,
    )
    if not cfkg_raw_items:
        return []

    recall_score_map = _normalize_score_map({
        item["movie_id"]: float(item.get("recall_score", item.get("score", 0.0)))
        for item in candidate_items
    })
    cfkg_score_map = _normalize_score_map({
        item["movie_id"]: float(item.get("score") or 0.0)
        for item in cfkg_raw_items
    })
    raw_title_map = {
        item["movie_id"]: item.get("title") or item["movie_id"]
        for item in cfkg_raw_items
    }
    recall_rank_map = {
        item["movie_id"]: index
        for index, item in enumerate(
            sorted(
                candidate_items,
                key=lambda item: (
                    -float(item.get("recall_score", item.get("score", 0.0))),
                    item["movie_id"],
                ),
            )
        )
    }
    cfkg_rank_map = {
        item["movie_id"]: index
        for index, item in enumerate(cfkg_raw_items)
    }
    rank_total_count = max(len(candidate_items), 1)

    effective_profile = user_profile
    if ranking_mode == "pipeline" and effective_profile is None:
        effective_profile = _build_seed_only_profile(
            seed_movie_ids=seed_movie_ids,
            timeout_ms=timeout_ms,
        )

    feature_map = {}
    if ranking_mode == "pipeline" and effective_profile:
        feature_map = fetch_movie_graph_profile_map(
            Neo4jConnection.get_driver(),
            candidate_movie_ids,
            timeout_ms=timeout_ms,
        )

    reranker_bundle = (
        None
        if disable_learned_rerank or ranking_mode != "pipeline"
        else load_reranker_bundle()
    )
    ranked_items = []
    for candidate in candidate_items:
        movie_id = candidate["movie_id"]
        if movie_id not in cfkg_score_map:
            continue

        recall_score = recall_score_map.get(movie_id, 0.0)
        recall_rank_score = _normalized_rank_score(recall_rank_map.get(movie_id, rank_total_count - 1), rank_total_count)
        cfkg_score = cfkg_score_map.get(movie_id, 0.0)
        cfkg_rank_score = _normalized_rank_score(cfkg_rank_map.get(movie_id, rank_total_count - 1), rank_total_count)
        profile_score = 0.0
        profile_reasons: list[str] = []
        negative_signals: list[str] = []
        overlap_features = {
            "genre_overlap_count": 0.0,
            "director_overlap_count": 0.0,
            "actor_overlap_count": 0.0,
            "negative_overlap_count": 0.0,
        }
        if ranking_mode == "pipeline" and effective_profile:
            movie_profile = feature_map.get(movie_id)
            profile_score, profile_reasons, negative_signals = score_movie_against_user_profile(
                movie_profile,
                effective_profile,
            )
            overlap_features = _build_overlap_feature_counts(
                movie_profile,
                effective_profile,
            )

        recall_sources = candidate.get("source_algorithms") or [candidate.get("source", "graph_cf")]
        reranker_features = build_reranker_feature_map(
            recall_score=recall_score,
            recall_rank_score=recall_rank_score,
            cfkg_score=cfkg_score,
            cfkg_rank_score=cfkg_rank_score,
            profile_score=profile_score,
            recall_sources=recall_sources,
            negative_signals=negative_signals,
            genre_overlap_count=overlap_features["genre_overlap_count"],
            director_overlap_count=overlap_features["director_overlap_count"],
            actor_overlap_count=overlap_features["actor_overlap_count"],
            negative_overlap_count=overlap_features["negative_overlap_count"],
        )

        if ranking_mode == "raw":
            final_score = cfkg_score
            reasons = ["CFKG 对第一阶段召回候选完成表示学习打分"]
            score_breakdown = {"cfkg": round(final_score, 6)}
        else:
            reasons = []
            reasons.extend(candidate.get("reasons", [])[:1])
            reasons.append("先由协同过滤召回候选，再由 CFKG 精排")
            reasons.extend(profile_reasons[:1])
            if reranker_bundle is None:
                final_score = (
                    CF_RECALL_WEIGHT * recall_score
                    + CFKG_RERANK_WEIGHT * cfkg_score
                    + PROFILE_WEIGHT * profile_score
                )
                recall_contrib = CF_RECALL_WEIGHT * recall_score
                recall_share = recall_contrib / max(len(recall_sources), 1)
                score_breakdown = {
                    source: round(recall_share, 6)
                    for source in recall_sources
                }
                score_breakdown["cfkg"] = round(CFKG_RERANK_WEIGHT * cfkg_score, 6)
                if profile_score > 0:
                    score_breakdown["profile"] = round(PROFILE_WEIGHT * profile_score, 6)
            else:
                final_score, contribution_map = score_reranker_features(
                    reranker_bundle,
                    reranker_features,
                )
                score_breakdown: dict[str, float] = {}
                recall_contrib = (
                    contribution_map.get("recall_score", 0.0)
                    + contribution_map.get("recall_rank_score", 0.0)
                )
                source_count_contrib = contribution_map.get("source_count", 0.0)
                recall_share = (recall_contrib + source_count_contrib) / max(len(recall_sources), 1)
                if abs(recall_share) > 1e-8:
                    for source in recall_sources:
                        score_breakdown[source] = round(score_breakdown.get(source, 0.0) + recall_share, 6)
                for source, feature_name in (
                    ("graph_cf", "has_cf_source"),
                    ("itemcf", "has_itemcf_source"),
                    ("graph_content", "has_content_source"),
                    ("graph_ppr", "has_ppr_source"),
                ):
                    contribution = contribution_map.get(feature_name, 0.0)
                    if abs(contribution) > 1e-8 and source in recall_sources:
                        score_breakdown[source] = round(score_breakdown.get(source, 0.0) + contribution, 6)
                cfkg_contribution = (
                    contribution_map.get("cfkg_score", 0.0)
                    + contribution_map.get("cfkg_rank_score", 0.0)
                )
                if abs(cfkg_contribution) > 1e-8:
                    score_breakdown["cfkg"] = round(cfkg_contribution, 6)
                profile_contribution = (
                    contribution_map.get("profile_score", 0.0)
                    + contribution_map.get("genre_overlap_count", 0.0)
                    + contribution_map.get("director_overlap_count", 0.0)
                    + contribution_map.get("actor_overlap_count", 0.0)
                    + contribution_map.get("negative_signal_count", 0.0)
                    + contribution_map.get("negative_overlap_count", 0.0)
                )
                if abs(profile_contribution) > 1e-8:
                    score_breakdown["profile"] = round(profile_contribution, 6)

        source_algorithms = dedupe_preserve_order(
            list(candidate.get("source_algorithms") or [candidate.get("source", "graph_cf")]) + ["cfkg"]
        )
        ranked_items.append({
            "movie_id": movie_id,
            "title": candidate.get("title") or raw_title_map.get(movie_id, movie_id),
            "final_score": final_score,
            "score": final_score,
            "reasons": dedupe_preserve_order(reasons)[:3],
            "negative_signals": negative_signals[:2],
            "source": "cfkg",
            "source_algorithms": source_algorithms,
            "score_breakdown": score_breakdown,
            "recall_score": recall_score,
            "recall_rank_score": recall_rank_score,
            "cfkg_score": cfkg_score,
            "cfkg_rank_score": cfkg_rank_score,
            "profile_score": profile_score,
            "genre_overlap_count": overlap_features["genre_overlap_count"],
            "director_overlap_count": overlap_features["director_overlap_count"],
            "actor_overlap_count": overlap_features["actor_overlap_count"],
            "negative_overlap_count": overlap_features["negative_overlap_count"],
        })

    ranked_items.sort(key=lambda item: (-item["final_score"], item["movie_id"]))
    return ranked_items[:limit]


async def get_cfkg_recommendations(
    user_id: int,
    user_profile: dict[str, Any] | None = None,
    seed_movie_ids: list[str] | None = None,
    seen_movie_ids: list[str] | None = None,
    limit: int = 50,
    timeout_ms: int | None = DEFAULT_TIMEOUT_MS,
    model_path: str | Path | None = None,
    disable_profile_rerank: bool = False,
    ranking_mode: str | None = None,
    conn=None,
) -> list[dict[str, Any]]:
    request_started_at = time.perf_counter()
    resolved_mode = ranking_mode or ("raw" if disable_profile_rerank else "pipeline")
    if resolved_mode not in {"raw", "pipeline"}:
        raise ValueError(f"未知 CFKG 排序模式: {resolved_mode}")

    try:
        bundle = await asyncio.to_thread(_load_model_bundle, model_path)
    except RuntimeError as exc:
        logger.warning("CFKG 模型不可用: %s", exc)
        return []

    if bundle is None:
        return []

    seen_ids = dedupe_preserve_order(seen_movie_ids)
    stage_metrics: dict[str, Any] = {}
    recall_candidates = await _collect_recall_candidates(
        conn=conn,
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_ids,
        limit=limit,
        timeout_ms=timeout_ms,
        stage_metrics=stage_metrics,
    )
    if not recall_candidates:
        logger.info(
            (
                "cfkg.timing user_id=%s ranking_mode=%s cf_recall_ms=%.1f "
                "content_recall_ms=%.1f cfkg_rerank_ms=0.0 total_ms=%.1f "
                "content_triggered=%s content_skip_reason=%s cf_candidate_count=%s candidate_count=0"
            ),
            user_id,
            resolved_mode,
            stage_metrics.get("cf_recall_ms", 0.0),
            stage_metrics.get("content_recall_ms", 0.0),
            (time.perf_counter() - request_started_at) * 1000,
            stage_metrics.get("content_triggered", False),
            stage_metrics.get("content_skip_reason"),
            stage_metrics.get("cf_candidate_count", 0),
        )
        return []

    rerank_started_at = time.perf_counter()
    ranked_items = await asyncio.to_thread(
        _rank_candidate_pool,
        bundle,
        user_id,
        recall_candidates,
        seen_ids,
        user_profile,
        seed_movie_ids,
        timeout_ms,
        resolved_mode,
        limit,
    )
    rerank_ms = (time.perf_counter() - rerank_started_at) * 1000
    total_ms = (time.perf_counter() - request_started_at) * 1000
    logger.info(
        (
            "cfkg.timing user_id=%s ranking_mode=%s cf_recall_ms=%.1f "
            "content_recall_ms=%.1f cfkg_rerank_ms=%.1f total_ms=%.1f "
            "content_triggered=%s content_skip_reason=%s content_timed_out=%s "
            "cf_candidate_count=%s content_candidate_count=%s candidate_count=%s"
        ),
        user_id,
        resolved_mode,
        stage_metrics.get("cf_recall_ms", 0.0),
        stage_metrics.get("content_recall_ms", 0.0),
        rerank_ms,
        total_ms,
        stage_metrics.get("content_triggered", False),
        stage_metrics.get("content_skip_reason"),
        stage_metrics.get("content_timed_out", False),
        stage_metrics.get("cf_candidate_count", 0),
        stage_metrics.get("content_candidate_count", 0),
        len(ranked_items),
    )
    return ranked_items
