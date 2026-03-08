"""
CFKG inference helpers and API-facing recommendation entry.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.algorithms.common import (
    build_weighted_user_profile,
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    score_movie_against_user_profile,
)
from app.algorithms.cfkg.artifacts import resolve_model_path
from app.algorithms.cfkg.model import TransEModel, require_torch
from app.algorithms.graph_cf import get_graph_cf_recall_candidates
from app.algorithms.graph_content import get_graph_content_recall_candidates
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT_MS = 800
DEFAULT_RECALL_TARGET_MIN = 120
DEFAULT_RECALL_TARGET_MAX = 160
CF_RECALL_WEIGHT = 0.50
CFKG_RERANK_WEIGHT = 0.35
PROFILE_WEIGHT = 0.15
_MODEL_CACHE: dict[str, Any] = {
    "path": None,
    "mtime": None,
    "bundle": None,
}


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
) -> list[dict[str, Any]]:
    recall_target = min(max(limit * 6, DEFAULT_RECALL_TARGET_MIN), DEFAULT_RECALL_TARGET_MAX)
    minimum_viable_candidates = max(limit * 2, 40)
    seen_ids = dedupe_preserve_order(seen_movie_ids)

    cf_candidates = await get_graph_cf_recall_candidates(
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_ids,
        exclude_mock_users=True,
        limit=recall_target,
        timeout_ms=max(timeout_ms or DEFAULT_TIMEOUT_MS, 1500),
    )
    merged_candidates = list(cf_candidates)
    if len(merged_candidates) >= recall_target or len(merged_candidates) >= minimum_viable_candidates:
        return merged_candidates[:recall_target]

    content_seen_ids = dedupe_preserve_order(
        seen_ids + [item["movie_id"] for item in merged_candidates]
    )
    content_candidates = await get_graph_content_recall_candidates(
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=content_seen_ids,
        exclude_mock_users=True,
        limit=max(recall_target, recall_target - len(merged_candidates) + 40),
        timeout_ms=min(max(timeout_ms or DEFAULT_TIMEOUT_MS, 500), 800),
    )
    merged_movie_ids = {item["movie_id"] for item in merged_candidates}
    for item in content_candidates:
        if item["movie_id"] in merged_movie_ids:
            continue
        merged_candidates.append(item)
        merged_movie_ids.add(item["movie_id"])
        if len(merged_candidates) >= recall_target:
            break
    return merged_candidates[:recall_target]


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

    ranked_items = []
    for candidate in candidate_items:
        movie_id = candidate["movie_id"]
        if movie_id not in cfkg_score_map:
            continue

        recall_score = recall_score_map.get(movie_id, 0.0)
        cfkg_score = cfkg_score_map.get(movie_id, 0.0)
        profile_score = 0.0
        profile_reasons: list[str] = []
        negative_signals: list[str] = []
        if ranking_mode == "pipeline" and effective_profile:
            profile_score, profile_reasons, negative_signals = score_movie_against_user_profile(
                feature_map.get(movie_id),
                effective_profile,
            )

        if ranking_mode == "raw":
            final_score = cfkg_score
            reasons = ["CFKG 对第一阶段召回候选完成表示学习打分"]
            score_breakdown = {"cfkg": round(final_score, 6)}
        else:
            final_score = (
                CF_RECALL_WEIGHT * recall_score
                + CFKG_RERANK_WEIGHT * cfkg_score
                + PROFILE_WEIGHT * profile_score
            )
            reasons = []
            reasons.extend(candidate.get("reasons", [])[:1])
            reasons.append("先由协同过滤召回候选，再由 CFKG 精排")
            reasons.extend(profile_reasons[:1])
            recall_sources = candidate.get("source_algorithms") or [candidate.get("source", "graph_cf")]
            recall_contrib = CF_RECALL_WEIGHT * recall_score
            recall_share = recall_contrib / max(len(recall_sources), 1)
            score_breakdown = {
                source: round(recall_share, 6)
                for source in recall_sources
            }
            score_breakdown["cfkg"] = round(CFKG_RERANK_WEIGHT * cfkg_score, 6)
            if profile_score > 0:
                score_breakdown["profile"] = round(PROFILE_WEIGHT * profile_score, 6)

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
            "cfkg_score": cfkg_score,
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
) -> list[dict[str, Any]]:
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
    recall_candidates = await _collect_recall_candidates(
        user_id=user_id,
        user_profile=user_profile,
        seed_movie_ids=seed_movie_ids,
        seen_movie_ids=seen_ids,
        limit=limit,
        timeout_ms=timeout_ms,
    )
    if not recall_candidates:
        return []

    return await asyncio.to_thread(
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
