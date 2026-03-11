"""
基于内容的推荐算法 (Content-Based)

基线算法：仅使用 MySQL 中的电影元数据（类型、年代、地区）
通过计算电影特征向量与用户偏好向量的余弦相似度来推荐

局限性：只使用浅层属性特征，无法捕捉深层语义关系
"""

import math
import numpy as np
from collections import defaultdict

from app.algorithms.base import BaseRecommender
from app.db.mysql import get_connection


class ContentBasedRecommender(BaseRecommender):
    name = "content"
    display_name = "基于内容的推荐"

    def __init__(self):
        self._movie_data = None
        self._genre_list = []
        self._region_list = []
        self._genre_idx = {}
        self._region_idx = {}
        
        self._movie_mids = []
        self._feature_matrix = None
        self._mid_to_matrix_idx = {}

    def _load_data(self):
        """一次性加载所有电影特征并缓存"""
        if self._movie_data is not None:
            return

        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT douban_id, name, genres, regions, year, douban_score "
                    "FROM movies WHERE douban_id IS NOT NULL"
                )
                all_movies = cursor.fetchall()
        finally:
            conn.close()

        all_genres = set()
        all_regions = set()
        self._movie_data = {}

        for m in all_movies:
            mid = str(m["douban_id"])
            genres = set(g.strip() for g in (m.get("genres") or "").split("/") if g.strip())
            regions_raw = m.get("regions") or ""
            regions = set(r.strip() for r in regions_raw.split("/") if r.strip())
            all_genres.update(genres)
            all_regions.update(regions)
            self._movie_data[mid] = {
                "name": m["name"],
                "genres": genres,
                "regions": regions,
                "year": m.get("year"),
                "score": float(m["douban_score"]) if m.get("douban_score") else None,
            }

        self._genre_list = sorted(all_genres)
        self._region_list = sorted(all_regions)
        self._genre_idx = {g: i for i, g in enumerate(self._genre_list)}
        self._region_idx = {r: i for i, r in enumerate(self._region_list)}

        # 预计算所有电影的特征矩阵
        self._movie_mids = list(self._movie_data.keys())
        feature_dim = len(self._genre_list) + len(self._region_list) + 5
        self._feature_matrix = np.zeros((len(self._movie_mids), feature_dim), dtype=np.float32)
        
        for idx, mid in enumerate(self._movie_mids):
            self._mid_to_matrix_idx[mid] = idx
            vec = self._make_feature_vector(mid)
            if vec:
                self._feature_matrix[idx] = vec
                
        # 归一化特征矩阵以便直接进行点积作为余弦相似度
        norms = np.linalg.norm(self._feature_matrix, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        self._feature_matrix = self._feature_matrix / norms

    def _make_feature_vector(self, mid: str):
        """构建电影特征向量: [genres one-hot | regions one-hot | year_bucket]"""
        info = self._movie_data.get(mid)
        if not info:
            return None
        vec = [0.0] * (len(self._genre_list) + len(self._region_list) + 5)
        # genres
        for g in info["genres"]:
            if g in self._genre_idx:
                vec[self._genre_idx[g]] = 1.0
        # regions
        offset = len(self._genre_list)
        for r in info["regions"]:
            if r in self._region_idx:
                vec[offset + self._region_idx[r]] = 1.0
        # year bucket (5 buckets)
        year = info.get("year")
        if year:
            offset2 = len(self._genre_list) + len(self._region_list)
            if year < 1990:
                vec[offset2] = 1.0
            elif year < 2000:
                vec[offset2 + 1] = 1.0
            elif year < 2010:
                vec[offset2 + 2] = 1.0
            elif year < 2020:
                vec[offset2 + 3] = 1.0
            else:
                vec[offset2 + 4] = 1.0
        return vec

    def recommend(self, user_id: int, n: int = 20, exclude_mids: set | None = None, exclude_from_training: set | None = None) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()
        
        # 确保数据已加载并缓存
        self._load_data()
        
        conn = get_connection()
        try:
            # 1. 获取用户正向电影（排除 test_mid 可能带来的训练噪声）
            positive_movies = self.get_user_positive_movies(conn, user_id, exclude_mids=exclude_from_training)
            if not positive_movies:
                return []

            # 已评分但排除 test_mid，作为候选排除列表
            rated_mids = self.get_user_all_rated_mids(conn, user_id, exclude_mids=exclude_from_training)
            exclude_all = rated_mids | exclude_mids
        finally:
            conn.close()

        positive_mids = [str(m["mid"]) for m in positive_movies]
        positive_weights = np.array([float(m["rating"]) for m in positive_movies])

        # 获取用户评分电影的向量
        pos_indices = []
        valid_weights = []
        for mid, w in zip(positive_mids, positive_weights):
            if mid in self._mid_to_matrix_idx:
                pos_indices.append(self._mid_to_matrix_idx[mid])
                valid_weights.append(w)
                
        if not pos_indices:
            return []
            
        pos_vectors = self._feature_matrix[pos_indices]
        valid_weights = np.array(valid_weights)
        total_weight = valid_weights.sum()
        
        if total_weight == 0:
            return []
            
        valid_weights = valid_weights / total_weight
        
        # 用户兴趣向量 (已加权)
        user_vec = np.average(pos_vectors, axis=0, weights=valid_weights)
        
        # 归一化用户向量
        u_norm = np.linalg.norm(user_vec)
        if u_norm > 0:
            user_vec = user_vec / u_norm
            
        # 批量计算余弦相似度 (因为矩阵和向量都归一化过，所以直接点积即可)
        scores = np.dot(self._feature_matrix, user_vec)

        # 获取用户偏好的类型 (用于生成推荐理由)
        user_top_genres = []
        for i, g in enumerate(self._genre_list):
            if user_vec[i] > 0.1:
                user_top_genres.append(g)
        user_top_genres = user_top_genres[:3]

        candidates = []
        for idx, mid in enumerate(self._movie_mids):
            if mid in exclude_all:
                continue
                
            sim = float(scores[idx])
            if sim > 0:
                info = self._movie_data[mid]
                # 生成推荐理由
                matched_genres = info["genres"] & set(user_top_genres)
                if matched_genres:
                    reason = f"因为你偏好 {'/'.join(matched_genres)} 类型的电影"
                else:
                    reason = "基于你的观影偏好特征匹配"

                candidates.append({
                    "mid": mid,
                    "score": round(sim, 4),
                    "reason": reason,
                })

        # 6. 排序取 Top-N
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:n]
