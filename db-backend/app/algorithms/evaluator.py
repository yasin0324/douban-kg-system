"""
离线评估框架 — 对比不同推荐算法的性能

使用 sampled leave-one-out 方法（学术标准）：
1. 对每个用户，留出最后一条高评分作为测试集（leave-one-out）
2. 从未评分电影中随机采样 99 条作为负样本
3. 让算法对 1 正 + 99 负 共 100 部电影打分排序
4. 检查正样本是否在 Top-K 中

这是 NCF、KGCN 等经典论文的标准评估方式，避免了「海量候选中碰巧推中」的稀疏问题。

评估指标: Precision@K, Recall@K, NDCG@K, Hit Rate@K

用法:
    cd db-backend
    python -m app.algorithms.evaluator
"""

import json
import logging
import math
import os
import random
import sys
import time
from collections import defaultdict

# 确保项目根目录在 sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.db.mysql import get_connection, init_pool
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

# 评估的 K 值
K_VALUES = [5, 10, 20]
# 正样本阈值
POSITIVE_THRESHOLD = 3.5
# 负采样数量
NUM_NEGATIVES = 99
# 随机种子
RANDOM_SEED = 42


def _ndcg_at_k(ranked_list: list[str], relevant: set[str], k: int) -> float:
    """计算 NDCG@K"""
    dcg = 0.0
    for i, mid in enumerate(ranked_list[:k]):
        if mid in relevant:
            dcg += 1.0 / math.log2(i + 2)
    # 理想 DCG (假设只有 1 个相关项)
    idcg = 1.0 / math.log2(2)
    return dcg / idcg if idcg > 0 else 0.0


