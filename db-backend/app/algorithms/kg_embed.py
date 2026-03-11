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

            # 注意：不加入 RATED 关系
            # 原因：评估时若某用户 RATED test_mid 的关系在训练集里，
            # TransE 嵌入会把 user_vec 和 test_mid_vec 拉近，
            # 导致评估数据泄露（test_mid 总是排前面）
            # KG-Embed 只用电影结构关系(导演/演员/类型)学习电影语义

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

        positive_mids = [str(m["mid"]) for m in positive_movies]
        pos_weights_map = {str(m["mid"]): float(m["rating"]) / 5.0 for m in positive_movies}

        # ── Step 1: 计算嵌入相似度 ──────────────────────────────────────────
        pos_embeddings = []
        pos_weight_vals = []
        for mid in positive_mids:
            entity_key = f"movie_{mid}"
            if entity_key in self._entity_to_idx:
                idx = self._entity_to_idx[entity_key]
                pos_embeddings.append(self._entity_embeddings[idx])
                pos_weight_vals.append(pos_weights_map.get(mid, 0.5))

        embed_scores: dict[str, float] = {}
        if pos_embeddings:
            pos_arr = np.array(pos_embeddings)
            pos_w = np.array(pos_weight_vals)
            pos_w = pos_w / pos_w.sum()
            user_vec = np.average(pos_arr, axis=0, weights=pos_w)
            u_norm = np.linalg.norm(user_vec)
            if u_norm > 0:
                user_vec = user_vec / u_norm

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
                    embed_scores[movie_mid] = sim

        # ── Step 2: 计算实体重叠奖励（导演/演员偏好） ─────────────────────────
        # 从用户 training movies 中统计喜欢的导演和演员
        driver = Neo4jConnection.get_driver()
        entity_preference: dict[str, float] = {}  # person_pid -> weight

        with driver.session() as session:
            for seed_mid in positive_mids[:10]:  # 取前10部控制查询量
                result = session.run(
                    "MATCH (m:Movie {mid: $mid})<-[:DIRECTED|ACTED_IN]-(p:Person) "
                    "RETURN p.pid AS pid",
                    mid=seed_mid,
                )
                seed_weight = pos_weights_map.get(seed_mid, 0.5)
                for r in result:
                    key = str(r["pid"])
                    entity_preference[key] = entity_preference.get(key, 0) + seed_weight

        # 取偏好最强的 top-30 人物，查找他们关联的候选电影
        top_persons = sorted(entity_preference, key=lambda k: -entity_preference[k])[:30]
        entity_scores: dict[str, float] = {}

        if top_persons:
            with driver.session() as session:
                result = session.run(
                    "MATCH (p:Person)-[:DIRECTED|ACTED_IN]->(m:Movie) "
                    "WHERE p.pid IN $pids "
                    "RETURN m.mid AS mid, p.pid AS pid",
                    pids=top_persons,
                )
                for r in result:
                    mid = str(r["mid"])
                    pid = str(r["pid"])
                    if mid not in exclude_all:
                        entity_scores[mid] = entity_scores.get(mid, 0) + entity_preference.get(pid, 0)

        # ── Step 3: 归一化并融合两个分数 ────────────────────────────────────
        # 归一化 embed_scores → [0, 1]
        if embed_scores:
            max_e = max(embed_scores.values())
            min_e = min(embed_scores.values())
            rng_e = max_e - min_e or 1e-8
            embed_scores = {mid: (s - min_e) / rng_e for mid, s in embed_scores.items()}

        # 归一化 entity_scores → [0, 1]
        if entity_scores:
            max_t = max(entity_scores.values())
            entity_scores = {mid: s / max_t for mid, s in entity_scores.items()}

        # 合并候选集（embedding 发现的 + entity 发现的）
        all_candidate_mids = set(embed_scores) | set(entity_scores)

        EMBED_WEIGHT = 0.6
        ENTITY_WEIGHT = 0.4

        candidates = []
        for mid in all_candidate_mids:
            if mid in exclude_all:
                continue
            e_score = embed_scores.get(mid, 0.0)
            t_score = entity_scores.get(mid, 0.0)
            final_score = EMBED_WEIGHT * e_score + ENTITY_WEIGHT * t_score

            if final_score > 0:
                # 生成推荐理由
                if t_score > 0 and e_score > 0:
                    reason = "基于知识图谱嵌入空间和实体关系（导演/演员）的综合推荐"
                elif t_score > 0:
                    reason = "基于你喜欢的导演/演员，在知识图谱中发现的相关电影"
                else:
                    reason = "基于知识图谱嵌入空间的语义相似性推荐"

                candidates.append({
                    "mid": mid,
                    "score": round(final_score, 4),
                    "reason": reason,
                })

        if not candidates:
            return []

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:n]
