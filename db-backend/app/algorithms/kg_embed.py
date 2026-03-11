"""
基于知识图谱嵌入的推荐算法 (KG-Embed / TransE)

核心 KG 算法：将知识图谱中的实体和关系嵌入到低维向量空间
用户兴趣向量 = 高评电影嵌入的加权平均，通过余弦相似度推荐

TransE 核心思想: h + r ≈ t (头实体 + 关系 ≈ 尾实体)

优势：嵌入空间编码了全局图结构，能捕捉隐式关系
"""

import json
import logging
import math
import os
import random
from collections import defaultdict

import numpy as np

from app.algorithms.base import BaseRecommender
from app.db.mysql import get_connection
from app.db.neo4j import Neo4jConnection

logger = logging.getLogger(__name__)

# 嵌入文件存储路径
EMBED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "embeddings")
EMBED_FILE = os.path.join(EMBED_DIR, "transe_embeddings.npz")
ENTITY_MAP_FILE = os.path.join(EMBED_DIR, "entity_map.json")


class KGEmbedRecommender(BaseRecommender):
    name = "kg_embed"
    display_name = "基于知识图谱嵌入的推荐"

    # TransE 超参数
    EMBED_DIM = 64
    LEARNING_RATE = 0.01
    MARGIN = 1.0
    EPOCHS = 100
    BATCH_SIZE = 4096

    def __init__(self):
        self._entity_embeddings = None
        self._entity_to_idx = None
        self._idx_to_entity = None
        self._movie_mids = None  # 所有电影的 mid 集合

    def _load_or_train(self):
        """加载已训练的嵌入，若不存在则训练"""
        if self._entity_embeddings is not None:
            return

        if os.path.exists(EMBED_FILE) and os.path.exists(ENTITY_MAP_FILE):
            logger.info("加载已有 TransE 嵌入向量...")
            data = np.load(EMBED_FILE)
            self._entity_embeddings = data["entity_embeddings"]
            with open(ENTITY_MAP_FILE, "r", encoding="utf-8") as f:
                maps = json.load(f)
            self._entity_to_idx = maps["entity_to_idx"]
            self._idx_to_entity = {int(k): v for k, v in maps["idx_to_entity"].items()}
            self._movie_mids = set(maps.get("movie_mids", []))
            logger.info(
                f"嵌入加载完成: {len(self._entity_to_idx)} 个实体, "
                f"维度 {self._entity_embeddings.shape[1]}"
            )
            return

        logger.info("未找到嵌入文件，开始训练 TransE...")
        self._train_transe()

    def _export_triples(self):
        """从 Neo4j 导出三元组"""
        driver = Neo4jConnection.get_driver()
        triples = []
        movie_mids = set()

        with driver.session() as session:
            # DIRECTED 关系
            result = session.run(
                "MATCH (p:Person)-[:DIRECTED]->(m:Movie) "
                "RETURN p.pid AS head, 'DIRECTED' AS rel, m.mid AS tail"
            )
            for r in result:
                triples.append((f"person_{r['head']}", "DIRECTED", f"movie_{r['tail']}"))
                movie_mids.add(r["tail"])

            # ACTED_IN 关系
            result = session.run(
                "MATCH (p:Person)-[:ACTED_IN]->(m:Movie) "
                "RETURN p.pid AS head, 'ACTED_IN' AS rel, m.mid AS tail"
            )
            for r in result:
                triples.append((f"person_{r['head']}", "ACTED_IN", f"movie_{r['tail']}"))
                movie_mids.add(r["tail"])

            # HAS_GENRE 关系
            result = session.run(
                "MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre) "
                "RETURN m.mid AS head, 'HAS_GENRE' AS rel, g.name AS tail"
            )
            for r in result:
                triples.append((f"movie_{r['head']}", "HAS_GENRE", f"genre_{r['tail']}"))
                movie_mids.add(r["head"])

            # RATED 关系
            result = session.run(
                "MATCH (u:User)-[:RATED]->(m:Movie) "
                "RETURN u.uid AS head, 'RATED' AS rel, m.mid AS tail"
            )
            for r in result:
                triples.append((f"user_{r['head']}", "RATED", f"movie_{r['tail']}"))
                movie_mids.add(r["tail"])

        logger.info(f"导出 {len(triples)} 条三元组, {len(movie_mids)} 部电影")
        return triples, movie_mids

    def _train_transe(self):
        """训练 TransE 嵌入"""
        triples, movie_mids = self._export_triples()

        if not triples:
            logger.warning("没有三元组数据，无法训练")
            return

        # 构建实体和关系映射
        entities = set()
        relations = set()
        for h, r, t in triples:
            entities.add(h)
            entities.add(t)
            relations.add(r)

        entity_list = sorted(entities)
        relation_list = sorted(relations)
        entity_to_idx = {e: i for i, e in enumerate(entity_list)}
        relation_to_idx = {r: i for i, r in enumerate(relation_list)}

        n_entities = len(entity_list)
        n_relations = len(relation_list)
        d = self.EMBED_DIM

        logger.info(f"实体: {n_entities}, 关系: {n_relations}, 维度: {d}")

        # 初始化嵌入向量 (Xavier 初始化)
        rng = np.random.RandomState(42)
        entity_emb = rng.uniform(-6.0 / math.sqrt(d), 6.0 / math.sqrt(d), (n_entities, d))
        relation_emb = rng.uniform(-6.0 / math.sqrt(d), 6.0 / math.sqrt(d), (n_relations, d))

        # 归一化实体嵌入
        norms = np.linalg.norm(entity_emb, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        entity_emb = entity_emb / norms

        # 将三元组转换为索引
        triple_indices = np.array(
            [(entity_to_idx[h], relation_to_idx[r], entity_to_idx[t]) for h, r, t in triples],
            dtype=np.int32,
        )

        # SGD 训练
        n_triples = len(triple_indices)
        logger.info(f"开始训练 TransE: {self.EPOCHS} epochs, batch_size={self.BATCH_SIZE}")

        for epoch in range(self.EPOCHS):
            # 随机打乱
            indices = rng.permutation(n_triples)
            total_loss = 0.0

            for start in range(0, n_triples, self.BATCH_SIZE):
                batch_idx = indices[start : start + self.BATCH_SIZE]
                batch = triple_indices[batch_idx]

                h_idx = batch[:, 0]
                r_idx = batch[:, 1]
                t_idx = batch[:, 2]

                # 负采样：随机替换头或尾实体
                neg_batch = batch.copy()
                mask = rng.random(len(batch)) < 0.5
                neg_entities = rng.randint(0, n_entities, len(batch))
                neg_batch[mask, 0] = neg_entities[mask]
                neg_batch[~mask, 2] = neg_entities[~mask]

                nh_idx = neg_batch[:, 0]
                nt_idx = neg_batch[:, 2]

                # 正样本距离: ||h + r - t||
                pos_dist = entity_emb[h_idx] + relation_emb[r_idx] - entity_emb[t_idx]
                pos_score = np.sum(pos_dist ** 2, axis=1)

                # 负样本距离
                neg_dist = entity_emb[nh_idx] + relation_emb[r_idx] - entity_emb[nt_idx]
                neg_score = np.sum(neg_dist ** 2, axis=1)

                # MarginRankingLoss: max(0, margin + pos - neg)
                loss = np.maximum(0, self.MARGIN + pos_score - neg_score)
                active = loss > 0

                if not np.any(active):
                    continue

                total_loss += np.sum(loss)

                # 梯度更新 (只更新 active 样本)
                lr = self.LEARNING_RATE
                active_pos_dist = pos_dist[active]
                active_neg_dist = neg_dist[active]

                # 正样本梯度
                grad_h = 2 * lr * active_pos_dist
                grad_t = -2 * lr * active_pos_dist
                grad_r = 2 * lr * active_pos_dist

                # 负样本梯度 (反向)
                grad_nh = -2 * lr * active_neg_dist
                grad_nt = 2 * lr * active_neg_dist

                active_h = h_idx[active]
                active_t = t_idx[active]
                active_nh = nh_idx[active]
                active_nt = nt_idx[active]
                active_r = r_idx[active]

                # 更新嵌入
                np.subtract.at(entity_emb, active_h, grad_h)
                np.subtract.at(entity_emb, active_t, grad_t)
                np.subtract.at(relation_emb, active_r, grad_r)
                np.subtract.at(entity_emb, active_nh, grad_nh)
                np.subtract.at(entity_emb, active_nt, grad_nt)

                # 重新归一化实体嵌入
                norms = np.linalg.norm(entity_emb, axis=1, keepdims=True)
                norms = np.maximum(norms, 1e-8)
                entity_emb = entity_emb / norms

            if (epoch + 1) % 20 == 0:
                avg_loss = total_loss / n_triples
                logger.info(f"  Epoch {epoch + 1}/{self.EPOCHS}, Loss: {avg_loss:.4f}")

        # 保存嵌入
        os.makedirs(EMBED_DIR, exist_ok=True)
        np.savez(EMBED_FILE, entity_embeddings=entity_emb)

        idx_to_entity = {i: e for e, i in entity_to_idx.items()}
        with open(ENTITY_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "entity_to_idx": entity_to_idx,
                    "idx_to_entity": {str(k): v for k, v in idx_to_entity.items()},
                    "movie_mids": sorted(movie_mids),
                },
                f,
                ensure_ascii=False,
            )

        self._entity_embeddings = entity_emb
        self._entity_to_idx = entity_to_idx
        self._idx_to_entity = idx_to_entity
        self._movie_mids = movie_mids

        logger.info(f"TransE 训练完成，嵌入已保存到 {EMBED_FILE}")

    def recommend(self, user_id: int, n: int = 20, exclude_mids: set | None = None, exclude_from_training: set | None = None) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()

        # 确保嵌入已加载
        self._load_or_train()
        if self._entity_embeddings is None:
            return []

        conn = get_connection()
        try:
            positive_movies = self.get_user_positive_movies(conn, user_id, exclude_mids=exclude_from_training)
            if not positive_movies:
                return []

            rated_mids = self.get_user_all_rated_mids(conn, user_id, exclude_mids=exclude_from_training)
            exclude_all = rated_mids | exclude_mids
        finally:
            conn.close()

        # 获取用户正向电影的嵌入向量
        pos_embeddings = []
        pos_weights = []
        for m in positive_movies:
            entity_key = f"movie_{m['mid']}"
            if entity_key in self._entity_to_idx:
                idx = self._entity_to_idx[entity_key]
                pos_embeddings.append(self._entity_embeddings[idx])
                pos_weights.append(float(m["rating"]) / 5.0)

        if not pos_embeddings:
            return []

        # 用户兴趣向量 = 高评电影嵌入的加权平均
        pos_embeddings = np.array(pos_embeddings)
        pos_weights = np.array(pos_weights)
        pos_weights = pos_weights / pos_weights.sum()
        user_vec = np.average(pos_embeddings, axis=0, weights=pos_weights)

        # 归一化
        norm = np.linalg.norm(user_vec)
        if norm > 0:
            user_vec = user_vec / norm

        # 计算与所有电影的余弦相似度
        candidates = []
        for movie_mid in self._movie_mids:
            if movie_mid in exclude_all:
                continue
            entity_key = f"movie_{movie_mid}"
            if entity_key not in self._entity_to_idx:
                continue
            idx = self._entity_to_idx[entity_key]
            movie_vec = self._entity_embeddings[idx]
            movie_norm = np.linalg.norm(movie_vec)
            if movie_norm == 0:
                continue
            sim = float(np.dot(user_vec, movie_vec / movie_norm))
            if sim > 0:
                candidates.append({
                    "mid": movie_mid,
                    "score": sim,
                    "reason": "基于知识图谱嵌入空间的语义相似性推荐",
                })

        if not candidates:
            return []

        # 归一化分数到 [0, 1]
        max_score = max(c["score"] for c in candidates)
        min_score = min(c["score"] for c in candidates)
        score_range = max_score - min_score
        if score_range > 0:
            for c in candidates:
                c["score"] = round((c["score"] - min_score) / score_range, 4)
        else:
            for c in candidates:
                c["score"] = 1.0

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:n]
