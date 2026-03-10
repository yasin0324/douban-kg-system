#!/usr/bin/env python3
"""
基于用户画像与时间切分的离线推荐评估脚本。
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
import json
import logging
import math
import os
from pathlib import Path
import sys
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.algorithms.cfkg import get_cfkg_recommendations
from app.algorithms.cfkg.artifacts import make_entity_key
from app.algorithms.cfkg.inference import _load_model_bundle as load_cfkg_model_bundle
from app.algorithms.cfkg.model import require_torch
from app.algorithms.cfkg.reranker import (
    build_reranker_feature_map,
    load_reranker_bundle,
    score_reranker_features,
)
from app.algorithms.common import (
    build_weighted_user_profile,
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    score_movie_against_user_profile,
    split_multi_value,
)
from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_content import (
    get_graph_content_recall_candidates,
    get_graph_content_recommendations,
)
from app.algorithms.graph_ppr import get_graph_ppr_recommendations
from app.algorithms.hybrid_manager import HybridRecommendationManager
from app.algorithms.item_cf import get_itemcf_recommendations
from app.algorithms.tfidf_content import get_tfidf_recommendations
from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection
from app.services import user_service

logger = logging.getLogger(__name__)
DEFAULT_ALGORITHMS = ["itemcf", "tfidf", "cf", "content", "ppr", "hybrid", "cfkg"]
LEGACY_PROTOCOL = "profile_based_time_split"
STRICT_PROTOCOL = "strict_profile_time_split"
DEFAULT_PROTOCOL = STRICT_PROTOCOL
REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_JSON_PATH = REPORT_DIR / "recommendation_eval_latest.json"
REPORT_MD_PATH = REPORT_DIR / "recommendation_eval_latest.md"
POSITIVE_RATING = 4.0
METRIC_K = 10
STRICT_CF_POSITIVE_RATING = 3.5
STRICT_CF_SHRINKAGE = 2.0
STRICT_CF_NEIGHBOR_LIMIT = 40
STRICT_CF_SIGNAL_QUALITY_BOOST = 0.03
STRICT_CF_NEGATIVE_CONFLICT_PENALTY = 0.08
STRICT_CFKG_RECALL_WEIGHT = 0.50
STRICT_CFKG_EMBEDDING_WEIGHT = 0.35
STRICT_CFKG_PROFILE_WEIGHT = 0.15
STRICT_CFKG_RECALL_TARGET_MIN = 120
STRICT_CFKG_RECALL_TARGET_MAX = 160
STRICT_CFKG_CONTENT_RECALL_TIMEOUT_MS = 600
STRICT_CFKG_CONTENT_RECALL_MIN_GAP = 12
EVAL_TIMEOUTS_MS = {
    "itemcf": 1500,
    "tfidf": 2500,
    "cfkg": 2500,
    "cf": 5000,
    "content": 12000,
    "ppr": 18000,
    "hybrid": 18000,
}
ALGORITHM_DESCRIPTIONS = {
    "itemcf": {
        "label": "ItemCF",
        "summary": "传统物品协同过滤，对照用户行为共现关系。",
        "strength": "对强历史共现信号响应稳定，实现简单，适合作为行为基线。",
        "weakness": "冷启动与长尾覆盖较弱，缺少图谱语义与多跳关系建模。",
    },
    "tfidf": {
        "label": "TF-IDF",
        "summary": "纯内容文本基线，对照电影元数据文本相似度。",
        "strength": "解释性强，对冷启动内容召回更友好。",
        "weakness": "难以利用用户间协同关系，对隐性兴趣发现能力有限。",
    },
    "cf": {
        "label": "Graph CF",
        "summary": "基于用户-电影评分图的协同过滤。",
        "strength": "能利用相似用户的图邻域行为，效果通常优于纯 ItemCF。",
        "weakness": "仍然依赖足够行为数据，对实体语义建模较弱。",
    },
    "content": {
        "label": "Graph Content",
        "summary": "基于图谱实体命中的内容推荐。",
        "strength": "解释路径清晰，可直接回溯到导演、演员、类型等实体。",
        "weakness": "多样性和隐性关系发现能力通常弱于图游走或嵌入模型。",
    },
    "ppr": {
        "label": "PPR",
        "summary": "基于知识图谱游走的多跳关联推荐。",
        "strength": "擅长发现隐性关联电影，更贴近知识图谱推荐主题。",
        "weakness": "对图结构质量和候选投影质量更敏感，延迟也更高。",
    },
    "hybrid": {
        "label": "Hybrid",
        "summary": "融合 CF、Content、PPR 的多策略推荐。",
        "strength": "兼顾稳定性、解释性与图谱多跳能力，整体表现通常较稳。",
        "weakness": "调参与系统复杂度更高，单条解释不如纯算法直接。",
    },
    "cfkg": {
        "label": "CFKG",
        "summary": "当前线上默认链路，联合用户行为与知识图谱嵌入。",
        "strength": "同时建模交互关系和知识图谱结构，适合作为主推荐链路。",
        "weakness": "训练与部署成本更高，实验复现实验链路更复杂。",
    },
}
STRICT_PROTOCOL_NOTES = [
    "协同过滤类算法仅使用严格早于切分时点的历史行为快照，不再读取当前整库的完整交互。",
    "TF-IDF、图内容和 PPR 仅使用历史画像与静态电影元数据/知识图谱结构。",
    "CFKG 在严格协议下改为“历史正反馈电影合成用户表示 + 候选集 learned reranker 精排”，避免直接使用现成用户 embedding。",
    "若需要对 CFKG 做完全无泄漏评估，仍需使用同一时间快照重导数据并重训嵌入模型。",
]


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


def build_time_split_case(
    rating_rows: list[dict[str, Any]],
    pref_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
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
        relevant_future_movie_ids = dedupe_preserve_order(
            event["movie_id"]
            for event in future_events
            if event["is_relevant"]
        )
        if relevant_future_movie_ids:
            split_index = index
            break

    if split_index is None:
        return None

    history_events = events[:split_index]
    future_events = events[split_index:]
    split_time = future_events[0]["sort_time"] if future_events else history_events[-1]["sort_time"]
    history_positive_movie_ids = dedupe_preserve_order(
        event["movie_id"]
        for event in history_events
        if (
            (event["kind"] == "rating" and float(event["row"].get("rating") or 0.0) >= POSITIVE_RATING)
            or (
                event["kind"] == "pref"
                and event["row"].get("pref_type") in {"like", "want_to_watch"}
            )
        )
    )
    history_rating_rows = [event["row"] for event in history_events if event["kind"] == "rating"]
    history_pref_rows = [event["row"] for event in history_events if event["kind"] == "pref"]
    future_relevant_movie_ids = dedupe_preserve_order(
        event["movie_id"]
        for event in future_events
        if event["is_relevant"]
    )
    auxiliary_future_want_movie_ids = dedupe_preserve_order(
        event["movie_id"]
        for event in future_events
        if event["kind"] == "pref" and event["row"].get("pref_type") == "want_to_watch"
    )
    return {
        "user_id": rating_rows[0]["user_id"] if rating_rows else (pref_rows or [])[0]["user_id"],
        "history_rating_rows": history_rating_rows,
        "history_pref_rows": history_pref_rows,
        "future_relevant_movie_ids": future_relevant_movie_ids,
        "future_want_movie_ids": auxiliary_future_want_movie_ids,
        "split_time": split_time,
        "history_event_count": len(history_events),
        "future_event_count": len(future_events),
        "holdout_movie_id": future_relevant_movie_ids[0],
        "seed_movie_ids": history_positive_movie_ids,
        "seen_movie_ids": dedupe_preserve_order(event["movie_id"] for event in history_events),
    }


def precision_at_k(items: list[dict[str, Any]], relevant_movie_ids: set[str], k: int) -> float:
    top_k = [str(item["movie_id"]) for item in items[:k]]
    if not top_k:
        return 0.0
    hits = sum(1 for movie_id in top_k if movie_id in relevant_movie_ids)
    return hits / float(k)


def hit_at_k(items: list[dict[str, Any]], holdout_movie_id: str, k: int) -> float:
    top_k = [str(item["movie_id"]) for item in items[:k]]
    return 1.0 if str(holdout_movie_id) in top_k else 0.0


def recall_at_k(items: list[dict[str, Any]], relevant_movie_ids: set[str], k: int) -> float:
    if not relevant_movie_ids:
        return 0.0
    top_k = [str(item["movie_id"]) for item in items[:k]]
    hits = sum(1 for movie_id in top_k if movie_id in relevant_movie_ids)
    return hits / float(len(relevant_movie_ids))


def ndcg_at_k(items: list[dict[str, Any]], relevant_movie_ids: set[str], k: int) -> float:
    dcg = 0.0
    for index, item in enumerate(items[:k], start=1):
        if str(item["movie_id"]) in relevant_movie_ids:
            dcg += 1.0 / math.log2(index + 1)
    ideal_count = min(len(relevant_movie_ids), k)
    if ideal_count <= 0:
        return 0.0
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    return dcg / idcg if idcg else 0.0


def diversity_at_k(
    items: list[dict[str, Any]],
    movie_genre_map: dict[str, set[str]],
    k: int,
) -> float:
    top_k_ids = [str(item["movie_id"]) for item in items[:k]]
    if len(top_k_ids) < 2:
        return 0.0

    distances = []
    for index, left_movie_id in enumerate(top_k_ids):
        left_genres = movie_genre_map.get(left_movie_id, set())
        for right_movie_id in top_k_ids[index + 1:]:
            right_genres = movie_genre_map.get(right_movie_id, set())
            union = left_genres | right_genres
            if not union:
                distances.append(0.0)
                continue
            similarity = len(left_genres & right_genres) / float(len(union))
            distances.append(1.0 - similarity)
    return sum(distances) / float(len(distances)) if distances else 0.0


def fetch_candidate_user_ids(conn, limit: int = 100) -> list[int]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE status = 'active' AND is_mock = 0 ORDER BY id ASC LIMIT %s",
            (limit,),
        )
        return [int(row["id"]) for row in cursor.fetchall()]


def fetch_user_rating_rows(conn, user_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, user_id, mid, rating, rated_at, updated_at "
            "FROM user_movie_ratings "
            "WHERE user_id = %s "
            "ORDER BY COALESCE(updated_at, rated_at) ASC, rated_at ASC, id ASC",
            (user_id,),
        )
        return cursor.fetchall()


def fetch_user_pref_rows(conn, user_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, user_id, mid, pref_type, created_at, updated_at "
            "FROM user_movie_prefs "
            "WHERE user_id = %s "
            "ORDER BY COALESCE(updated_at, created_at) ASC, created_at ASC, id ASC",
            (user_id,),
        )
        return cursor.fetchall()


def fetch_movie_catalog_count(conn) -> int:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM movies WHERE type = 'movie'")
        row = cursor.fetchone()
    return int(row["total"] or 0)


def fetch_movie_genre_map(conn, movie_ids: list[str]) -> dict[str, set[str]]:
    movie_ids = dedupe_preserve_order(movie_ids)
    if not movie_ids:
        return {}

    placeholders = ",".join(["%s"] * len(movie_ids))
    query = f"""
        SELECT douban_id AS movie_id,
               genres
        FROM movies
        WHERE douban_id IN ({placeholders})
    """
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(movie_ids))
        rows = cursor.fetchall()
    return {
        str(row["movie_id"]): split_multi_value(row.get("genres"))
        for row in rows
    }


def fetch_movie_title_map(conn, movie_ids: list[str]) -> dict[str, str]:
    movie_ids = dedupe_preserve_order(movie_ids)
    if not movie_ids:
        return {}

    placeholders = ",".join(["%s"] * len(movie_ids))
    query = f"""
        SELECT douban_id AS movie_id,
               name AS title
        FROM movies
        WHERE douban_id IN ({placeholders})
    """
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(movie_ids))
        rows = cursor.fetchall()
    return {
        str(row["movie_id"]): row.get("title") or str(row["movie_id"])
        for row in rows
    }


def resolve_positive_context(user_profile: dict[str, Any] | None) -> tuple[list[str], dict[str, float]]:
    if not user_profile:
        return [], {}
    movie_feedback = user_profile.get("movie_feedback", {})
    positive_movie_ids = dedupe_preserve_order(
        user_profile.get("context_movie_ids")
        or user_profile.get("positive_movie_ids")
        or []
    )[:24]
    positive_weights = {
        movie_id: float(movie_feedback.get(movie_id, {}).get("positive_weight") or 1.0)
        for movie_id in positive_movie_ids
    }
    return positive_movie_ids, positive_weights


def build_strict_seed_context(
    positive_movie_ids: list[str],
    positive_weights: dict[str, float],
) -> tuple[list[tuple[str, float]], float]:
    seed_rows: list[tuple[str, float]] = []
    total_seed_weight = 0.0
    for movie_id in dedupe_preserve_order(positive_movie_ids):
        seed_weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if seed_weight <= 0:
            continue
        seed_rows.append((movie_id, seed_weight))
        total_seed_weight += seed_weight
    return seed_rows, total_seed_weight


def resolve_strict_graph_cf_context(
    user_profile: dict[str, Any] | None,
) -> tuple[list[str], dict[str, float]]:
    positive_movie_ids, positive_weights = resolve_positive_context(user_profile)
    if not user_profile:
        return positive_movie_ids, positive_weights

    movie_feedback = user_profile.get("movie_feedback", {})
    filtered_ids = [
        movie_id
        for movie_id in positive_movie_ids
        if (
            float(movie_feedback.get(movie_id, {}).get("rating") or 0.0) >= STRICT_CF_POSITIVE_RATING
            or bool(movie_feedback.get(movie_id, {}).get("is_liked"))
        )
    ]
    if not filtered_ids:
        return positive_movie_ids, positive_weights
    return filtered_ids, {
        movie_id: positive_weights[movie_id]
        for movie_id in filtered_ids
        if movie_id in positive_weights
    }


def has_sufficient_content_signal(user_profile: dict[str, Any] | None) -> bool:
    if not user_profile:
        return False
    positive_features = user_profile.get("positive_features", {})
    return (
        len(positive_features.get("genres", {})) >= 2
        or len(positive_features.get("directors", {})) >= 1
        or len(positive_features.get("actors", {})) >= 2
    )


def normalize_recall_candidates(
    records: list[dict[str, Any]],
    score_key: str,
    source: str,
) -> list[dict[str, Any]]:
    if not records:
        return []

    scores = [float(record.get(score_key) or 0.0) for record in records]
    min_score = min(scores)
    max_score = max(scores)
    scale = max(max_score - min_score, 1e-8)
    normalized = []
    for record in records:
        raw_score = float(record.get(score_key) or 0.0)
        normalized_score = (raw_score - min_score) / scale if max_score > min_score else 1.0
        normalized.append({
            "movie_id": str(record["movie_id"]),
            "title": record.get("title", ""),
            "score": normalized_score,
            "recall_score": normalized_score,
            "reasons": list(record.get("reasons") or []),
            "negative_signals": list(record.get("negative_signals") or []),
            "source": source,
            "source_algorithms": [source],
        })
    normalized.sort(key=lambda item: (-item["recall_score"], item["movie_id"]))
    return normalized


def merge_ranked_candidates(
    *candidate_lists: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    merged_items: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []

    for candidate_list in candidate_lists:
        for item in candidate_list or []:
            movie_id = str(item["movie_id"])
            recall_score = float(item.get("recall_score", item.get("score", 0.0)))
            if movie_id not in merged_items:
                merged_items[movie_id] = {
                    **item,
                    "movie_id": movie_id,
                    "recall_score": recall_score,
                    "reasons": dedupe_preserve_order(list(item.get("reasons") or []))[:3],
                    "source_algorithms": dedupe_preserve_order(
                        list(item.get("source_algorithms") or [item.get("source", "graph_cf")])
                    ),
                }
                ordered_ids.append(movie_id)
                continue

            merged = merged_items[movie_id]
            merged["recall_score"] = combine_recall_support_scores(
                [
                    float(merged.get("recall_score", merged.get("score", 0.0))),
                    recall_score,
                ]
            )
            merged["score"] = max(
                float(merged.get("score", merged.get("recall_score", 0.0))),
                float(item.get("score", recall_score)),
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


def combine_recall_support_scores(scores: list[float]) -> float:
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


def _format_strict_itemcf_reason(support_movies: list[dict[str, Any]]) -> list[str]:
    if not support_movies:
        return ["历史窗口内的协同共现用户对该电影有明显偏好"]
    titles = [item.get("title") for item in support_movies if item.get("title")]
    overlap_count = max(int(item.get("overlap_count") or 0) for item in support_movies)
    if titles:
        return [
            f"与《{'》《'.join(titles[:2])}》在历史快照中的正向用户群高度重合",
            f"历史快照内共同正向反馈用户最多 {overlap_count} 人",
        ]
    return [f"历史快照内共同正向反馈用户最多 {overlap_count} 人"]


def _format_strict_graph_cf_reason(record: dict[str, Any]) -> str:
    similar_user_count = int(record.get("similar_user_count") or 0)
    strongest_similarity = float(record.get("strongest_similarity") or 0.0)
    reason = f"{similar_user_count} 位历史相似用户也对这部电影给出正向反馈"
    if strongest_similarity > 0.2:
        reason += f"，近邻强度 {strongest_similarity:.2f}"
    return reason


def build_profile_from_history(
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


STRICT_ITEMCF_SIMILARITY_QUERY = """
WITH positive_interactions AS (
    SELECT DISTINCT user_id, mid
    FROM (
        SELECT user_id, mid
        FROM user_movie_ratings
        WHERE rating >= %s
          AND COALESCE(updated_at, rated_at) < %s
        UNION ALL
        SELECT user_id, mid
        FROM user_movie_prefs
        WHERE pref_type IN ('like', 'want_to_watch')
          AND COALESCE(updated_at, created_at) < %s
    ) AS positive_rows
),
source_users AS (
    SELECT DISTINCT user_id
    FROM positive_interactions
    WHERE mid = %s
),
source_stats AS (
    SELECT COUNT(*) AS source_user_count
    FROM source_users
),
candidate_overlap AS (
    SELECT target.mid AS movie_id,
           COUNT(DISTINCT target.user_id) AS overlap_count
    FROM positive_interactions AS target
    JOIN source_users AS source_user
      ON source_user.user_id = target.user_id
    WHERE target.mid <> %s
    GROUP BY target.mid
),
target_popularity AS (
    SELECT mid AS movie_id,
           COUNT(DISTINCT user_id) AS target_user_count
    FROM positive_interactions
    GROUP BY mid
)
SELECT candidate_overlap.movie_id,
       candidate_overlap.overlap_count,
       source_stats.source_user_count,
       target_popularity.target_user_count,
       (
           (
               candidate_overlap.overlap_count
               / SQRT(source_stats.source_user_count * target_popularity.target_user_count)
           ) * (
               candidate_overlap.overlap_count
               / (candidate_overlap.overlap_count + %s)
           )
       ) AS similarity
