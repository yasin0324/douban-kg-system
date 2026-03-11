"""
基于知识图谱路径的推荐算法 (KG-Path)

核心 KG 算法：在 Neo4j 知识图谱中通过多跳路径发现候选电影
利用导演、演员、类型的关系网络做推荐，天然具有可解释性

优势：多跳路径利用图谱深层语义关系，即使评分稀疏也能发现关联
"""

from collections import defaultdict

from app.algorithms.base import BaseRecommender
from app.db.mysql import get_connection
from app.db.neo4j import Neo4jConnection


class KGPathRecommender(BaseRecommender):
    name = "kg_path"
    display_name = "基于知识图谱路径的推荐"

    # 路径衰减系数：hop 数越多，权重越低
    HOP_WEIGHTS = {
        "director": 1.0,     # 共同导演，最强信号
        "actor": 0.8,        # 共同演员
        "genre": 0.5,        # 共同类型
        "actor_actor": 0.4,  # 演员的演员 (2-hop)
    }

    def recommend(self, user_id: int, n: int = 20, exclude_mids: set | None = None, exclude_from_training: set | None = None) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()
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
        positive_weights = {str(m["mid"]): float(m["rating"]) / 5.0 for m in positive_movies}

        # 在 Neo4j 中查询多跳路径
        driver = Neo4jConnection.get_driver()
        candidate_scores: dict[str, float] = defaultdict(float)
        candidate_reasons: dict[str, list[str]] = defaultdict(list)
        candidate_paths: dict[str, int] = defaultdict(int)  # 路径命中次数

        with driver.session() as session:
            for seed_mid in positive_mids:
                seed_weight = positive_weights.get(seed_mid, 0.5)

                # --- 1-hop: 共同导演 ---
                result = session.run(
                    "MATCH (seed:Movie {mid: $mid})<-[:DIRECTED]-(p:Person)-[:DIRECTED]->(cand:Movie) "
                    "WHERE cand.mid <> $mid "
                    "RETURN DISTINCT cand.mid AS mid, p.name AS via_name "
                    "LIMIT 30",
                    mid=seed_mid,
                )
                for record in result:
                    cand_mid = record["mid"]
                    if cand_mid in exclude_all:
                        continue
                    score = self.HOP_WEIGHTS["director"] * seed_weight
                    candidate_scores[cand_mid] += score
                    candidate_paths[cand_mid] += 1
                    candidate_reasons[cand_mid].append(
                        f"与你喜欢的电影有共同导演 {record['via_name']}"
                    )

                # --- 1-hop: 共同演员 ---
                result = session.run(
                    "MATCH (seed:Movie {mid: $mid})<-[:ACTED_IN]-(p:Person)-[:ACTED_IN]->(cand:Movie) "
                    "WHERE cand.mid <> $mid "
                    "RETURN cand.mid AS mid, p.name AS via_name, count(*) AS cnt "
                    "ORDER BY cnt DESC "
                    "LIMIT 50",
                    mid=seed_mid,
                )
                for record in result:
                    cand_mid = record["mid"]
                    if cand_mid in exclude_all:
                        continue
                    score = self.HOP_WEIGHTS["actor"] * seed_weight
                    candidate_scores[cand_mid] += score
                    candidate_paths[cand_mid] += 1
                    if len(candidate_reasons[cand_mid]) < 3:
                        candidate_reasons[cand_mid].append(
                            f"有共同演员 {record['via_name']}"
                        )

                # --- 1-hop: 共同类型 ---
                result = session.run(
                    "MATCH (seed:Movie {mid: $mid})-[:HAS_GENRE]->(g:Genre)<-[:HAS_GENRE]-(cand:Movie) "
                    "WHERE cand.mid <> $mid "
                    "RETURN cand.mid AS mid, collect(DISTINCT g.name) AS genres, count(DISTINCT g) AS gcnt "
                    "ORDER BY gcnt DESC "
                    "LIMIT 50",
                    mid=seed_mid,
                )
                for record in result:
                    cand_mid = record["mid"]
                    if cand_mid in exclude_all:
                        continue
                    # 共同类型越多分数越高
                    genre_count = record["gcnt"]
                    score = self.HOP_WEIGHTS["genre"] * seed_weight * min(genre_count / 3.0, 1.0)
                    candidate_scores[cand_mid] += score
                    candidate_paths[cand_mid] += 1
                    if len(candidate_reasons[cand_mid]) < 3:
                        genres_str = "/".join(record["genres"][:3])
                        candidate_reasons[cand_mid].append(
                            f"同属 {genres_str} 类型"
                        )

                # --- 2-hop: 通过演员发现更远的电影 ---
                result = session.run(
                    "MATCH (seed:Movie {mid: $mid})<-[:ACTED_IN]-(p1:Person)-[:ACTED_IN]->(mid_movie:Movie) "
                    "<-[:ACTED_IN]-(p2:Person)-[:ACTED_IN]->(cand:Movie) "
                    "WHERE cand.mid <> $mid AND mid_movie.mid <> $mid AND cand.mid <> mid_movie.mid "
                    "  AND p1 <> p2 "
                    "RETURN DISTINCT cand.mid AS mid, p2.name AS via_name "
                    "LIMIT 30",
                    mid=seed_mid,
                )
                for record in result:
                    cand_mid = record["mid"]
                    if cand_mid in exclude_all:
                        continue
                    score = self.HOP_WEIGHTS["actor_actor"] * seed_weight
                    candidate_scores[cand_mid] += score
                    candidate_paths[cand_mid] += 1

        if not candidate_scores:
            return []

        # 归一化并排序
        max_score = max(candidate_scores.values())
        if max_score == 0:
            return []

        results = []
        for mid, score in candidate_scores.items():
            reasons = candidate_reasons.get(mid, [])
            reason = reasons[0] if reasons else "基于知识图谱路径关联推荐"
            results.append({
                "mid": mid,
                "score": round(score / max_score, 4),
                "reason": reason,
                "path_count": candidate_paths.get(mid, 0),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n]
