"""
Offline evaluation for recommendation algorithms.

Protocol:
1. Build leave-one-out positives from ratings >= threshold.
2. Split eligible users into validation/test subsets.
3. Tune configurable algorithms on validation split only.
4. Report 5-seed sampled leave-one-out means/stds on the held-out test split.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean, pstdev

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.algorithms.graph_cache import GraphMetadataCache
from app.db.mysql import get_connection, init_pool
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

K_VALUES = [5, 10, 20]
POSITIVE_THRESHOLD = 3.5
NUM_NEGATIVES = 99
USER_SPLIT_SEED = 42
VALIDATION_RATIO = 0.2
NEGATIVE_SAMPLE_SEEDS = [42, 52, 62, 72, 82]
LEGACY_NEGATIVE_SEED = 42
SINGLE_POSITIVE_METRIC_NOTE = (
    "当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；"
    "因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。"
)
USER_SOURCE_CHOICES = ("all", "public", "seed_cfkg", "non_public")
USER_SOURCE_LABELS = {
    "all": "全量用户（真实公开 + 历史 mock）",
    "public": "公开豆瓣用户（douban_public_*)",
    "seed_cfkg": "历史 mock 用户（seed_cfkg_*)",
    "non_public": "非公开导入用户（排除 douban_public_*）",
}


def _build_progress_label(
    stage: str,
    display_name: str,
    *,
    current: int | None = None,
    total: int | None = None,
    detail: str | None = None,
) -> str:
    label = stage
    if current is not None and total is not None:
        label = f"{label}[{current}/{total}]"
    if detail:
        return f"  {label} {display_name} - {detail}"
    return f"  {label} {display_name}"


def describe_user_source(user_source: str) -> str:
    try:
        return USER_SOURCE_LABELS[user_source]
    except KeyError as exc:
        raise ValueError(f"Unsupported user source: {user_source}") from exc


def _ratings_query_for_user_source(user_source: str) -> tuple[str, tuple[str, ...]]:
    query = (
        "SELECT r.user_id, r.mid, r.rating, r.rated_at "
        "FROM user_movie_ratings r "
        "JOIN users u ON u.id = r.user_id "
    )
    if user_source == "all":
        return query + "ORDER BY r.user_id, r.rated_at ASC", ()
    if user_source == "public":
        return query + "WHERE u.username LIKE %s ORDER BY r.user_id, r.rated_at ASC", ("douban_public_%",)
    if user_source == "seed_cfkg":
        return query + "WHERE u.username LIKE %s ORDER BY r.user_id, r.rated_at ASC", ("seed_cfkg_%",)
    if user_source == "non_public":
        return query + "WHERE u.username NOT LIKE %s ORDER BY r.user_id, r.rated_at ASC", ("douban_public_%",)
    raise ValueError(f"Unsupported user source: {user_source}")


def _ndcg_at_k(ranked_list: list[str], relevant: set[str], k: int) -> float:
    dcg = 0.0
    for idx, mid in enumerate(ranked_list[:k]):
        if mid in relevant:
            dcg += 1.0 / math.log2(idx + 2)
    return dcg


def _movie_signature(mid: str) -> set[str]:
    per_relation = GraphMetadataCache.movie_entities(
        mid,
        with_relation_tokens=True,
        actor_top_only=True,
    )
    signature = set()
    for tokens in per_relation.values():
        signature |= tokens
    return signature


def _diversity_at_k(ranked_list: list[str], k: int) -> float:
    mids = ranked_list[:k]
    if len(mids) < 2:
        return 0.0
    signatures = [_movie_signature(mid) for mid in mids]
    pair_scores = []
    for idx in range(len(signatures)):
        for jdx in range(idx + 1, len(signatures)):
            left = signatures[idx]
            right = signatures[jdx]
            union = left | right
            if not union:
                pair_scores.append(1.0)
                continue
            similarity = len(left & right) / len(union)
            pair_scores.append(1.0 - similarity)
    return sum(pair_scores) / len(pair_scores) if pair_scores else 0.0


def build_evaluation_users(*, user_source: str = "all") -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        ratings_query, ratings_params = _ratings_query_for_user_source(user_source)
        with conn.cursor() as cursor:
            cursor.execute(ratings_query, ratings_params)
            all_ratings = cursor.fetchall()
        with conn.cursor() as cursor:
            cursor.execute("SELECT douban_id FROM movies WHERE douban_id IS NOT NULL")
            all_movie_mids = [str(row["douban_id"]) for row in cursor.fetchall()]
    finally:
        conn.close()

    all_movie_mids_set = set(all_movie_mids)
    user_ratings: dict[int, list[dict]] = defaultdict(list)
    for row in all_ratings:
        user_ratings[row["user_id"]].append(row)

    evaluation_users = []
    for uid in sorted(user_ratings):
        ratings = user_ratings[uid]
        if len(ratings) < 3:
            continue
        positive_ratings = [row for row in ratings if float(row["rating"]) >= POSITIVE_THRESHOLD]
        if len(positive_ratings) < 2:
            continue

        test_item = positive_ratings[-1]
        test_mid = str(test_item["mid"])
        user_rated_mids = {str(row["mid"]) for row in ratings if str(row["mid"]) != test_mid}
        candidate_negatives = sorted(all_movie_mids_set - user_rated_mids - {test_mid})
        if len(candidate_negatives) < NUM_NEGATIVES:
            continue

        sampled_negatives = {}
        for seed in NEGATIVE_SAMPLE_SEEDS:
            rng = random.Random(seed + uid)
            sampled_negatives[seed] = rng.sample(candidate_negatives, NUM_NEGATIVES)

        evaluation_users.append(
            {
                "user_id": uid,
                "test_mid": test_mid,
                "sampled_negatives": sampled_negatives,
            }
        )

    return evaluation_users, len(all_movie_mids)


def split_evaluation_users(evaluation_users: list[dict]) -> tuple[list[dict], list[dict]]:
    shuffled = sorted(evaluation_users, key=lambda item: item["user_id"])
    rng = random.Random(USER_SPLIT_SEED)
    rng.shuffle(shuffled)
    val_size = max(1, int(len(shuffled) * VALIDATION_RATIO))
    validation_users = sorted(shuffled[:val_size], key=lambda item: item["user_id"])
    test_users = sorted(shuffled[val_size:], key=lambda item: item["user_id"])
    return validation_users, test_users


def rank_sampled_candidates(recommendations: list[dict], test_mid: str, candidate_mids: list[str]) -> list[str]:
    candidate_set = set(candidate_mids) | {test_mid}
    sampled = [row for row in recommendations if row["mid"] in candidate_set]
    scored_mids = {row["mid"] for row in sampled}
    for mid in candidate_set:
        if mid not in scored_mids:
            sampled.append({"mid": mid, "score": 0.0, "reason": ""})
    sampled.sort(key=lambda item: (-float(item["score"]), item["mid"]))
    return [row["mid"] for row in sampled]


def evaluate_algorithm(
    algo,
    evaluation_users: list[dict],
    *,
    negative_seeds: list[int],
    k_values: list[int],
    all_movie_count: int,
    progress_label: str,
) -> dict:
    from tqdm import tqdm

    per_seed = {
        seed: {
            "users": 0,
            "k": {
                k: {"hits": 0, "precision_sum": 0.0, "recall_sum": 0.0, "ndcg_sum": 0.0}
                for k in k_values
            },
            "coverage_mids": set(),
            "diversity_sum": 0.0,
        }
        for seed in negative_seeds
    }

    total_time = 0.0
    successful_users = 0

    for test_case in tqdm(evaluation_users, desc=progress_label, leave=False, ncols=90):
        user_id = test_case["user_id"]
        test_mid = test_case["test_mid"]
        try:
            start_time = time.time()
            recommendations = algo.recommend(
                user_id=user_id,
                n=99999,
                exclude_mids=None,
                exclude_from_training={test_mid},
            )
            total_time += time.time() - start_time
            successful_users += 1
        except Exception as exc:
            logger.warning("算法 %s 对用户 %s 推荐失败: %s", algo.name, user_id, exc)
            continue

        for seed in negative_seeds:
            ranked_mids = rank_sampled_candidates(
                recommendations=recommendations,
                test_mid=test_mid,
                candidate_mids=test_case["sampled_negatives"][seed],
            )
            relevant = {test_mid}
            per_seed[seed]["users"] += 1
            per_seed[seed]["diversity_sum"] += _diversity_at_k(ranked_mids, 10)
            per_seed[seed]["coverage_mids"].update(ranked_mids[:20])

            for k in k_values:
                top_k = ranked_mids[:k]
                hit = 1 if test_mid in top_k else 0
                per_seed[seed]["k"][k]["hits"] += hit
                per_seed[seed]["k"][k]["precision_sum"] += hit / k
                per_seed[seed]["k"][k]["recall_sum"] += hit
                per_seed[seed]["k"][k]["ndcg_sum"] += _ndcg_at_k(ranked_mids, relevant, k)

    return summarize_metrics(
        per_seed=per_seed,
        k_values=k_values,
        all_movie_count=all_movie_count,
        total_time=total_time,
        successful_users=successful_users,
        negative_seeds=negative_seeds,
    )


def summarize_metrics(
    *,
    per_seed: dict,
    k_values: list[int],
    all_movie_count: int,
    total_time: float,
    successful_users: int,
    negative_seeds: list[int],
) -> dict:
    seed_metrics = {}
    for seed in negative_seeds:
        seed_data = per_seed[seed]
        users = seed_data["users"]
        if users == 0:
            seed_metrics[str(seed)] = {
                "users": 0,
                "metrics": {str(k): {"precision": 0.0, "recall": 0.0, "ndcg": 0.0, "hit_rate": 0.0} for k in k_values},
                "coverage_at_20": 0.0,
                "diversity_at_10": 0.0,
            }
            continue

        seed_metrics[str(seed)] = {
            "users": users,
            "metrics": {
                str(k): {
                    "precision": round(seed_data["k"][k]["precision_sum"] / users, 4),
                    "recall": round(seed_data["k"][k]["recall_sum"] / users, 4),
                    "ndcg": round(seed_data["k"][k]["ndcg_sum"] / users, 4),
                    "hit_rate": round(seed_data["k"][k]["hits"] / users, 4),
                }
                for k in k_values
            },
            "coverage_at_20": round(len(seed_data["coverage_mids"]) / max(all_movie_count, 1), 4),
            "diversity_at_10": round(seed_data["diversity_sum"] / users, 4),
        }

    aggregate_metrics = {}
    for k in k_values:
        aggregate_metrics[str(k)] = {}
        for metric_name in ("precision", "recall", "ndcg", "hit_rate"):
            values = [seed_metrics[str(seed)]["metrics"][str(k)][metric_name] for seed in negative_seeds]
            aggregate_metrics[str(k)][metric_name] = round(mean(values), 4)
            aggregate_metrics[str(k)][f"{metric_name}_std"] = round(pstdev(values), 4) if len(values) > 1 else 0.0

    coverage_values = [seed_metrics[str(seed)]["coverage_at_20"] for seed in negative_seeds]
    diversity_values = [seed_metrics[str(seed)]["diversity_at_10"] for seed in negative_seeds]

    return {
        "metrics": aggregate_metrics,
        "per_seed": seed_metrics,
        "coverage_at_20": {
            "mean": round(mean(coverage_values), 4),
            "std": round(pstdev(coverage_values), 4) if len(coverage_values) > 1 else 0.0,
        },
        "diversity_at_10": {
            "mean": round(mean(diversity_values), 4),
            "std": round(pstdev(diversity_values), 4) if len(diversity_values) > 1 else 0.0,
        },
        "time_seconds": round(total_time, 2),
        "avg_time_seconds": round(total_time / max(successful_users, 1), 4),
        "n_users": successful_users,
    }


def select_best_config(validation_results: dict) -> tuple[dict, dict]:
    scored = []
    for params_key, payload in validation_results.items():
        metrics = payload["metrics"]
        scored.append(
            (
                metrics["10"]["ndcg"],
                metrics["10"]["hit_rate"],
                metrics["5"]["ndcg"],
                params_key,
                payload,
            )
        )
    scored.sort(reverse=True)
    best = scored[0]
    return deepcopy(best[4]["params"]), best[4]


def tune_algorithm(algo_class, validation_users: list[dict], all_movie_count: int) -> tuple[dict, dict]:
    param_grid = algo_class.parameter_grid()
    if len(param_grid) <= 1:
        return {}, {}

    algo = algo_class()
    validation_results = {}
    print(
        f"  🔍 验证集网格搜索: {len(param_grid)} 组参数 × {len(validation_users)} 用户"
    )
    for idx, params in enumerate(param_grid, start=1):
        if params:
            algo.set_params(**params)
        result = evaluate_algorithm(
            algo=algo,
            evaluation_users=validation_users,
            negative_seeds=NEGATIVE_SAMPLE_SEEDS,
            k_values=K_VALUES,
            all_movie_count=all_movie_count,
            progress_label=_build_progress_label(
                "验证",
                algo.display_name,
                current=idx,
                total=len(param_grid),
            ),
        )
        params_key = json.dumps(params, ensure_ascii=False, sort_keys=True)
        validation_results[params_key] = {"params": deepcopy(params), **result}

    return select_best_config(validation_results)


def evaluate_suite(*, user_source: str = "all") -> dict:
    from app.algorithms import ALGORITHMS

    print("=" * 78)
    print("🧪 推荐算法离线评估 (Validation + 5-seed Sampled Leave-One-Out)")
    print("=" * 78)
    print(f"  评估方法: 1 正样本 + {NUM_NEGATIVES} 随机负样本，共 {NUM_NEGATIVES + 1} 个候选")
    print(f"  测试负采样 seeds: {NEGATIVE_SAMPLE_SEEDS}")
    print(f"  用户来源: {describe_user_source(user_source)}")

    print("\n📊 准备评估数据...")
    evaluation_users, all_movie_count = build_evaluation_users(user_source=user_source)
    validation_users, test_users = split_evaluation_users(evaluation_users)
    print(f"  符合条件用户数: {len(evaluation_users)}")
    print(f"  验证集用户数: {len(validation_users)}")
    print(f"  测试集用户数: {len(test_users)}")

    if not test_users:
        raise RuntimeError("没有足够的用户用于离线评估")

    main_results = {}
    legacy_results = {}

    for algo_name, algo_class in ALGORITHMS.items():
        print(f"\n🔄 评估算法: {algo_class.display_name} ({algo_name})...")
        best_params = {}
        validation_summary = {}
        if len(algo_class.parameter_grid()) > 1 and validation_users:
            best_params, validation_summary = tune_algorithm(
                algo_class=algo_class,
                validation_users=validation_users,
                all_movie_count=all_movie_count,
            )
            print(f"  🎯 验证集最优参数: {best_params}")

        algo = algo_class()
        if best_params:
            algo.set_params(**best_params)

        print(f"  🧪 测试集评估: {len(test_users)} 用户 × {len(NEGATIVE_SAMPLE_SEEDS)} 个负采样 seed")
        test_summary = evaluate_algorithm(
            algo=algo,
            evaluation_users=test_users,
            negative_seeds=NEGATIVE_SAMPLE_SEEDS,
            k_values=K_VALUES,
            all_movie_count=all_movie_count,
            progress_label=_build_progress_label("测试", algo.display_name, detail="main"),
        )

        ablations = {}
        ablation_items = list(algo_class.ablation_configs().items())
        if ablation_items:
            print(f"  🧩 消融实验: {len(ablation_items)} 组配置 × {len(test_users)} 用户")
        for idx, (label, ablation_params) in enumerate(ablation_items, start=1):
            ablation_algo = algo_class()
            merged_params = {**best_params, **ablation_params}
            if merged_params:
                ablation_algo.set_params(**merged_params)
            ablations[label] = evaluate_algorithm(
                algo=ablation_algo,
                evaluation_users=test_users,
                negative_seeds=NEGATIVE_SAMPLE_SEEDS,
                k_values=K_VALUES,
                all_movie_count=all_movie_count,
                progress_label=_build_progress_label(
                    "消融",
                    algo.display_name,
                    current=idx,
                    total=len(ablation_items),
                    detail=label,
                ),
            )
            ablations[label]["params"] = merged_params

        print(f"  📎 Legacy 对照: {len(test_users)} 用户 × seed {LEGACY_NEGATIVE_SEED}")
        legacy_summary = evaluate_algorithm(
            algo=algo,
            evaluation_users=test_users,
            negative_seeds=[LEGACY_NEGATIVE_SEED],
            k_values=K_VALUES,
            all_movie_count=all_movie_count,
            progress_label=_build_progress_label(
                "Legacy",
                algo.display_name,
                detail=f"seed={LEGACY_NEGATIVE_SEED}",
            ),
        )

        main_results[algo_name] = {
            "display_name": algo_class.display_name,
            "metrics": test_summary["metrics"],
            "coverage_at_20": test_summary["coverage_at_20"],
            "diversity_at_10": test_summary["diversity_at_10"],
            "time_seconds": test_summary["time_seconds"],
            "avg_time_seconds": test_summary["avg_time_seconds"],
            "n_test_users": test_summary["n_users"],
            "best_params": best_params,
            "validation_summary": validation_summary,
            "per_seed": test_summary["per_seed"],
            "ablations": ablations,
        }
        legacy_results[algo_name] = {
            "display_name": algo_class.display_name,
            "metrics": legacy_summary["metrics"],
            "coverage_at_20": legacy_summary["coverage_at_20"],
            "diversity_at_10": legacy_summary["diversity_at_10"],
            "time_seconds": legacy_summary["time_seconds"],
            "avg_time_seconds": legacy_summary["avg_time_seconds"],
            "n_test_users": legacy_summary["n_users"],
            "negative_seed": LEGACY_NEGATIVE_SEED,
        }
        print(f"  ✅ 完成 ({test_summary['time_seconds']}s)")

    generated_at = datetime.now(timezone.utc).astimezone().isoformat()
    report = {
        "protocol_version": 2,
        "generated_at": generated_at,
        "eval_method": f"validation_and_test_sampled_leave_one_out (1_positive + {NUM_NEGATIVES}_negatives)",
        "user_source": user_source,
        "user_source_display": describe_user_source(user_source),
        "user_split_seed": USER_SPLIT_SEED,
        "negative_sample_seeds": NEGATIVE_SAMPLE_SEEDS,
        "n_total_users": len(evaluation_users),
        "n_validation_users": len(validation_users),
        "n_test_users": len(test_users),
        "results": main_results,
    }
    legacy_report = {
        "protocol_version": 1,
        "generated_at": generated_at,
        "eval_method": f"single_seed_sampled_leave_one_out (seed={LEGACY_NEGATIVE_SEED})",
        "user_source": user_source,
        "user_source_display": describe_user_source(user_source),
        "negative_sample_seeds": [LEGACY_NEGATIVE_SEED],
        "n_test_users": len(test_users),
        "results": legacy_results,
    }
    return {"main": report, "legacy": legacy_report}


def _print_comparison_table(results: dict):
    print("\n" + "=" * 78)
    print("📋 测试集结果对比（5-seed mean ± std）")
    print("=" * 78)
    print(f"  说明: {SINGLE_POSITIVE_METRIC_NOTE}")
    for k in K_VALUES:
        print(f"\n  --- K = {k} ---")
        print(f"  {'算法':<24} {'HR@K':>12} {'NDCG@K':>12}")
        print(f"  {'-' * 64}")
        for algo_name, payload in results.items():
            metrics = payload["metrics"][str(k)]
            ndcg_text = f"{metrics['ndcg']:.4f}±{metrics['ndcg_std']:.4f}"
            hit_text = f"{metrics['hit_rate']:.4f}±{metrics['hit_rate_std']:.4f}"
            print(
                f"  {payload['display_name']:<24}"
                f" {hit_text:>12}"
                f" {ndcg_text:>12}"
            )

    print("\n  --- Coverage / Diversity / Time ---")
    for payload in results.values():
        print(
            f"  {payload['display_name']:<24}"
            f" coverage@20={payload['coverage_at_20']['mean']:.4f}±{payload['coverage_at_20']['std']:.4f}"
            f" diversity@10={payload['diversity_at_10']['mean']:.4f}±{payload['diversity_at_10']['std']:.4f}"
            f" avg_time={payload['avg_time_seconds']:.4f}s"
        )


def _report_stamp(report: dict) -> str:
    raw = report.get("generated_at")
    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            return dt.astimezone().strftime("%Y-%m-%d_%H%M%S")
        except ValueError:
            pass
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d_%H%M%S")


def _next_available_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{root}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _write_report_files(
    *,
    json_path: str,
    markdown_path: str,
    report: dict,
    include_ablations: bool,
):
    with open(json_path, "w", encoding="utf-8") as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)
    with open(markdown_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(build_markdown_report(report, include_ablations=include_ablations))


def _save_results(report_bundle: dict):
    reports_dir = os.path.join(BACKEND_DIR, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    history_dir = os.path.join(reports_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    main_json_path = os.path.join(reports_dir, "eval_results.json")
    main_md_path = os.path.join(reports_dir, "eval_results.md")
    _write_report_files(
        json_path=main_json_path,
        markdown_path=main_md_path,
        report=report_bundle["main"],
        include_ablations=True,
    )

    legacy_json_path = os.path.join(reports_dir, "eval_results_legacy.json")
    legacy_md_path = os.path.join(reports_dir, "eval_results_legacy.md")
    _write_report_files(
        json_path=legacy_json_path,
        markdown_path=legacy_md_path,
        report=report_bundle["legacy"],
        include_ablations=False,
    )

    stamp = _report_stamp(report_bundle["main"])
    history_main_json_path = _next_available_path(
        os.path.join(history_dir, f"{stamp}_eval_results.json")
    )
    history_main_md_path = os.path.splitext(history_main_json_path)[0] + ".md"
    _write_report_files(
        json_path=history_main_json_path,
        markdown_path=history_main_md_path,
        report=report_bundle["main"],
        include_ablations=True,
    )

    history_legacy_json_path = _next_available_path(
        os.path.join(history_dir, f"{stamp}_eval_results_legacy.json")
    )
    history_legacy_md_path = os.path.splitext(history_legacy_json_path)[0] + ".md"
    _write_report_files(
        json_path=history_legacy_json_path,
        markdown_path=history_legacy_md_path,
        report=report_bundle["legacy"],
        include_ablations=False,
    )

    print(f"\n  📄 JSON 报告: {main_json_path}")
    print(f"  📄 Legacy JSON: {legacy_json_path}")
    print(f"  📄 Markdown 报告: {main_md_path}")
    print(f"  📄 Legacy Markdown: {legacy_md_path}")
    print(f"  🗂️ 历史 JSON 报告: {history_main_json_path}")
    print(f"  🗂️ 历史 Legacy JSON: {history_legacy_json_path}")


def build_markdown_report(report: dict, *, include_ablations: bool) -> str:
    lines = [
        "# 推荐算法离线评估报告",
        "",
        f"- 协议版本: **v{report['protocol_version']}**",
        f"- 评估方法: **{report['eval_method']}**",
        f"- 用户来源: **{report.get('user_source_display', describe_user_source(report.get('user_source', 'all')))}**",
        f"- 负采样 seeds: **{report['negative_sample_seeds']}**",
    ]
    if "n_validation_users" in report:
        lines.append(f"- 验证集用户数: **{report['n_validation_users']}**")
    lines.append(f"- 测试集用户数: **{report['n_test_users']}**")
    lines.append(f"- 指标说明: **{SINGLE_POSITIVE_METRIC_NOTE}**")
    lines.append("")

    for k in K_VALUES:
        lines.append(f"## K = {k}")
        lines.append("")
        lines.append(
            f"| 算法 | HR@{k} | NDCG@{k} |"
        )
        lines.append("|------|------|------|")
        for payload in report["results"].values():
            metrics = payload["metrics"][str(k)]
            lines.append(
                f"| {payload['display_name']} "
                f"| {metrics['hit_rate']:.4f} ± {metrics.get('hit_rate_std', 0.0):.4f} "
                f"| {metrics['ndcg']:.4f} ± {metrics.get('ndcg_std', 0.0):.4f} |"
            )
        lines.append("")

    lines.append("## Coverage / Diversity / Time")
    lines.append("")
    lines.append("| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |")
    lines.append("|------|-------------|--------------|--------------|")
    for payload in report["results"].values():
        lines.append(
            f"| {payload['display_name']} "
            f"| {payload['coverage_at_20']['mean']:.4f} ± {payload['coverage_at_20']['std']:.4f} "
            f"| {payload['diversity_at_10']['mean']:.4f} ± {payload['diversity_at_10']['std']:.4f} "
            f"| {payload['avg_time_seconds']:.4f} |"
        )
    lines.append("")

    if include_ablations:
        lines.append("## Best Params")
        lines.append("")
        for algo_name, payload in report["results"].items():
            lines.append(f"- **{payload['display_name']} ({algo_name})**: `{json.dumps(payload.get('best_params', {}), ensure_ascii=False, sort_keys=True)}`")
        lines.append("")
        lines.append("## Ablations")
        lines.append("")
        for payload in report["results"].values():
            if not payload.get("ablations"):
                continue
            lines.append(f"### {payload['display_name']}")
            lines.append("")
            lines.append("| 消融 | HR@10 | NDCG@10 | Params |")
            lines.append("|------|-------|---------|--------|")
            for label, ablation in payload["ablations"].items():
                metrics = ablation["metrics"]["10"]
                lines.append(
                    f"| {label} "
                    f"| {metrics['hit_rate']:.4f} ± {metrics.get('hit_rate_std', 0.0):.4f} "
                    f"| {metrics['ndcg']:.4f} ± {metrics.get('ndcg_std', 0.0):.4f} "
                    f"| `{json.dumps(ablation.get('params', {}), ensure_ascii=False, sort_keys=True)}` |"
                )
            lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="推荐算法离线评估")
    parser.add_argument(
        "--user-source",
        choices=USER_SOURCE_CHOICES,
        default="all",
        help="评估用户来源：all=全量，public=公开豆瓣用户，seed_cfkg=历史 mock 用户，non_public=排除公开导入用户。",
    )
    return parser.parse_args()


def run_evaluation(*, user_source: str = "all"):
    report_bundle = evaluate_suite(user_source=user_source)
    _print_comparison_table(report_bundle["main"]["results"])
    _save_results(report_bundle)


if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
    init_pool()
    Neo4jConnection.get_driver()

    try:
        run_evaluation(user_source=args.user_source)
    finally:
        from app.db.mysql import close_pool

        close_pool()
        Neo4jConnection.close()