FROM candidate_overlap
JOIN target_popularity
  ON target_popularity.movie_id = candidate_overlap.movie_id
CROSS JOIN source_stats
WHERE source_stats.source_user_count > 0
  AND candidate_overlap.overlap_count >= %s
ORDER BY similarity DESC,
         candidate_overlap.overlap_count DESC,
         candidate_overlap.movie_id ASC
LIMIT %s
"""


def fetch_strict_itemcf_similar_movies(
    conn,
    source_movie_id: str,
    interaction_cutoff: datetime,
    limit: int = 120,
    min_overlap: int = 1,
) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            STRICT_ITEMCF_SIMILARITY_QUERY,
            (
                STRICT_CF_POSITIVE_RATING,
                interaction_cutoff,
                interaction_cutoff,
                source_movie_id,
                source_movie_id,
                STRICT_CF_SHRINKAGE,
                min_overlap,
                limit,
            ),
        )
        rows = cursor.fetchall()

    normalized = []
    for row in rows:
        source_user_count = int(row.get("source_user_count") or 0)
        target_user_count = int(row.get("target_user_count") or 0)
        similarity = float(row.get("similarity") or 0.0)
        if source_user_count <= 0 or target_user_count <= 0 or similarity <= 0:
            continue
        normalized.append({
            "movie_id": str(row["movie_id"]),
            "overlap_count": int(row.get("overlap_count") or 0),
            "source_user_count": source_user_count,
            "target_user_count": target_user_count,
            "similarity": similarity,
        })
    return normalized


async def get_strict_itemcf_recommendations(
    conn,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    interaction_cutoff: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    positive_movie_ids, positive_weights = resolve_positive_context(user_profile)
    if not positive_movie_ids:
        return []

    seen_set = set(dedupe_preserve_order(seen_movie_ids))
    candidate_scores: dict[str, float] = defaultdict(float)
    support_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    popularity_map: dict[str, int] = defaultdict(int)
    for movie_id in positive_movie_ids:
        seed_weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if seed_weight <= 0:
            continue
        for neighbor in fetch_strict_itemcf_similar_movies(
            conn=conn,
            source_movie_id=movie_id,
            interaction_cutoff=interaction_cutoff,
            limit=min(max(limit * 6, 120), 220),
        ):
            candidate_id = neighbor["movie_id"]
            if candidate_id in seen_set:
                continue
            contribution = seed_weight * float(neighbor["similarity"])
            if contribution <= 0:
                continue
            candidate_scores[candidate_id] += contribution
            popularity_map[candidate_id] = max(
                popularity_map[candidate_id],
                int(neighbor.get("target_user_count") or 0),
            )
            support_rows[candidate_id].append({
                "movie_id": movie_id,
                "similarity": float(neighbor["similarity"]),
                "overlap_count": int(neighbor.get("overlap_count") or 0),
                "contribution": contribution,
            })

    if not candidate_scores:
        return []

    title_map = fetch_movie_title_map(conn, positive_movie_ids)
    total_positive_weight = max(sum(positive_weights.values()), 1e-8)
    ranked_items = []
    for candidate_id, raw_score in candidate_scores.items():
        sorted_support = sorted(
            support_rows[candidate_id],
            key=lambda item: (
                -float(item["contribution"]),
                -float(item["similarity"]),
                item["movie_id"],
            ),
        )
        support_details = [
            {
                **support,
                "title": title_map.get(support["movie_id"], support["movie_id"]),
            }
            for support in sorted_support[:3]
        ]
        normalized_score = raw_score / total_positive_weight
        popularity_bonus = min(0.08, math.sqrt(max(popularity_map[candidate_id], 0)) * 0.004)
        ranked_items.append({
            "movie_id": candidate_id,
            "title": "",
            "score": normalized_score + popularity_bonus,
            "reasons": _format_strict_itemcf_reason(support_details),
            "negative_signals": [],
            "support_movies": support_details,
            "source": "itemcf",
        })

    ranked_items.sort(key=lambda item: (-float(item["score"]), item["movie_id"]))
    return ranked_items[:limit]


def fetch_strict_graph_cf_records(
    conn,
    user_id: int,
    positive_movie_ids: list[str],
    positive_weights: dict[str, float],
    negative_movie_ids: list[str],
    seen_movie_ids: list[str],
    interaction_cutoff: datetime,
    exclude_mock_users: bool,
    limit: int,
) -> list[dict[str, Any]]:
    seed_rows, total_seed_weight = build_strict_seed_context(
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
    )
    if not seed_rows or total_seed_weight <= 0:
        return []

    seed_context_sql = "\n    UNION ALL\n    ".join(
        "SELECT %s AS mid, %s AS seed_weight" for _ in seed_rows
    )
    seed_params: list[Any] = []
    for movie_id, seed_weight in seed_rows:
        seed_params.extend([movie_id, seed_weight])

    seen_filter_sql = ""
    seen_params: list[Any] = []
    if seen_movie_ids:
        seen_filter_sql = f"AND pf.mid NOT IN ({','.join(['%s'] * len(seen_movie_ids))})"
        seen_params.extend(seen_movie_ids)

    negative_cte_sql = """
