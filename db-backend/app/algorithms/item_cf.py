"""
基于物品的协同过滤推荐算法 (ItemCF)

基线算法：仅使用 MySQL 中的用户评分矩阵
通过计算物品间余弦相似度，为用户推荐与其高评电影相似的其他电影

局限性：依赖评分矩阵的稠密度，稀疏数据下相似度噪声大
"""

import math
from collections import defaultdict

from app.algorithms.base import BaseRecommender
from app.db.mysql import get_connection


class ItemCFRecommender(BaseRecommender):
    name = "item_cf"
    display_name = "基于物品的协同过滤"
    MAX_POSITIVE_RATING_SEEDS = 50
    MAX_LIKE_SEEDS = 10
    MAX_WISH_SEEDS = 0

    def __init__(self):
        self._item_users = None
        self._user_items = None
        self._movie_names = None
        self._item_norms = None

    def get_user_positive_movies(
        self,
        conn,
        user_id: int,
        threshold: float = 3.5,
        exclude_mids: set | None = None,
    ) -> list[dict]:
        return self.get_user_positive_movies_for_kg(
            conn,
            user_id,
            threshold=threshold,
            exclude_mids=exclude_mids,
            max_positive_ratings=self.MAX_POSITIVE_RATING_SEEDS,
            max_likes=self.MAX_LIKE_SEEDS,
            max_wishes=self.MAX_WISH_SEEDS,
        )

    def _load_data(self):
        """一次性加载全局评分矩阵并缓存"""
        if self._item_users is not None:
            return

        conn = get_connection()
        try:
            # 构建评分矩阵 (item -> {user: rating})
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT user_id, mid, rating FROM user_movie_ratings"
                )
                all_ratings = cursor.fetchall()

            # 获取电影名称用于推荐理由
            with conn.cursor() as cursor:
                cursor.execute("SELECT douban_id, name FROM movies")
                self._movie_names = {str(r["douban_id"]): r["name"] for r in cursor.fetchall()}
        finally:
            conn.close()

        # item -> {user_id: rating}
        self._item_users = defaultdict(dict)
        # user -> [mid1, mid2, ...]
        self._user_items = defaultdict(list)

        for r in all_ratings:
            mid_str = str(r["mid"])
            uid = r["user_id"]
            self._item_users[mid_str][uid] = float(r["rating"])
            self._user_items[uid].append(mid_str)

        # 预计算每项的向量范数
        self._item_norms = {}
        for mid, users in self._item_users.items():
            self._item_norms[mid] = math.sqrt(sum(v ** 2 for v in users.values()))

    def recommend(
        self,
        user_id: int,
        n: int = 20,
        exclude_mids: set | None = None,
        exclude_from_training: set | None = None,
    ) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()

        # 确保数据已加载
        self._load_data()

        conn = get_connection()
        try:
            # 1. 获取用户正向电影和所有已评分电影（排除 test_mid 的训练影响）
            positive_movies = self.get_user_positive_movies(
                conn, user_id, exclude_mids=exclude_from_training
            )
            if not positive_movies:
                return []

            rated_mids = self.get_user_all_rated_mids(
                conn, user_id, exclude_mids=exclude_from_training
            )
            exclude_all = rated_mids | exclude_mids
        finally:
            conn.close()

        positive_mids = [str(m["mid"]) for m in positive_movies]
        positive_weights = {str(m["mid"]): float(m["rating"]) for m in positive_movies}

        # 2. 数据泄露修复：临时屏蔽当前用户对 test_mid 的评分
        # 若不屏蔽，当前用户同时评了 seed_mid 和 test_mid，会造成虚假的高共现相似度
        temporary_masks: dict[tuple, float] = {}
        for masked_mid in exclude_from_training:
            if masked_mid in self._item_users and user_id in self._item_users[masked_mid]:
                val = self._item_users[masked_mid].pop(user_id)
                temporary_masks[(masked_mid, user_id)] = val

        try:
            # 3. 计算物品间余弦相似度（内嵌函数）
            def item_cosine_sim(mid_a: str, mid_b: str) -> float:
                users_a = self._item_users.get(mid_a, {})
                users_b = self._item_users.get(mid_b, {})
                # 找共同评分用户
                common_users = set(users_a.keys()) & set(users_b.keys())
                if len(common_users) < 2:
                    return 0.0
                dot = sum(users_a[u] * users_b[u] for u in common_users)
                norm_a = self._item_norms.get(mid_a, 0.0)
                norm_b = self._item_norms.get(mid_b, 0.0)
                if norm_a == 0 or norm_b == 0:
                    return 0.0
                return dot / (norm_a * norm_b)

            # 4. 找候选：只考虑与用户喜欢电影有共同评分用户的电影
            candidate_mids = set()
            for seed_mid in positive_mids:
                for u in self._item_users.get(seed_mid, {}):
                    candidate_mids.update(self._user_items.get(u, []))

            # 5. 聚合相似度分数
            candidate_scores: dict[str, float] = defaultdict(float)
            candidate_reasons: dict[str, str] = {}

            for candidate_mid in candidate_mids:
                if candidate_mid in exclude_all:
                    continue

                best_sim = 0.0
                best_seed = None

                for seed_mid in positive_mids:
                    sim = item_cosine_sim(seed_mid, candidate_mid)
                    if sim > 0:
                        weight = positive_weights.get(seed_mid, 1.0) / 5.0
                        candidate_scores[candidate_mid] += sim * weight
                        if sim > best_sim:
                            best_sim = sim
                            best_seed = seed_mid

                if best_seed and candidate_mid in candidate_scores:
                    seed_name = self._movie_names.get(best_seed, best_seed)
                    candidate_reasons[candidate_mid] = (
                        f"因为你喜欢《{seed_name}》，推荐评分行为相似的电影"
                    )

        finally:
            # 6. 恢复被屏蔽的评分（无论是否异常都要还原）
            for (masked_mid, uid), val in temporary_masks.items():
                self._item_users[masked_mid][uid] = val

        # 7. 归一化并排序
        if not candidate_scores:
            return []

        max_score = max(candidate_scores.values())
        if max_score == 0:
            return []

        results = []
        for mid, score in candidate_scores.items():
            results.append({
                "mid": mid,
                "score": round(score / max_score, 4),
                "reason": candidate_reasons.get(mid, "基于协同过滤相似性推荐"),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n]
