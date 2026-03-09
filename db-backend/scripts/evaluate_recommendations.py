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
from app.algorithms.common import (
    build_weighted_user_profile,
    dedupe_preserve_order,
    fetch_movie_graph_profile_map,
    split_multi_value,
)
from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_content import get_graph_content_recommendations
from app.algorithms.graph_ppr import get_graph_ppr_recommendations
from app.algorithms.hybrid_manager import HybridRecommendationManager
from app.algorithms.item_cf import get_itemcf_recommendations
from app.algorithms.tfidf_content import get_tfidf_recommendations
from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection
from app.services import user_service

logger = logging.getLogger(__name__)
DEFAULT_ALGORITHMS = ["itemcf", "tfidf", "cf", "content", "ppr", "hybrid", "cfkg"]
REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_JSON_PATH = REPORT_DIR / "recommendation_eval_latest.json"
REPORT_MD_PATH = REPORT_DIR / "recommendation_eval_latest.md"
POSITIVE_RATING = 4.0
METRIC_K = 10
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


async def run_algorithm(
    name: str,
    manager: HybridRecommendationManager,
    conn,
    user_id: int,
    user_profile: dict[str, Any],
    seen_movie_ids: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    timeout_ms = EVAL_TIMEOUTS_MS[name]
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
        "",
        "## 指标总表",
        "",
        "| 算法 | Precision@10 | Recall@10 | NDCG@10 | Coverage | User Coverage | Diversity | Cases | Failures |",
        "| ---- | ------------ | --------- | ------- | -------- | ------------- | --------- | ----- | -------- |",
    ]
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
        "protocol_name": "profile_based_time_split",
        "user_limit": user_limit,
        "recommendation_limit": recommendation_limit,
        "metric_k": METRIC_K,
        "algorithms": algorithms,
        "catalog_movie_count": catalog_movie_count,
        "valid_case_count": valid_case_count,
    }
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
    )
    json_path, md_path = write_report_files(report)
    print_report(report)
    print(f"json_report={json_path}")
    print(f"markdown_report={md_path}")


if __name__ == "__main__":
    asyncio.run(main())