negative_conflicts AS (
    SELECT NULL AS neighbor_id, 0 AS negative_conflict_count
    WHERE 1 = 0
),
"""
    negative_params: list[Any] = []
    if negative_movie_ids:
        negative_placeholders = ",".join(["%s"] * len(negative_movie_ids))
        negative_cte_sql = f"""
negative_conflicts AS (
    SELECT pf.user_id AS neighbor_id,
           COUNT(DISTINCT pf.mid) AS negative_conflict_count
    FROM positive_feedback pf
    WHERE pf.mid IN ({negative_placeholders})
    GROUP BY pf.user_id
),
"""
        negative_params.extend(negative_movie_ids)

    mock_filter_sql = "AND COALESCE(u.is_mock, 0) = 0" if exclude_mock_users else ""
    query = f"""
WITH raw_positive_feedback AS (
    SELECT r.user_id, r.mid, r.rating
    FROM user_movie_ratings r
    JOIN users u
      ON u.id = r.user_id
    WHERE r.rating >= %s
      AND COALESCE(r.updated_at, r.rated_at) < %s
      {mock_filter_sql}
),
raw_preference_feedback AS (
    SELECT p.user_id,
           p.mid,
           CASE
             WHEN p.pref_type = 'like' THEN %s
             ELSE %s
           END AS signal_weight
    FROM user_movie_prefs p
    JOIN users u
      ON u.id = p.user_id
    WHERE p.pref_type = 'like'
      AND COALESCE(p.updated_at, p.created_at) < %s
      {mock_filter_sql}
),
positive_feedback AS (
    SELECT user_id,
           mid,
           SUM(signal_weight) AS signal_weight
    FROM (
        SELECT user_id,
               mid,
               CASE
                 WHEN rating >= %s THEN %s + (rating - %s) * %s
                 ELSE %s
               END AS signal_weight
        FROM raw_positive_feedback
        UNION ALL
        SELECT user_id, mid, signal_weight
        FROM raw_preference_feedback
    ) positive_rows
    GROUP BY user_id, mid
),
seed_context AS (
    {seed_context_sql}
),
neighbor_overlap AS (
    SELECT pf.user_id AS neighbor_id,
           COUNT(DISTINCT sc.mid) AS matched_seed_count,
           SUM(SQRT(sc.seed_weight * pf.signal_weight)) AS weighted_overlap,
           AVG(pf.signal_weight) AS shared_positive_avg
    FROM positive_feedback pf
    JOIN seed_context sc
      ON sc.mid = pf.mid
    WHERE pf.user_id <> %s
    GROUP BY pf.user_id
    HAVING matched_seed_count >= %s
),
neighbor_stats AS (
    SELECT pf.user_id AS neighbor_id,
           COUNT(*) AS neighbor_positive_count,
           SUM(pf.signal_weight) AS neighbor_positive_weight
    FROM positive_feedback pf
    GROUP BY pf.user_id
),
{negative_cte_sql}
neighbor_scores AS (
    SELECT overlap.neighbor_id,
           overlap.matched_seed_count,
           overlap.shared_positive_avg,
           COALESCE(conflict.negative_conflict_count, 0) AS negative_conflict_count,
           (
             ((1.0 * overlap.weighted_overlap) / sqrt((1.0 * %s) * (1.0 * stats.neighbor_positive_weight))) *
             ((1.0 * overlap.weighted_overlap) / ((1.0 * overlap.weighted_overlap) + %s))
           ) * (1.0 + (%s * (overlap.shared_positive_avg - %s))) -
           (%s * (1.0 * COALESCE(conflict.negative_conflict_count, 0))) AS similarity
    FROM neighbor_overlap overlap
    JOIN neighbor_stats stats
      ON stats.neighbor_id = overlap.neighbor_id
    LEFT JOIN negative_conflicts conflict
      ON conflict.neighbor_id = overlap.neighbor_id
    WHERE stats.neighbor_positive_weight > 0
)
SELECT pf.mid AS movie_id,
       MAX(m.name) AS title,
       SUM(ns.similarity * SQRT(pf.signal_weight)) AS cf_score,
       COUNT(DISTINCT ns.neighbor_id) AS similar_user_count,
       MAX(ns.similarity) AS strongest_similarity,
       AVG(pf.signal_weight) AS avg_neighbor_signal
