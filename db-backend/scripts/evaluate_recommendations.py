#!/usr/bin/env python3
"""
基于时间切分的离线推荐评估脚本。
"""
import asyncio
import os
import sys
from statistics import mean

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_content import get_graph_content_recommendations
from app.algorithms.graph_ppr import get_graph_ppr_recommendations
from app.algorithms.hybrid_manager import HybridRecommendationManager
from app.db.mysql import close_pool, get_connection, init_pool
from app.db.neo4j import Neo4jConnection

EVAL_LIMITS = (10, 20, 50)
POSITIVE_RATING = 4.0
EVAL_TIMEOUTS_MS = {
    "cf": 1500,
    "content": 8000,
    "ppr": 12000,
}


def dedupe_movie_ids(movie_ids):
    seen = set()
    items = []
    for movie_id in movie_ids:
        if movie_id in seen:
            continue
        seen.add(movie_id)
        items.append(movie_id)
    return items


def build_time_split_case(rows):
    holdout_index = None
    for index, row in enumerate(rows):
        if float(row["rating"]) >= POSITIVE_RATING:
            holdout_index = index

    if holdout_index is None or holdout_index == 0:
        return None

    history_rows = rows[:holdout_index]
    positive_seed_ids = dedupe_movie_ids(
        [row["mid"] for row in history_rows if float(row["rating"]) >= POSITIVE_RATING]
    )
    seed_movie_ids = list(reversed(positive_seed_ids[-5:]))
    if not seed_movie_ids:
        return None

    holdout_row = rows[holdout_index]
    seen_movie_ids = dedupe_movie_ids([row["mid"] for row in history_rows])
    return {
        "user_id": rows[0]["user_id"],
        "holdout_movie_id": holdout_row["mid"],
        "seed_movie_ids": seed_movie_ids,
        "seen_movie_ids": seen_movie_ids,
    }


def hit_at_k(items, holdout_movie_id: str, k: int) -> float:
    top_k_movie_ids = [item["movie_id"] for item in items[:k]]
    return 1.0 if holdout_movie_id in top_k_movie_ids else 0.0


def fetch_candidate_user_ids(conn, limit: int = 100):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE status = 'active' AND is_mock = 0 ORDER BY id ASC LIMIT %s",
            (limit,),
        )
        return [row["id"] for row in cursor.fetchall()]


def fetch_user_rating_rows(conn, user_id: int):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, user_id, mid, rating, rated_at, updated_at "
            "FROM user_movie_ratings "
            "WHERE user_id = %s "
            "ORDER BY COALESCE(updated_at, rated_at) ASC, rated_at ASC, id ASC",
            (user_id,),
        )
        return cursor.fetchall()


async def run_algorithm(name, manager, user_id, seed_movie_ids, seen_movie_ids, limit):
    if name == "cf":
        return await get_graph_cf_recommendations(
            user_id=user_id,
            seed_movie_ids=seed_movie_ids,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
            timeout_ms=EVAL_TIMEOUTS_MS["cf"],
        )
    if name == "content":
        return await get_graph_content_recommendations(
            user_id=user_id,
            seed_movie_ids=seed_movie_ids,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
            timeout_ms=EVAL_TIMEOUTS_MS["content"],
        )
    if name == "ppr":
        return await get_graph_ppr_recommendations(
            user_id=user_id,
            seed_movie_ids=seed_movie_ids,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
            timeout_ms=EVAL_TIMEOUTS_MS["ppr"],
        )
    if name == "hybrid":
        return await manager.get_hybrid_recommendations(
            user_id=user_id,
            seed_movie_ids=seed_movie_ids,
            seen_movie_ids=seen_movie_ids,
            exclude_mock_users=True,
            limit=limit,
        )
    raise ValueError(f"未知算法: {name}")


def summarize_report(raw_report):
    summary = {}
    for algorithm, data in raw_report.items():
        cases = data["cases"]
        summary[algorithm] = {
            "cases": cases,
            "avg_candidates": round(mean(data["candidate_sizes"]), 2) if data["candidate_sizes"] else 0.0,
            "coverage": len(data["unique_movies"]),
        }
        for k in EVAL_LIMITS:
            metric_name = f"hit_rate@{k}"
            summary[algorithm][metric_name] = round(data["hits"][k] / cases, 4) if cases else 0.0
    return summary


async def evaluate_algorithms(user_limit: int = 100, recommendation_limit: int = 50):
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
            "hits": {k: 0.0 for k in EVAL_LIMITS},
            "candidate_sizes": [],
            "unique_movies": set(),
        }
        for name in ("cf", "content", "ppr", "hybrid")
    }

    init_pool()
    conn = get_connection()
    try:
        for user_id in fetch_candidate_user_ids(conn, limit=user_limit):
            case = build_time_split_case(fetch_user_rating_rows(conn, user_id))
            if not case:
                continue

            for algorithm in raw_report:
                items = await run_algorithm(
                    algorithm,
                    manager,
                    case["user_id"],
                    case["seed_movie_ids"],
                    case["seen_movie_ids"],
                    recommendation_limit,
                )
                raw_report[algorithm]["cases"] += 1
                raw_report[algorithm]["candidate_sizes"].append(len(items))
                raw_report[algorithm]["unique_movies"].update(item["movie_id"] for item in items)
                for k in EVAL_LIMITS:
                    raw_report[algorithm]["hits"][k] += hit_at_k(items, case["holdout_movie_id"], k)
    finally:
        conn.close()
        close_pool()
        Neo4jConnection.close()

    return summarize_report(raw_report)


def print_report(report):
    print("推荐离线评估结果")
    print("=" * 60)
    for algorithm, metrics in report.items():
        print(f"[{algorithm}]")
        print(f"  cases: {metrics['cases']}")
        print(f"  avg_candidates: {metrics['avg_candidates']}")
        print(f"  coverage: {metrics['coverage']}")
        for k in EVAL_LIMITS:
            print(f"  hit_rate@{k}: {metrics[f'hit_rate@{k}']}")
        print()


async def main():
    report = await evaluate_algorithms()
    print_report(report)


if __name__ == "__main__":
    asyncio.run(main())
