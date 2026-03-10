"""
Train a lightweight reranker on top of the CFKG pipeline features.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.algorithms.common import (
    build_weighted_user_profile,
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
)
from app.algorithms.cfkg.artifacts import DEFAULT_RERANKER_PATH
from app.algorithms.cfkg.inference import (
    DEFAULT_TIMEOUT_MS,
    _collect_recall_candidates,
    _load_model_bundle,
    _rank_candidate_pool,
)
from app.algorithms.cfkg.reranker import (
    save_reranker_artifact,
    train_reranker_model,
)
from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection
from app.services import user_service

POSITIVE_RATING = 4.0


@dataclass
class RerankerTrainingConfig:
    output_path: str | Path = DEFAULT_RERANKER_PATH
    user_limit: int = 200
    recommendation_limit: int = 50
    timeout_ms: int = 2500
    iterations: int = 800
    learning_rate: float = 0.08
    l2: float = 0.01


def _coerce_sort_time(value: Any, fallback_index: int) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime(1970, 1, 1) + timedelta(seconds=fallback_index)


def _build_profile_from_history(
    history_rating_rows: list[dict[str, Any]],
    history_pref_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_profile = user_service.build_user_recommendation_profile_from_rows(
        rating_rows=history_rating_rows,
        pref_rows=history_pref_rows,
    )
    movie_ids = dedupe_preserve_order(
        raw_profile["positive_movie_ids"]
        + raw_profile["negative_movie_ids"]
        + raw_profile["representative_movie_ids"]
    )
    movie_profile_map = fetch_movie_graph_profile_map(
        Neo4jConnection.get_driver(),
        movie_ids,
        timeout_ms=1000,
    )
    weighted_profile = build_weighted_user_profile(
        movie_profile_map,
        raw_profile["movie_feedback"],
    )
    return {
        **raw_profile,
        **weighted_profile,
    }


def _build_time_split_case(
    rating_rows: list[dict[str, Any]],
    pref_rows: list[dict[str, Any]] | None = None,
):
    events: list[dict[str, Any]] = []
    for index, row in enumerate(rating_rows):
        events.append({
            "kind": "rating",
            "sort_time": _coerce_sort_time(
                row.get("updated_at") or row.get("rated_at"),
                index,
            ),
            "row": row,
            "is_relevant": float(row.get("rating") or 0.0) >= POSITIVE_RATING,
            "movie_id": str(row["mid"]),
        })
    base_index = len(events)
    for index, row in enumerate(pref_rows or []):
        events.append({
            "kind": "pref",
            "sort_time": _coerce_sort_time(
                row.get("updated_at") or row.get("created_at"),
                base_index + index,
            ),
            "row": row,
            "is_relevant": row.get("pref_type") == "like",
            "movie_id": str(row["mid"]),
        })

    if len(events) < 4:
        return None

    events.sort(key=lambda item: (item["sort_time"], item["kind"], item["movie_id"]))
    preferred_split = max(1, min(len(events) - 1, int(len(events) * 0.8)))

    split_index = None
    candidate_indices = list(range(preferred_split, len(events))) + list(
        range(preferred_split - 1, 0, -1)
    )
    for index in candidate_indices:
        history_events = events[:index]
        future_events = events[index:]
        if len(history_events) < 2:
            continue
        if any(event["is_relevant"] for event in future_events):
            split_index = index
            break

    if split_index is None:
        return None

    history_events = events[:split_index]
    future_events = events[split_index:]
    history_rating_rows = [event["row"] for event in history_events if event["kind"] == "rating"]
    history_pref_rows = [event["row"] for event in history_events if event["kind"] == "pref"]
    future_positive_movie_ids = dedupe_preserve_order(
        event["movie_id"]
        for event in future_events
        if event["is_relevant"]
    )
    if not future_positive_movie_ids:
        return None

    user_profile = _build_profile_from_history(
        history_rating_rows=history_rating_rows,
        history_pref_rows=history_pref_rows,
    )
    context_movie_ids = dedupe_preserve_order(
        user_profile.get("context_movie_ids")
        or user_profile.get("positive_movie_ids")
        or []
    )
    if not context_movie_ids:
        return None

    seed_movie_ids = dedupe_preserve_order(
        (user_profile.get("representative_movie_ids") or [])[:5]
        + context_movie_ids[:5]
    )[:5]
    seen_movie_ids = dedupe_preserve_order(user_profile.get("hard_exclude_movie_ids") or [])
    return {
        "user_id": rating_rows[0]["user_id"] if rating_rows else pref_rows[0]["user_id"],
        "holdout_movie_id": future_positive_movie_ids[0],
        "seed_movie_ids": seed_movie_ids,
        "seen_movie_ids": seen_movie_ids,
        "user_profile": user_profile,
    }


def _fetch_candidate_user_ids(conn, limit: int):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE status = 'active' AND is_mock = 0 ORDER BY id ASC LIMIT %s",
            (limit,),
        )
        return [row["id"] for row in cursor.fetchall()]


def _fetch_user_rating_rows(conn, user_id: int):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, user_id, mid, rating, rated_at, updated_at "
            "FROM user_movie_ratings "
            "WHERE user_id = %s "
            "ORDER BY COALESCE(updated_at, rated_at) ASC, rated_at ASC, id ASC",
            (user_id,),
        )
        return cursor.fetchall()


def _fetch_user_pref_rows(conn, user_id: int):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, user_id, mid, pref_type, created_at, updated_at "
            "FROM user_movie_prefs "
            "WHERE user_id = %s "
            "ORDER BY COALESCE(updated_at, created_at) ASC, created_at ASC, id ASC",
            (user_id,),
        )
        return cursor.fetchall()


async def train_cfkg_reranker(config: RerankerTrainingConfig) -> dict[str, Any]:
    bundle = await asyncio.to_thread(_load_model_bundle, None)
    if bundle is None:
        raise FileNotFoundError("当前没有可用的 CFKG 模型，无法训练 reranker")

    init_pool()
    conn = get_connection()
    try:
        feature_rows: list[dict[str, float]] = []
        labels: list[int] = []
        cases = 0
        used_cases = 0
        skipped_missing_positive = 0

        for user_id in _fetch_candidate_user_ids(conn, limit=config.user_limit):
            case = _build_time_split_case(
                _fetch_user_rating_rows(conn, user_id),
                _fetch_user_pref_rows(conn, user_id),
            )
            if not case:
                continue
            cases += 1
            recall_candidates = await _collect_recall_candidates(
                conn=conn,
                user_id=case["user_id"],
                user_profile=case["user_profile"],
                seed_movie_ids=case["seed_movie_ids"],
                seen_movie_ids=case["seen_movie_ids"],
                limit=config.recommendation_limit,
                timeout_ms=max(config.timeout_ms, DEFAULT_TIMEOUT_MS),
            )
            if not recall_candidates:
                skipped_missing_positive += 1
                continue

            ranked_items = await asyncio.to_thread(
                _rank_candidate_pool,
                bundle,
                case["user_id"],
                recall_candidates,
                case["seen_movie_ids"],
                case["user_profile"],
                case["seed_movie_ids"],
                config.timeout_ms,
                "pipeline",
                len(recall_candidates),
                True,
            )
            if not ranked_items:
                skipped_missing_positive += 1
                continue

            holdout_movie_id = case["holdout_movie_id"]
            if not any(item["movie_id"] == holdout_movie_id for item in ranked_items):
                skipped_missing_positive += 1
                continue

            used_cases += 1
            for item in ranked_items:
                feature_rows.append({
                    "recall_score": float(item.get("recall_score", 0.0)),
                    "recall_rank_score": float(item.get("recall_rank_score", 0.0)),
                    "cfkg_score": float(item.get("cfkg_score", 0.0)),
                    "cfkg_rank_score": float(item.get("cfkg_rank_score", 0.0)),
                    "profile_score": float(item.get("profile_score", 0.0)),
                    "source_count": float(
                        len([source for source in item.get("source_algorithms", []) if source != "cfkg"])
                    ),
                    "has_cf_source": 1.0 if "graph_cf" in item.get("source_algorithms", []) else 0.0,
                    "has_itemcf_source": 1.0 if "itemcf" in item.get("source_algorithms", []) else 0.0,
                    "has_content_source": 1.0 if "graph_content" in item.get("source_algorithms", []) else 0.0,
                    "has_ppr_source": 1.0 if "graph_ppr" in item.get("source_algorithms", []) else 0.0,
                    "genre_overlap_count": float(item.get("genre_overlap_count", 0.0)),
                    "director_overlap_count": float(item.get("director_overlap_count", 0.0)),
                    "actor_overlap_count": float(item.get("actor_overlap_count", 0.0)),
                    "negative_signal_count": float(len(item.get("negative_signals", []) or [])),
                    "negative_overlap_count": float(item.get("negative_overlap_count", 0.0)),
                })
                labels.append(1 if item["movie_id"] == holdout_movie_id else 0)
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()

    artifact = train_reranker_model(
        feature_rows,
        labels,
        iterations=config.iterations,
        learning_rate=config.learning_rate,
        l2=config.l2,
    )
    artifact["metrics"].update({
        "candidate_case_count": cases,
        "used_case_count": used_cases,
        "skipped_missing_positive_case_count": skipped_missing_positive,
        "recommendation_limit": config.recommendation_limit,
        "timeout_ms": config.timeout_ms,
        "base_model_path": bundle["path"],
    })
    output_path = save_reranker_artifact(artifact, config.output_path)
    return {
        "output_path": output_path,
        "metrics": artifact["metrics"],
    }