FROM neighbor_scores ns
JOIN positive_feedback pf
  ON pf.user_id = ns.neighbor_id
JOIN movies m
  ON m.douban_id = pf.mid
WHERE ns.similarity > 0
  {seen_filter_sql}
GROUP BY pf.mid
ORDER BY cf_score DESC, similar_user_count DESC, movie_id ASC
LIMIT %s
"""
    params: list[Any] = [
        STRICT_CF_POSITIVE_RATING,
        interaction_cutoff,
        user_service.LIKE_WEIGHT,
        user_service.WANT_WEIGHT,
        interaction_cutoff,
        user_service.STRONG_POSITIVE_RATING_THRESHOLD,
        user_service.STRONG_POSITIVE_RATING_BASE,
        user_service.STRONG_POSITIVE_RATING_THRESHOLD,
        user_service.STRONG_POSITIVE_RATING_STEP,
        user_service.WEAK_POSITIVE_RATING_WEIGHT,
        *seed_params,
        user_id,
        1 if len(seed_rows) < 4 else 2,
        *negative_params,
        total_seed_weight,
        STRICT_CF_SHRINKAGE,
        STRICT_CF_SIGNAL_QUALITY_BOOST,
        user_service.WEAK_POSITIVE_RATING_WEIGHT,
        STRICT_CF_NEGATIVE_CONFLICT_PENALTY,
        *seen_params,
        limit,
    ]
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    return [
        {
            "movie_id": str(row["movie_id"]),
            "title": row.get("title") or str(row["movie_id"]),
            "cf_score": float(row.get("cf_score") or 0.0),
            "similar_user_count": int(row.get("similar_user_count") or 0),
            "strongest_similarity": float(row.get("strongest_similarity") or 0.0),
            "avg_neighbor_signal": float(row.get("avg_neighbor_signal") or 0.0),
            "reasons": [_format_strict_graph_cf_reason(row)],
            "negative_signals": [],
        }
        for row in rows
        if float(row.get("cf_score") or 0.0) > 0
    ]


def rerank_strict_graph_cf_records(
    user_profile: dict[str, Any] | None,
    records: list[dict[str, Any]],
    timeout_ms: int | None,
) -> list[dict[str, Any]]:
    if not records:
        return []
    feature_map = fetch_movie_graph_profile_map(
        Neo4jConnection.get_driver(),
        [record["movie_id"] for record in records],
        timeout_ms=timeout_ms,
    )
    max_score = max(float(record["cf_score"]) for record in records) or 1.0
    reranked = []
    for record in records:
        movie_id = record["movie_id"]
        base_score = float(record["cf_score"]) / max_score
        if user_profile:
            profile_score, profile_reasons, negative_signals = score_movie_against_user_profile(
                feature_map.get(movie_id),
                user_profile,
            )
        else:
            profile_score, profile_reasons, negative_signals = 0.0, [], []
        reranked.append({
            "movie_id": movie_id,
            "title": record.get("title", ""),
            "score": 1.05 * base_score + 0.40 * profile_score,
            "reasons": [record["reasons"][0], *profile_reasons[:1]][:3],
            "negative_signals": negative_signals[:2],
            "source": "graph_cf",
        })
    reranked.sort(key=lambda item: (-item["score"], item["movie_id"]))
    return reranked


async def get_strict_graph_cf_recommendations(
    conn,
    user_id: int,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    interaction_cutoff: datetime,
    exclude_mock_users: bool,
    limit: int,
    timeout_ms: int | None,
) -> list[dict[str, Any]]:
    positive_movie_ids, positive_weights = resolve_strict_graph_cf_context(user_profile)
    negative_movie_ids = dedupe_preserve_order(user_profile.get("negative_movie_ids") or [])[:12]
    records = fetch_strict_graph_cf_records(
        conn=conn,
        user_id=user_id,
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
        negative_movie_ids=negative_movie_ids,
        seen_movie_ids=seen_movie_ids,
        interaction_cutoff=interaction_cutoff,
        exclude_mock_users=exclude_mock_users,
        limit=min(max(limit * 4, 80), 180),
    )
    return rerank_strict_graph_cf_records(
        user_profile=user_profile,
        records=records,
        timeout_ms=timeout_ms,
    )[:limit]


async def get_strict_graph_cf_recall_candidates(
    conn,
    user_id: int,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    interaction_cutoff: datetime,
    exclude_mock_users: bool,
    limit: int,
) -> list[dict[str, Any]]:
    positive_movie_ids, positive_weights = resolve_strict_graph_cf_context(user_profile)
    negative_movie_ids = dedupe_preserve_order(user_profile.get("negative_movie_ids") or [])[:12]
    records = fetch_strict_graph_cf_records(
        conn=conn,
        user_id=user_id,
        positive_movie_ids=positive_movie_ids,
        positive_weights=positive_weights,
        negative_movie_ids=negative_movie_ids,
        seen_movie_ids=seen_movie_ids,
        interaction_cutoff=interaction_cutoff,
        exclude_mock_users=exclude_mock_users,
        limit=limit,
    )
    return normalize_recall_candidates(records, score_key="cf_score", source="graph_cf")[:limit]


def merge_hybrid_branch_results(
    manager: HybridRecommendationManager,
    branch_results: dict[str, list[dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    active_weights = manager.resolve_branch_weights(branch_results)
    if not active_weights:
        return []

    normalized_results = {
        name: manager.normalize_scores(results)
        for name, results in branch_results.items()
        if name in active_weights
    }
    behavior_candidate_ids = {
        item["movie_id"]
        for name in ("graph_cf", "itemcf")
        for item in normalized_results.get(name, [])
    }
    behavior_dominant = bool(behavior_candidate_ids) and len(behavior_candidate_ids) >= max(10, limit // 2)

    movie_dict: dict[str, dict[str, Any]] = {}

    def _merge(
        branch_name: str,
        norm_list: list[dict[str, Any]],
        weight: float,
        restrict_to_ids: set[str] | None = None,
        out_of_pool_scale: float = 1.0,
        backbone_bonus: float = 0.0,
    ) -> None:
        total_items = max(len(norm_list), 1)
        for index, item in enumerate(norm_list):
            movie_id = item["movie_id"]
            effective_weight = weight
            if restrict_to_ids is not None and movie_id not in restrict_to_ids:
                effective_weight *= out_of_pool_scale
                if effective_weight <= 0:
                    continue
            if movie_id not in movie_dict:
                movie_dict[movie_id] = {
                    "movie_id": movie_id,
                    "title": item.get("title", ""),
                    "final_score": 0.0,
                    "reasons": set(),
                    "source_algorithms": set(),
                    "score_breakdown": {},
                }
            contribution = float(item["score"]) * effective_weight
            movie_dict[movie_id]["final_score"] += contribution
            movie_dict[movie_id]["source_algorithms"].add(branch_name)
            movie_dict[movie_id]["score_breakdown"][branch_name] = (
                movie_dict[movie_id]["score_breakdown"].get(branch_name, 0.0)
                + contribution
            )
            if backbone_bonus > 0:
                bonus = backbone_bonus * (1.0 - index / total_items)
                movie_dict[movie_id]["final_score"] += bonus
                movie_dict[movie_id]["score_breakdown"][branch_name] += bonus
            for reason in item.get("reasons", []):
                movie_dict[movie_id]["reasons"].add(reason)

    for branch_name, weight in active_weights.items():
        if branch_name in {"graph_cf", "itemcf"}:
            _merge(
                branch_name,
                normalized_results[branch_name],
                weight,
                backbone_bonus=(
                    0.24 if branch_name == "graph_cf" else 0.18
                ) if behavior_dominant else 0.0,
            )
            continue
        _merge(
            branch_name,
            normalized_results[branch_name],
            weight,
            restrict_to_ids=behavior_candidate_ids if behavior_dominant else None,
            out_of_pool_scale=0.22 if behavior_dominant else 1.0,
        )

    hybrid_items = []
    for item in movie_dict.values():
        hybrid_items.append({
            "movie_id": item["movie_id"],
            "title": item.get("title", ""),
            "score": float(item["final_score"]),
            "reasons": list(item["reasons"])[:3],
            "negative_signals": [],
            "source": "hybrid",
            "source_algorithms": sorted(item["source_algorithms"]),
            "score_breakdown": {
                source: round(score, 6)
                for source, score in item["score_breakdown"].items()
            },
        })
    hybrid_items.sort(key=lambda item: (-item["score"], item["movie_id"]))
    return hybrid_items[:limit]


def build_strict_cfkg_head_embedding(
    bundle: dict[str, Any],
    user_profile: dict[str, Any],
):
    torch_module, _, functional = require_torch()
    positive_movie_ids, positive_weights = resolve_positive_context(user_profile)
    if not positive_movie_ids:
        return None

    relation_id = int(bundle["relation_name_to_id"]["interact"])
    relation_vector = functional.normalize(
        bundle["model"].relation_embeddings.weight[relation_id].detach(),
        p=2,
        dim=-1,
    )

    weighted_vectors = []
    total_weight = 0.0
    for movie_id in positive_movie_ids:
        movie_key = make_entity_key("Movie", str(movie_id))
        entity_id = bundle["entity_key_to_id"].get(movie_key)
        weight = max(float(positive_weights.get(movie_id) or 0.0), 0.0)
        if entity_id is None or weight <= 0:
            continue
        movie_vector = functional.normalize(
            bundle["model"].entity_embeddings.weight[int(entity_id)].detach(),
            p=2,
            dim=-1,
        )
        weighted_vectors.append((movie_vector - relation_vector) * weight)
        total_weight += weight

    if not weighted_vectors or total_weight <= 0:
        return None
    head_vector = torch_module.stack(weighted_vectors).sum(dim=0) / total_weight
    return functional.normalize(head_vector, p=2, dim=-1)


def score_strict_cfkg_candidates(
    bundle: dict[str, Any],
    head_embedding,
    candidate_movie_ids: list[str],
) -> dict[str, float]:
    if head_embedding is None or not candidate_movie_ids:
        return {}

    torch_module, _, functional = require_torch()
    relation_id = int(bundle["relation_name_to_id"]["interact"])
    relation_vector = functional.normalize(
        bundle["model"].relation_embeddings.weight[relation_id].detach(),
        p=2,
        dim=-1,
    )

    candidate_pairs = []
    for movie_id in dedupe_preserve_order(candidate_movie_ids):
        movie_key = make_entity_key("Movie", str(movie_id))
        entity_id = bundle["entity_key_to_id"].get(movie_key)
        if entity_id is None:
            continue
        candidate_pairs.append((int(entity_id), str(movie_id)))
    if not candidate_pairs:
        return {}

    tail_ids = torch_module.tensor([item[0] for item in candidate_pairs], dtype=torch_module.long)
    with torch_module.no_grad():
        tail_vectors = functional.normalize(
            bundle["model"].entity_embeddings(tail_ids),
            p=2,
            dim=-1,
        )
        distances = (head_embedding.unsqueeze(0) + relation_vector.unsqueeze(0) - tail_vectors).abs().sum(dim=-1)
        scores = (-distances).tolist()

    raw_score_map = {
        movie_id: float(score)
        for (_, movie_id), score in zip(candidate_pairs, scores)
    }
    return normalize_score_map(raw_score_map)


def normalize_score_map(score_map: dict[str, float]) -> dict[str, float]:
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


def normalized_rank_score(index: int, total_count: int) -> float:
    if total_count <= 1:
        return 1.0
    return 1.0 - (index / max(total_count - 1, 1))


def build_overlap_feature_counts(
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


async def collect_strict_cfkg_recall_candidates(
    conn,
    user_id: int,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    interaction_cutoff: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    recall_target = min(max(limit * 6, STRICT_CFKG_RECALL_TARGET_MIN), STRICT_CFKG_RECALL_TARGET_MAX)
    minimum_viable_candidates = max(limit * 2, 40)
    cf_candidates = await get_strict_graph_cf_recall_candidates(
        conn=conn,
        user_id=user_id,
        user_profile=user_profile,
        seen_movie_ids=seen_movie_ids,
        interaction_cutoff=interaction_cutoff,
        exclude_mock_users=True,
        limit=recall_target,
    )
    itemcf_candidates = await get_strict_itemcf_recommendations(
        conn=conn,
        user_profile=user_profile,
        seen_movie_ids=seen_movie_ids,
        interaction_cutoff=interaction_cutoff,
        limit=recall_target,
    )
    merged_candidates = merge_ranked_candidates(
        cf_candidates,
        itemcf_candidates,
        limit=recall_target,
    )
    if len(merged_candidates) >= minimum_viable_candidates:
        return merged_candidates[:recall_target]
    if not has_sufficient_content_signal(user_profile):
        return merged_candidates[:recall_target]

    missing_count = max(minimum_viable_candidates - len(merged_candidates), 0)
    if missing_count < STRICT_CFKG_CONTENT_RECALL_MIN_GAP:
        return merged_candidates[:recall_target]

    content_seen_ids = dedupe_preserve_order(
        list(seen_movie_ids) + [item["movie_id"] for item in merged_candidates]
    )
    content_candidates = await get_graph_content_recall_candidates(
        user_id=user_id,
        user_profile=user_profile,
        seen_movie_ids=content_seen_ids,
        exclude_mock_users=True,
        limit=min(missing_count + 20, 80),
        timeout_ms=STRICT_CFKG_CONTENT_RECALL_TIMEOUT_MS,
    )
    return merge_ranked_candidates(
        merged_candidates,
        content_candidates,
        limit=recall_target,
    )


async def get_strict_cfkg_recommendations(
    conn,
    user_id: int,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    interaction_cutoff: datetime,
    limit: int,
    timeout_ms: int | None,
) -> list[dict[str, Any]]:
    bundle = await asyncio.to_thread(load_cfkg_model_bundle, None)
    if bundle is None:
        return []

    recall_candidates = await collect_strict_cfkg_recall_candidates(
        conn=conn,
        user_id=user_id,
        user_profile=user_profile,
        seen_movie_ids=seen_movie_ids,
        interaction_cutoff=interaction_cutoff,
        limit=limit,
    )
    if not recall_candidates:
        return []

    head_embedding = build_strict_cfkg_head_embedding(bundle, user_profile)
    score_map = score_strict_cfkg_candidates(
        bundle=bundle,
        head_embedding=head_embedding,
        candidate_movie_ids=[item["movie_id"] for item in recall_candidates],
    )
    if not score_map:
        return []

    feature_map = fetch_movie_graph_profile_map(
        Neo4jConnection.get_driver(),
        [item["movie_id"] for item in recall_candidates],
        timeout_ms=timeout_ms,
    )
    reranker_bundle = load_reranker_bundle()
    recall_rank_map = {
        item["movie_id"]: index
        for index, item in enumerate(
            sorted(
                recall_candidates,
                key=lambda item: (
                    -float(item.get("recall_score", item.get("score", 0.0))),
                    item["movie_id"],
                ),
            )
        )
    }
    cfkg_rank_map = {
        movie_id: index
        for index, (movie_id, _) in enumerate(
            sorted(score_map.items(), key=lambda item: (-float(item[1]), item[0]))
        )
    }
    rank_total_count = max(len(recall_candidates), 1)
    ranked_items = []
    for candidate in recall_candidates:
        movie_id = candidate["movie_id"]
        if movie_id not in score_map:
            continue
        recall_score = float(candidate.get("recall_score", candidate.get("score", 0.0)))
        cfkg_score = float(score_map.get(movie_id, 0.0))
        profile_score, profile_reasons, negative_signals = score_movie_against_user_profile(
            feature_map.get(movie_id),
            user_profile,
        )
        overlap_features = build_overlap_feature_counts(
            feature_map.get(movie_id),
            user_profile,
        )
        recall_sources = candidate.get("source_algorithms") or [candidate.get("source", "graph_cf")]
        reranker_features = build_reranker_feature_map(
            recall_score=recall_score,
            recall_rank_score=normalized_rank_score(
                recall_rank_map.get(movie_id, rank_total_count - 1),
                rank_total_count,
            ),
            cfkg_score=cfkg_score,
            cfkg_rank_score=normalized_rank_score(
                cfkg_rank_map.get(movie_id, rank_total_count - 1),
                rank_total_count,
            ),
            profile_score=profile_score,
            recall_sources=recall_sources,
            negative_signals=negative_signals,
            genre_overlap_count=overlap_features["genre_overlap_count"],
            director_overlap_count=overlap_features["director_overlap_count"],
            actor_overlap_count=overlap_features["actor_overlap_count"],
            negative_overlap_count=overlap_features["negative_overlap_count"],
        )
        if reranker_bundle is None:
            final_score = (
                STRICT_CFKG_RECALL_WEIGHT * recall_score
                + STRICT_CFKG_EMBEDDING_WEIGHT * cfkg_score
                + STRICT_CFKG_PROFILE_WEIGHT * profile_score
            )
            recall_share = STRICT_CFKG_RECALL_WEIGHT * recall_score / max(len(recall_sources), 1)
            score_breakdown = {
                source: round(recall_share, 6)
                for source in recall_sources
            }
            score_breakdown["cfkg"] = round(STRICT_CFKG_EMBEDDING_WEIGHT * cfkg_score, 6)
            if profile_score > 0:
                score_breakdown["profile"] = round(STRICT_CFKG_PROFILE_WEIGHT * profile_score, 6)
            ranking_reason = "使用历史正反馈电影合成 CFKG 用户表示完成精排"
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
            ranking_reason = "使用历史正反馈电影合成 CFKG 用户表示并复用 learned reranker 精排"
        ranked_items.append({
            "movie_id": movie_id,
            "title": candidate.get("title", ""),
            "score": final_score,
            "reasons": dedupe_preserve_order(
                list(candidate.get("reasons") or [])[:1]
                + [ranking_reason]
                + profile_reasons[:1]
            )[:3],
            "negative_signals": negative_signals[:2],
            "source": "cfkg",
            "source_algorithms": dedupe_preserve_order(
                list(candidate.get("source_algorithms") or [candidate.get("source", "graph_cf")]) + ["cfkg"]
            ),
            "score_breakdown": score_breakdown,
        })
    ranked_items.sort(key=lambda item: (-item["score"], item["movie_id"]))
    return ranked_items[:limit]


async def run_algorithm(
    name: str,
    manager: HybridRecommendationManager,
    conn,
    user_id: int,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    limit: int,
    protocol_name: str,
    interaction_cutoff: datetime,
) -> list[dict[str, Any]]:
    timeout_ms = EVAL_TIMEOUTS_MS[name]
    if protocol_name == STRICT_PROTOCOL:
        if name == "itemcf":
            return await get_strict_itemcf_recommendations(
                conn=conn,
                user_profile=user_profile,
                seen_movie_ids=seen_movie_ids,
                interaction_cutoff=interaction_cutoff,
                limit=limit,
            )
        if name == "tfidf":
            return await get_tfidf_recommendations(
                conn=conn,
                user_id=user_id,
                user_profile=user_profile,
                seen_movie_ids=seen_movie_ids,
                limit=limit,
                timeout_ms=timeout_ms,
            )
        if name == "cf":
            return await get_strict_graph_cf_recommendations(
                conn=conn,
                user_id=user_id,
                user_profile=user_profile,
                seen_movie_ids=seen_movie_ids,
                interaction_cutoff=interaction_cutoff,
                exclude_mock_users=True,
                limit=limit,
                timeout_ms=timeout_ms,
            )
        if name == "content":
            return await get_graph_content_recommendations(
                user_id=user_id,
                user_profile=user_profile,
                seen_movie_ids=seen_movie_ids,
                exclude_mock_users=True,
                limit=limit,
                timeout_ms=timeout_ms,
            )
        if name == "ppr":
            return await get_graph_ppr_recommendations(
                user_id=user_id,
                user_profile=user_profile,
                seen_movie_ids=seen_movie_ids,
                exclude_mock_users=True,
                limit=limit,
                timeout_ms=timeout_ms,
            )
        if name == "hybrid":
            branch_results = {
                "itemcf": await get_strict_itemcf_recommendations(
                    conn=conn,
                    user_profile=user_profile,
                    seen_movie_ids=seen_movie_ids,
                    interaction_cutoff=interaction_cutoff,
                    limit=limit * 2,
                ),
                "graph_cf": await get_strict_graph_cf_recommendations(
                    conn=conn,
                    user_id=user_id,
                    user_profile=user_profile,
                    seen_movie_ids=seen_movie_ids,
                    interaction_cutoff=interaction_cutoff,
                    exclude_mock_users=True,
                    limit=limit * 2,
                    timeout_ms=EVAL_TIMEOUTS_MS["cf"],
                ),
                "graph_content": await get_graph_content_recommendations(
                    user_id=user_id,
                    user_profile=user_profile,
                    seen_movie_ids=seen_movie_ids,
                    exclude_mock_users=True,
                    limit=limit * 2,
                    timeout_ms=EVAL_TIMEOUTS_MS["content"],
                ),
                "graph_ppr": await get_graph_ppr_recommendations(
                    user_id=user_id,
                    user_profile=user_profile,
                    seen_movie_ids=seen_movie_ids,
                    exclude_mock_users=True,
                    limit=limit * 2,
                    timeout_ms=EVAL_TIMEOUTS_MS["ppr"],
                ),
            }
            return merge_hybrid_branch_results(manager, branch_results, limit)
        if name == "cfkg":
            return await get_strict_cfkg_recommendations(
                conn=conn,
                user_id=user_id,
                user_profile=user_profile,
                seen_movie_ids=seen_movie_ids,
                interaction_cutoff=interaction_cutoff,
                limit=limit,
                timeout_ms=timeout_ms,
            )

    if name == "itemcf":
        return await get_itemcf_recommendations(
            conn=conn,
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
            timeout_ms=timeout_ms,
        )
    if name == "tfidf":
        return await get_tfidf_recommendations(
            conn=conn,
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
            timeout_ms=timeout_ms,
        )
    if name == "cfkg":
        return await get_cfkg_recommendations(
            conn=conn,
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            limit=limit,
            timeout_ms=timeout_ms,
        )
    if name == "cf":
        return await get_graph_cf_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
            timeout_ms=timeout_ms,
        )
    if name == "content":
        return await get_graph_content_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
            timeout_ms=timeout_ms,
        )
    if name == "ppr":
        return await get_graph_ppr_recommendations(
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
            timeout_ms=timeout_ms,
        )
    if name == "hybrid":
        return await manager.get_hybrid_recommendations(
            conn=conn,
            user_id=user_id,
            user_profile=user_profile,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
        )
    raise ValueError(f"未知算法: {name}")


def summarize_report(
    raw_report: dict[str, dict[str, Any]],
    catalog_movie_count: int,
) -> dict[str, dict[str, Any]]:
    summary = {}
    for algorithm, data in raw_report.items():
        cases = data["cases"]
        summary[algorithm] = {
            "cases": cases,
            "failures": data["failures"],
            "empty_cases": data["empty_cases"],
            "avg_candidates": round(data["candidate_total"] / cases, 4) if cases else 0.0,
            "precision_at_10": round(data["precision_total"] / cases, 4) if cases else 0.0,
            "recall_at_10": round(data["recall_total"] / cases, 4) if cases else 0.0,
            "ndcg_at_10": round(data["ndcg_total"] / cases, 4) if cases else 0.0,
            "coverage": round(len(data["unique_movies"]) / float(catalog_movie_count), 4)
            if catalog_movie_count
            else 0.0,
            "user_coverage": round(data["non_empty_cases"] / float(cases), 4) if cases else 0.0,
            "diversity": round(data["diversity_total"] / cases, 4) if cases else 0.0,
            "coverage_movie_count": len(data["unique_movies"]),
        }
    return summary


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    return value


def build_markdown_report(
    summary: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
) -> str:
    generated_at = metadata["generated_at"]
    algorithms = metadata["algorithms"]
    lines = [
        "# 推荐系统离线评估报告",
        "",
        f"- 生成时间: {generated_at}",
        f"- 评估协议: {metadata['protocol_name']}",
        f"- 评估用户数上限: {metadata['user_limit']}",
        f"- 推荐列表长度: {metadata['recommendation_limit']}",
        f"- 指标 Top-K: {metadata['metric_k']}",
        "",
        "## 评估协议说明",
        "",
        "- 采用用户级时间切分：按评分、喜欢、想看行为的时间顺序切分历史窗口与未来窗口。",
        "- 历史窗口用于构建用户画像，画像权重与线上推荐保持一致。",
        "- 未来窗口仅将 `rating >= 4.0` 与 `like` 视为主相关真值，`want_to_watch` 仅作为辅助行为。",
    ]
    protocol_notes = metadata.get("protocol_notes") or []
    if protocol_notes:
        lines.extend([
            "",
            "## 严格协议附加说明",
            "",
        ])
        lines.extend(f"- {note}" for note in protocol_notes)
    lines.extend([
        "",
        "## 指标总表",
        "",
        "| 算法 | Precision@10 | Recall@10 | NDCG@10 | Coverage | User Coverage | Diversity | Cases | Failures |",
        "| ---- | ------------ | --------- | ------- | -------- | ------------- | --------- | ----- | -------- |",
    ])
    for algorithm in algorithms:
        metrics = summary[algorithm]
        lines.append(
            "| {label} | {precision_at_10:.4f} | {recall_at_10:.4f} | {ndcg_at_10:.4f} | "
            "{coverage:.4f} | {user_coverage:.4f} | {diversity:.4f} | {cases} | {failures} |".format(
                label=ALGORITHM_DESCRIPTIONS[algorithm]["label"],
                **metrics,
            )
        )

    lines.extend([
        "",
        "## 算法分析",
        "",
    ])
    ranked_algorithms = sorted(
        algorithms,
        key=lambda name: (
            -summary[name]["ndcg_at_10"],
            -summary[name]["recall_at_10"],
            name,
        ),
    )
    for algorithm in ranked_algorithms:
        desc = ALGORITHM_DESCRIPTIONS[algorithm]
        metrics = summary[algorithm]
        lines.extend([
            f"### {desc['label']}",
            "",
            f"- 定位: {desc['summary']}",
            f"- 优点: {desc['strength']}",
            f"- 局限: {desc['weakness']}",
            (
                f"- 本次结果: Precision@10={metrics['precision_at_10']:.4f}, "
                f"Recall@10={metrics['recall_at_10']:.4f}, "
                f"NDCG@10={metrics['ndcg_at_10']:.4f}, "
                f"Coverage={metrics['coverage']:.4f}, "
                f"Diversity={metrics['diversity']:.4f}"
            ),
            "",
        ])

    best_algorithm = ranked_algorithms[0] if ranked_algorithms else None
    lines.extend([
        "## 推荐结论",
        "",
    ])
    if best_algorithm:
        lines.append(
            (
                f"- 在当前协议下，综合 NDCG@10 和 Recall@10 表现最优的算法为 "
                f"`{ALGORITHM_DESCRIPTIONS[best_algorithm]['label']}`。"
            )
        )
    lines.append("- `CFKG` 仍建议作为线上主推荐链路，传统基线主要承担论文对照角色。")
    if metadata.get("cfkg_evaluation_mode"):
        lines.append("- 严格协议下的 `CFKG` 采用历史正反馈合成用户表示并复用 learned reranker，不等价于按同一时间快照完整重训后的线上模型。")
    lines.append("- `ItemCF` 与 `TF-IDF` 可分别作为行为基线与纯内容基线，便于说明知识图谱算法的增益。")
    lines.append("")
    return "\n".join(lines)


def write_report_files(report_payload: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(
        json.dumps(_json_safe(report_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    REPORT_MD_PATH.write_text(
        build_markdown_report(report_payload["summary"], report_payload["metadata"]),
        encoding="utf-8",
    )
    return REPORT_JSON_PATH, REPORT_MD_PATH


def parse_algorithm_names(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_ALGORITHMS)
    alias_map = {
        "tf-idf": "tfidf",
    }
    names = []
    for item in value.split(","):
        normalized = alias_map.get(item.strip().lower(), item.strip().lower())
        if not normalized:
            continue
        if normalized not in DEFAULT_ALGORITHMS:
            raise ValueError(f"未知算法: {normalized}")
        names.append(normalized)
    return dedupe_preserve_order(names) or list(DEFAULT_ALGORITHMS)


async def evaluate_algorithms(
    user_limit: int = 100,
    recommendation_limit: int = 50,
    algorithms: list[str] | None = None,
    protocol_name: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    algorithms = algorithms or list(DEFAULT_ALGORITHMS)
    manager = HybridRecommendationManager(
        branch_timeouts_ms={
            "graph_cf": EVAL_TIMEOUTS_MS["cf"],
            "graph_content": EVAL_TIMEOUTS_MS["content"],
            "graph_ppr": EVAL_TIMEOUTS_MS["ppr"],
        }
    )
    raw_report = {
        name: {
            "cases": 0,
            "failures": 0,
            "empty_cases": 0,
            "non_empty_cases": 0,
            "candidate_total": 0.0,
            "precision_total": 0.0,
            "recall_total": 0.0,
            "ndcg_total": 0.0,
            "diversity_total": 0.0,
            "unique_movies": set(),
        }
        for name in algorithms
    }

    init_pool()
    conn = get_connection()
    movie_genre_cache: dict[str, set[str]] = {}
    catalog_movie_count = fetch_movie_catalog_count(conn)
    valid_case_count = 0
    try:
        for user_id in fetch_candidate_user_ids(conn, limit=user_limit):
            rating_rows = fetch_user_rating_rows(conn, user_id)
            pref_rows = fetch_user_pref_rows(conn, user_id)
            case = build_time_split_case(rating_rows, pref_rows)
            if not case:
                continue

            user_profile = build_profile_from_history(
                history_rating_rows=case["history_rating_rows"],
                history_pref_rows=case["history_pref_rows"],
            )
            relevant_movie_ids = set(case["future_relevant_movie_ids"]) - set(
                user_profile.get("hard_exclude_movie_ids") or []
            )
            if not relevant_movie_ids:
                continue

            seen_movie_ids = dedupe_preserve_order(user_profile.get("hard_exclude_movie_ids") or [])
            valid_case_count += 1

            for algorithm in algorithms:
                try:
                    items = await run_algorithm(
                        name=algorithm,
                        manager=manager,
                        conn=conn,
                        user_id=user_id,
                        user_profile=user_profile,
                        seen_movie_ids=seen_movie_ids,
                        limit=recommendation_limit,
                        protocol_name=protocol_name,
                        interaction_cutoff=case["split_time"],
                    )
                except Exception as exc:
                    logger.warning("算法 %s 在用户 %s 上评估失败: %s", algorithm, user_id, exc)
                    raw_report[algorithm]["failures"] += 1
                    items = []

                raw_report[algorithm]["cases"] += 1
                raw_report[algorithm]["candidate_total"] += len(items)
                if not items:
                    raw_report[algorithm]["empty_cases"] += 1
                else:
                    raw_report[algorithm]["non_empty_cases"] += 1
                raw_report[algorithm]["unique_movies"].update(
                    str(item["movie_id"]) for item in items
                )

                top_movie_ids = [str(item["movie_id"]) for item in items[:METRIC_K]]
                missing_movie_ids = [
                    movie_id
                    for movie_id in top_movie_ids
                    if movie_id not in movie_genre_cache
                ]
                if missing_movie_ids:
                    movie_genre_cache.update(fetch_movie_genre_map(conn, missing_movie_ids))

                raw_report[algorithm]["precision_total"] += precision_at_k(
                    items,
                    relevant_movie_ids,
                    METRIC_K,
                )
                raw_report[algorithm]["recall_total"] += recall_at_k(
                    items,
                    relevant_movie_ids,
                    METRIC_K,
                )
                raw_report[algorithm]["ndcg_total"] += ndcg_at_k(
                    items,
                    relevant_movie_ids,
                    METRIC_K,
                )
                raw_report[algorithm]["diversity_total"] += diversity_at_k(
                    items,
                    movie_genre_cache,
                    METRIC_K,
                )
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol_name": protocol_name,
        "user_limit": user_limit,
        "recommendation_limit": recommendation_limit,
        "metric_k": METRIC_K,
        "algorithms": algorithms,
        "catalog_movie_count": catalog_movie_count,
        "valid_case_count": valid_case_count,
    }
    if protocol_name == STRICT_PROTOCOL:
        metadata["protocol_notes"] = list(STRICT_PROTOCOL_NOTES)
        metadata["cfkg_evaluation_mode"] = (
            "history_head_with_learned_reranker"
            if load_reranker_bundle() is not None
            else "history_head_without_learned_reranker"
        )
    summary = summarize_report(raw_report, catalog_movie_count=catalog_movie_count)
    return {
        "metadata": metadata,
        "summary": summary,
        "raw_report": raw_report,
    }


def print_report(report: dict[str, Any]) -> None:
    print("推荐离线评估结果")
    print("=" * 80)
    print(f"generated_at: {report['metadata']['generated_at']}")
    print(f"protocol: {report['metadata']['protocol_name']}")
    print(f"valid_cases: {report['metadata']['valid_case_count']}")
    print()
    for algorithm in report["metadata"]["algorithms"]:
        metrics = report["summary"][algorithm]
        print(f"[{ALGORITHM_DESCRIPTIONS[algorithm]['label']}]")
        print(f"  cases: {metrics['cases']}")
        print(f"  failures: {metrics['failures']}")
        print(f"  empty_cases: {metrics['empty_cases']}")
        print(f"  precision@10: {metrics['precision_at_10']}")
        print(f"  recall@10: {metrics['recall_at_10']}")
        print(f"  ndcg@10: {metrics['ndcg_at_10']}")
        print(f"  coverage: {metrics['coverage']}")
        print(f"  user_coverage: {metrics['user_coverage']}")
        print(f"  diversity: {metrics['diversity']}")
        print()


def parse_args():
    parser = argparse.ArgumentParser(description="离线评估推荐算法")
    parser.add_argument("--user-limit", type=int, default=100)
    parser.add_argument("--recommendation-limit", type=int, default=50)
    parser.add_argument(
        "--protocol",
        default=DEFAULT_PROTOCOL,
        choices=[STRICT_PROTOCOL, LEGACY_PROTOCOL],
        help=f"评估协议，可选: {STRICT_PROTOCOL}, {LEGACY_PROTOCOL}",
    )
    parser.add_argument(
        "--algorithm",
        default="itemcf,tfidf,cf,content,ppr,hybrid,cfkg",
        help="逗号分隔的算法列表，例如 itemcf,tfidf,cf,content,ppr,hybrid,cfkg",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    report = await evaluate_algorithms(
        user_limit=args.user_limit,
        recommendation_limit=args.recommendation_limit,
        algorithms=parse_algorithm_names(args.algorithm),
        protocol_name=args.protocol,
    )
    json_path, md_path = write_report_files(report)
    print_report(report)
    print(f"json_report={json_path}")
    print(f"markdown_report={md_path}")


if __name__ == "__main__":
    asyncio.run(main())
