"""
Train a lightweight reranker on top of the CFKG pipeline features.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _dedupe_movie_ids(movie_ids):
    seen = set()
    items = []
    for movie_id in movie_ids:
        if movie_id in seen:
            continue
        seen.add(movie_id)
        items.append(movie_id)
    return items


def _build_time_split_case(rows):
    holdout_index = None
    for index, row in enumerate(rows):
        if float(row["rating"]) >= POSITIVE_RATING:
            holdout_index = index

    if holdout_index is None or holdout_index == 0:
        return None

    history_rows = rows[:holdout_index]
    positive_seed_ids = _dedupe_movie_ids(
        [row["mid"] for row in history_rows if float(row["rating"]) >= POSITIVE_RATING]
    )
    seed_movie_ids = list(reversed(positive_seed_ids[-5:]))
    if not seed_movie_ids:
        return None

    holdout_row = rows[holdout_index]
    seen_movie_ids = _dedupe_movie_ids([row["mid"] for row in history_rows])
    return {
        "user_id": rows[0]["user_id"],
        "holdout_movie_id": holdout_row["mid"],
        "seed_movie_ids": seed_movie_ids,
        "seen_movie_ids": seen_movie_ids,
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
            case = _build_time_split_case(_fetch_user_rating_rows(conn, user_id))
            if not case:
                continue
            cases += 1
            recall_candidates = await _collect_recall_candidates(
                user_id=case["user_id"],
                user_profile=None,
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
                None,
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