def get_test_data():
    """
    构建评估数据集（sampled leave-one-out）

    返回:
        test_users: list[dict] 每项包含:
            - user_id: 用户 ID
            - test_mid: 留出的测试电影 mid（正样本）
            - neg_mids: 随机采样的负样本 mid 集合（99 条）
            - all_mids: 正样本 + 负样本（共 100 条）
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 获取每个用户的评分记录 (按时间排序)
            cursor.execute(
                "SELECT user_id, mid, rating, rated_at "
                "FROM user_movie_ratings "
                "ORDER BY user_id, rated_at ASC"
            )
            all_ratings = cursor.fetchall()

        # 获取所有电影 mid（用于负采样）
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT douban_id FROM movies WHERE douban_id IS NOT NULL"
            )
            all_movie_mids = [str(r["douban_id"]) for r in cursor.fetchall()]
    finally:
        conn.close()

    all_movie_mids_set = set(all_movie_mids)

    # 按用户分组
    user_ratings: dict[int, list[dict]] = defaultdict(list)
    for r in all_ratings:
        user_ratings[r["user_id"]].append(r)

    rng = random.Random(RANDOM_SEED)
    test_users = []

    for uid, ratings in user_ratings.items():
        # 至少需要有 3 条评分（2 条训练 + 1 条测试）
        if len(ratings) < 3:
            continue

        # 从正向评分中选最后一条作为测试集
        positive_ratings = [r for r in ratings if float(r["rating"]) >= POSITIVE_THRESHOLD]
        if len(positive_ratings) < 2:
            continue

        test_item = positive_ratings[-1]  # 最后一条正向评分
        test_mid = str(test_item["mid"])

        # 用户所有已评分电影（不包括 test_mid）
        user_rated_mids = {str(r["mid"]) for r in ratings if str(r["mid"]) != test_mid}

        # 负采样：从未评分电影中随机取 99 条
        candidate_negatives = list(all_movie_mids_set - user_rated_mids - {test_mid})
        if len(candidate_negatives) < NUM_NEGATIVES:
            continue

        neg_mids = rng.sample(candidate_negatives, NUM_NEGATIVES)

        test_users.append({
            "user_id": uid,
            "test_mid": test_mid,
            "neg_mids": neg_mids,
            "all_mids": [test_mid] + neg_mids,  # 100 条候选
        })

    return test_users


def evaluate_algorithm(algo, test_users: list[dict], k_values: list[int]) -> dict:
    """
    对单个算法运行采样评估

    方法：
    1. 算法为用户生成所有候选的推荐分数
    2. 只保留 test_mid + 99 条负样本 的分数
    3. 在这 100 条中按分数排序，看 test_mid 的排名

    返回各 K 值下的指标
    """
    from tqdm import tqdm
    results = {k: {"hits": 0, "precision_sum": 0.0, "ndcg_sum": 0.0} for k in k_values}
    total_users = 0
    max_k = max(k_values)

    for test_case in tqdm(test_users, desc=f"  评估 {algo.display_name}", leave=False, ncols=80):
        user_id = test_case["user_id"]
        test_mid = test_case["test_mid"]
        all_mids_set = set(test_case["all_mids"])  # 100 条候选

        try:
            # 用全量推荐（只排除 test_mid 的训练影响，不限候选）
            # 获取足够大的推荐列表，确保覆盖所有 100 条候选
            recommendations = algo.recommend(
                user_id=user_id,
                n=99999,  # 获取全量打分
                exclude_mids=None,
                exclude_from_training={test_mid},
            )
        except Exception as e:
            logger.warning(f"算法 {algo.name} 对用户 {user_id} 推荐失败: {e}")
            continue

        # 只保留 100 条候选中的结果（sampled evaluation 核心）
        sampled_recs = [r for r in recommendations if r["mid"] in all_mids_set]

        # 如果算法没有对某些候选打分（如 KG-Path 只生成图路径能覆盖的电影），
        # 将未打分的候选电影追加到列表末尾（分数 0）
        scored_mids = {r["mid"] for r in sampled_recs}
        for mid in test_case["all_mids"]:
            if mid not in scored_mids:
                sampled_recs.append({"mid": mid, "score": 0.0, "reason": ""})

        # 按分数排序（模拟用户在 100 候选中的感知）
        sampled_recs.sort(key=lambda x: x["score"], reverse=True)
        ranked_mids = [r["mid"] for r in sampled_recs]

        total_users += 1
        relevant = {test_mid}

        for k in k_values:
            top_k_mids = ranked_mids[:k]
            hit = 1 if test_mid in top_k_mids else 0
            results[k]["hits"] += hit
            results[k]["precision_sum"] += hit / k
            results[k]["ndcg_sum"] += _ndcg_at_k(ranked_mids, relevant, k)

    if total_users == 0:
        return {k: {"precision": 0, "recall": 0, "ndcg": 0, "hit_rate": 0} for k in k_values}

    metrics = {}
    for k in k_values:
        metrics[k] = {
            "precision": round(results[k]["precision_sum"] / total_users, 4),
            "recall": round(results[k]["hits"] / total_users, 4),
            "ndcg": round(results[k]["ndcg_sum"] / total_users, 4),
            "hit_rate": round(results[k]["hits"] / total_users, 4),
        }

    return metrics


def run_evaluation():
    """运行完整评估流程"""
    from app.algorithms import ALGORITHMS

    print("=" * 70)
    print("🧪 推荐算法离线评估 (Sampled Leave-One-Out)")
    print("=" * 70)
    print(f"  评估方法: 1 正样本 + {NUM_NEGATIVES} 随机负样本 共 {NUM_NEGATIVES+1} 条候选")

    # 1. 准备测试数据
    print("\n📊 准备评估数据...")
    test_users = get_test_data()
    print(f"  测试用户数: {len(test_users)}")

    if not test_users:
        print("❌ 没有足够的评分数据进行评估")
        print("  需要至少有用户拥有 3 条以上评分（其中 2 条正向评分）")
        return

    # 2. 逐算法评估
    all_results = {}
    for algo_name, algo_class in ALGORITHMS.items():
        print(f"\n🔄 评估算法: {algo_class.display_name} ({algo_name})...")
        algo = algo_class()
        start_time = time.time()

        metrics = evaluate_algorithm(algo, test_users, K_VALUES)
        elapsed = time.time() - start_time

        all_results[algo_name] = {
            "display_name": algo_class.display_name,
            "metrics": metrics,
            "time_seconds": round(elapsed, 2),
        }
        print(f"  ✅ 完成 ({elapsed:.1f}s)")

    # 3. 输出结果
    _print_comparison_table(all_results, len(test_users))
    _save_results(all_results, len(test_users))


def _print_comparison_table(results: dict, n_users: int):
    """终端打印对比表格"""
    print("\n" + "=" * 70)
    print(f"📋 评估结果对比 (测试用户: {n_users}, 候选集: {NUM_NEGATIVES+1})")
    print("=" * 70)

    for k in K_VALUES:
        print(f"\n  --- K = {k} ---")
        print(f"  {'算法':<20} {'Precision@K':>12} {'Recall@K':>10} {'NDCG@K':>10} {'Hit Rate':>10}")
        print(f"  {'-' * 62}")

        for algo_name, data in results.items():
            m = data["metrics"].get(k, {})
            algo_type = "🌐KG" if algo_name.startswith("kg_") else "📊基线"
            print(
                f"  {data['display_name']:<20}"
                f" {m.get('precision', 0):>11.4f}"
                f" {m.get('recall', 0):>9.4f}"
                f" {m.get('ndcg', 0):>9.4f}"
                f" {m.get('hit_rate', 0):>9.4f}"
            )

    print(f"\n  ⏱️  各算法耗时:")
    for algo_name, data in results.items():
        print(f"    {data['display_name']}: {data['time_seconds']}s")


def _save_results(results: dict, n_users: int):
    """保存评估结果到文件"""
    reports_dir = os.path.join(BACKEND_DIR, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    # JSON 格式
    json_path = os.path.join(reports_dir, "eval_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "n_test_users": n_users,
                "eval_method": f"sampled_leave_one_out (1_positive + {NUM_NEGATIVES}_negatives)",
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n  📄 JSON 报告: {json_path}")

    # Markdown 表格
    md_path = os.path.join(reports_dir, "eval_results.md")
    lines = [
        "# 推荐算法离线评估报告",
        "",
        f"- 测试用户数: **{n_users}**",
        f"- 评估方法: **Sampled Leave-One-Out**",
        f"- 候选集大小: **{NUM_NEGATIVES+1}**（1 正样本 + {NUM_NEGATIVES} 随机负样本）",
        f"- 正样本阈值: **rating ≥ {POSITIVE_THRESHOLD}**",
        "",
        "> 说明：采用学术标准的采样评估方法（参考 NCF、KGCN 等论文），",
        "> 每次评估在 100 个候选（1 个真实喜欢的电影 + 99 个随机未看过的电影）中排序，",
        "> 指标更具判别力。",
        "",
    ]

    for k in K_VALUES:
        lines.append(f"## K = {k}")
        lines.append("")
        lines.append(f"| 算法 | 类型 | Precision@{k} | Recall@{k} | NDCG@{k} | Hit Rate@{k} |")
        lines.append("|------|------|" + "------|" * 4)

        for algo_name, data in results.items():
            m = data["metrics"].get(k, {})
            algo_type = "KG" if algo_name.startswith("kg_") else "基线"
            lines.append(
                f"| {data['display_name']} | {algo_type} "
                f"| {m.get('precision', 0):.4f} "
                f"| {m.get('recall', 0):.4f} "
                f"| {m.get('ndcg', 0):.4f} "
                f"| {m.get('hit_rate', 0):.4f} |"
            )
        lines.append("")

    # 算法耗时
    lines.append("## 算法耗时")
    lines.append("")
    lines.append("| 算法 | 耗时 (秒) |")
    lines.append("|------|----------|")
    for algo_name, data in results.items():
        lines.append(f"| {data['display_name']} | {data['time_seconds']} |")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  📄 Markdown 报告: {md_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
    # 初始化数据库连接
    init_pool()
    Neo4jConnection.get_driver()

    try:
        run_evaluation()
    finally:
        from app.db.mysql import close_pool
        close_pool()
        Neo4jConnection.close()
