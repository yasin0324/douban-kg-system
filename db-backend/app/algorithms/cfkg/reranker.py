"""
Lightweight learned reranker for the CFKG pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.algorithms.cfkg.artifacts import ensure_dir, resolve_reranker_path

RERANKER_FEATURE_NAMES = (
    "recall_score",
    "recall_rank_score",
    "cfkg_score",
    "cfkg_rank_score",
    "profile_score",
    "source_count",
    "has_cf_source",
    "has_itemcf_source",
    "has_content_source",
    "has_ppr_source",
    "genre_overlap_count",
    "director_overlap_count",
    "actor_overlap_count",
    "negative_signal_count",
    "negative_overlap_count",
)

_RERANKER_CACHE: dict[str, Any] = {
    "path": None,
    "mtime": None,
    "bundle": None,
}


def clear_reranker_cache() -> None:
    _RERANKER_CACHE.update({
        "path": None,
        "mtime": None,
        "bundle": None,
    })


def build_reranker_feature_map(
    *,
    recall_score: float,
    recall_rank_score: float = 0.0,
    cfkg_score: float,
    cfkg_rank_score: float = 0.0,
    profile_score: float,
    recall_sources: list[str],
    negative_signals: list[str],
    genre_overlap_count: float = 0.0,
    director_overlap_count: float = 0.0,
    actor_overlap_count: float = 0.0,
    negative_overlap_count: float = 0.0,
) -> dict[str, float]:
    normalized_sources = set(recall_sources or [])
    return {
        "recall_score": float(recall_score),
        "recall_rank_score": float(recall_rank_score),
        "cfkg_score": float(cfkg_score),
        "cfkg_rank_score": float(cfkg_rank_score),
        "profile_score": float(profile_score),
        "source_count": float(len(normalized_sources)),
        "has_cf_source": 1.0 if "graph_cf" in normalized_sources else 0.0,
        "has_itemcf_source": 1.0 if "itemcf" in normalized_sources else 0.0,
        "has_content_source": 1.0 if "graph_content" in normalized_sources else 0.0,
        "has_ppr_source": 1.0 if "graph_ppr" in normalized_sources else 0.0,
        "genre_overlap_count": float(genre_overlap_count),
        "director_overlap_count": float(director_overlap_count),
        "actor_overlap_count": float(actor_overlap_count),
        "negative_signal_count": float(len(negative_signals or [])),
        "negative_overlap_count": float(negative_overlap_count),
    }


def feature_vector_from_map(
    feature_map: dict[str, float],
    feature_names: list[str] | tuple[str, ...] = RERANKER_FEATURE_NAMES,
) -> np.ndarray:
    return np.array(
        [float(feature_map.get(name, 0.0)) for name in feature_names],
        dtype=np.float64,
    )


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def train_reranker_model(
    feature_rows: list[dict[str, float]],
    labels: list[int],
    *,
    iterations: int = 800,
    learning_rate: float = 0.08,
    l2: float = 0.01,
) -> dict[str, Any]:
    if not feature_rows or not labels:
        raise ValueError("训练 reranker 需要非空样本")
    if len(feature_rows) != len(labels):
        raise ValueError("特征与标签数量不一致")

    x_matrix = np.vstack([feature_vector_from_map(row, RERANKER_FEATURE_NAMES) for row in feature_rows])
    y_vector = np.array(labels, dtype=np.float64)
    if np.all(y_vector == y_vector[0]):
        raise ValueError("标签必须同时包含正负样本")

    means = x_matrix.mean(axis=0)
    scales = x_matrix.std(axis=0)
    scales = np.where(scales < 1e-8, 1.0, scales)
    normalized_x = (x_matrix - means) / scales

    positive_count = float(np.sum(y_vector))
    negative_count = float(len(y_vector) - positive_count)
    positive_weight = negative_count / max(positive_count, 1.0)
    sample_weights = np.where(y_vector > 0.5, positive_weight, 1.0)

    weights = np.zeros(normalized_x.shape[1], dtype=np.float64)
    bias = 0.0
    losses: list[float] = []

    for _ in range(iterations):
        logits = normalized_x @ weights + bias
        probabilities = _sigmoid(logits)
        probabilities = np.clip(probabilities, 1e-8, 1.0 - 1e-8)
        weighted_error = (probabilities - y_vector) * sample_weights
        gradient_w = (normalized_x.T @ weighted_error) / len(y_vector) + l2 * weights
        gradient_b = float(np.sum(weighted_error) / len(y_vector))
        weights -= learning_rate * gradient_w
        bias -= learning_rate * gradient_b

        loss = (
            -np.mean(
                sample_weights
                * (
                    y_vector * np.log(probabilities)
                    + (1.0 - y_vector) * np.log(1.0 - probabilities)
                )
            )
            + 0.5 * l2 * float(np.sum(weights ** 2))
        )
        losses.append(float(loss))

    training_scores = _sigmoid(normalized_x @ weights + bias)
    predictions = (training_scores >= 0.5).astype(np.float64)
    accuracy = float(np.mean(predictions == y_vector))

    return {
        "feature_names": list(RERANKER_FEATURE_NAMES),
        "weights": weights.tolist(),
        "bias": float(bias),
        "means": means.tolist(),
        "scales": scales.tolist(),
        "metrics": {
            "iterations": iterations,
            "learning_rate": learning_rate,
            "l2": l2,
            "training_row_count": int(len(feature_rows)),
            "positive_count": int(positive_count),
            "negative_count": int(negative_count),
            "final_loss": round(losses[-1], 6),
            "training_accuracy": round(accuracy, 6),
        },
    }


def save_reranker_artifact(
    artifact: dict[str, Any],
    reranker_path: str | Path | None = None,
) -> str:
    resolved_path = resolve_reranker_path(reranker_path)
    ensure_dir(resolved_path.parent)
    with resolved_path.open("w", encoding="utf-8") as file_obj:
        json.dump(artifact, file_obj, ensure_ascii=False, indent=2)
    clear_reranker_cache()
    return str(resolved_path)


def load_reranker_bundle(
    reranker_path: str | Path | None = None,
) -> dict[str, Any] | None:
    resolved_path = resolve_reranker_path(reranker_path)
    if not resolved_path.exists():
        return None

    current_mtime = resolved_path.stat().st_mtime
    if (
        _RERANKER_CACHE["path"] == str(resolved_path)
        and _RERANKER_CACHE["mtime"] == current_mtime
        and _RERANKER_CACHE["bundle"] is not None
    ):
        return _RERANKER_CACHE["bundle"]

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    bundle = {
        "path": str(resolved_path),
        "feature_names": payload["feature_names"],
        "weights": np.array(payload["weights"], dtype=np.float64),
        "bias": float(payload["bias"]),
        "means": np.array(payload["means"], dtype=np.float64),
        "scales": np.array(payload["scales"], dtype=np.float64),
        "metrics": payload.get("metrics", {}),
    }
    _RERANKER_CACHE.update({
        "path": str(resolved_path),
        "mtime": current_mtime,
        "bundle": bundle,
    })
    return bundle


def score_reranker_features(
    bundle: dict[str, Any],
    feature_map: dict[str, float],
) -> tuple[float, dict[str, float]]:
    feature_names = bundle["feature_names"]
    vector = feature_vector_from_map(feature_map, feature_names)
    normalized = (vector - bundle["means"]) / np.where(bundle["scales"] < 1e-8, 1.0, bundle["scales"])
    contributions = normalized * bundle["weights"]
    score = float(_sigmoid(np.array([float(np.sum(contributions) + bundle["bias"])], dtype=np.float64))[0])
    contribution_map = {
        feature_name: float(value)
        for feature_name, value in zip(feature_names, contributions.tolist())
    }
    return score, contribution_map
