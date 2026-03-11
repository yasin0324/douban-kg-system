"""
Path-based KG recommender with batched Cypher retrieval and cached evidence.
"""

from __future__ import annotations

from collections import defaultdict

from app.algorithms.base import BaseRecommender
from app.algorithms.graph_cache import (
    REL_ACTOR,
    REL_DIRECTOR,
    REL_GENRE,
    safe_idf,
)
from app.db.mysql import get_connection
from app.db.neo4j import Neo4jConnection


class KGPathRecommender(BaseRecommender):
    name = "kg_path"
    display_name = "基于知识图谱路径的推荐"

    DEFAULT_CONFIG = {
        "director_weight": 1.0,
        "actor_weight": 0.6,
        "genre_weight": 0.4,
        "two_hop_weight": 0.2,
        "actor_order_limit": 5,
        "enable_two_hop": True,
        "use_degree_penalty": True,
        "one_hop_query_limit": 12000,
        "two_hop_query_limit": 6000,
    }

    def __init__(self, **config):
        self._config = {**self.DEFAULT_CONFIG, **config}
        self._evidence_cache: dict[tuple[int, tuple[str, ...], int], dict] = {}
        self._user_context_cache: dict[tuple[int, tuple[str, ...]], tuple[list[dict], set[str]] | None] = {}

    def set_params(self, **params):
        if params:
            self._config.update(params)

    @classmethod
    def parameter_grid(cls) -> list[dict]:
        grid = []
        for director_weight in (0.8, 1.0):
            for actor_weight in (0.4, 0.6, 0.8):
                for genre_weight in (0.2, 0.4, 0.6):
                    for two_hop_weight in (0.1, 0.2, 0.4):
                        for actor_order_limit in (3, 5):
                            grid.append(
                                {
                                    "director_weight": director_weight,
                                    "actor_weight": actor_weight,
                                    "genre_weight": genre_weight,
                                    "two_hop_weight": two_hop_weight,
                                    "actor_order_limit": actor_order_limit,
                                    "enable_two_hop": True,
                                    "use_degree_penalty": True,
                                }
                            )
        return grid

    @classmethod
    def ablation_configs(cls) -> dict[str, dict]:
        return {
            "1-hop": {
                "enable_two_hop": False,
                "use_degree_penalty": False,
            },
            "+2-hop": {
                "enable_two_hop": True,
                "use_degree_penalty": False,
            },
            "+IDF weighting": {
                "enable_two_hop": True,
                "use_degree_penalty": True,
            },
        }

    def recommend(
        self,
        user_id: int,
        n: int = 20,
        exclude_mids: set | None = None,
        exclude_from_training: set | None = None,
    ) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()

        user_context = self._get_user_context(user_id, exclude_from_training)
        if user_context is None:
            return []

        positive_movies, rated_mids = user_context
        exclude_all = rated_mids | exclude_mids
        evidence_bundle = self._get_evidence_bundle(user_id, positive_movies, exclude_from_training)
        candidate_scores = evidence_bundle["candidate_scores"]
        candidate_paths = evidence_bundle["candidate_paths"]

        if not candidate_scores:
            return []

        results = []
        max_score = max(candidate_scores.values()) if candidate_scores else 0.0
        if max_score <= 0:
            return []

        for mid, score in candidate_scores.items():
            if mid in exclude_all:
                continue
            reasons = evidence_bundle["candidate_reasons"].get(mid, [])
            results.append(
                {
                    "mid": mid,
                    "score": round(score / max_score, 4),
                    "reason": reasons[0] if reasons else "基于知识图谱路径关联推荐",
                    "path_count": candidate_paths.get(mid, 0),
                }
            )

        results.sort(key=lambda item: (item["score"], item["path_count"]), reverse=True)
        return results[:n]

    def _get_user_context(self, user_id: int, exclude_from_training: set[str]) -> tuple[list[dict], set[str]] | None:
        cache_key = (user_id, tuple(sorted(exclude_from_training)))
        if cache_key in self._user_context_cache:
            return self._user_context_cache[cache_key]

        conn = get_connection()
        try:
            positive_movies = self.get_user_positive_movies(
                conn,
                user_id,
                exclude_mids=exclude_from_training,
            )
            if not positive_movies:
                return None
            rated_mids = self.get_user_all_rated_mids(
                conn,
                user_id,
                exclude_mids=exclude_from_training,
            )
        finally:
            conn.close()

        payload = (positive_movies, rated_mids)
        self._user_context_cache[cache_key] = payload
        return payload

    def _get_evidence_bundle(
        self,
        user_id: int,
        positive_movies: list[dict],
        exclude_from_training: set[str],
    ) -> dict:
        actor_order_limit = int(self._config["actor_order_limit"])
        cache_key = (user_id, tuple(sorted(exclude_from_training)), actor_order_limit)
        if cache_key in self._evidence_cache:
            return self._score_candidates(self._evidence_cache[cache_key])

        seeds = [
            {
                "mid": str(movie["mid"]),
                "weight": float(movie["rating"]) / 5.0,
            }
            for movie in positive_movies
        ]

        evidence = self._fetch_evidence_from_graph(seeds, actor_order_limit)
        self._evidence_cache[cache_key] = evidence
        return self._score_candidates(evidence)

    def _fetch_evidence_from_graph(self, seeds: list[dict], actor_order_limit: int) -> dict:
        driver = Neo4jConnection.get_driver()
        candidate_evidence: dict[str, list[dict]] = defaultdict(list)

        with driver.session() as session:
            one_hop_rows = session.run(
                """
                UNWIND $seeds AS seed
                MATCH (seed_movie:Movie {mid: seed.mid})
                CALL (seed_movie, seed) {
                    MATCH (seed_movie)<-[:DIRECTED]-(p:Person)-[:DIRECTED]->(cand:Movie)
                    WHERE cand.mid <> seed.mid
                    RETURN cand.mid AS mid,
                           'director' AS relation,
                           [p.pid] AS entity_ids,
                           [p.name] AS entity_names,
                           seed.weight AS strength,
                           1 AS hits

                    UNION ALL

                    MATCH (seed_movie)<-[seed_act:ACTED_IN]-(p:Person)-[cand_act:ACTED_IN]->(cand:Movie)
                    WHERE cand.mid <> seed.mid
                      AND coalesce(seed_act.order, 9999) <= $actor_order_limit
                      AND coalesce(cand_act.order, 9999) <= $actor_order_limit
                    RETURN cand.mid AS mid,
                           'actor' AS relation,
                           [p.pid] AS entity_ids,
                           [p.name] AS entity_names,
                           seed.weight AS strength,
                           1 AS hits

                    UNION ALL

                    MATCH (seed_movie)-[:HAS_GENRE]->(g:Genre)<-[:HAS_GENRE]-(cand:Movie)
                    WHERE cand.mid <> seed.mid
                    WITH cand, seed, collect(DISTINCT g.name) AS shared_genres
                    RETURN cand.mid AS mid,
                           'genre' AS relation,
                           shared_genres[0..3] AS entity_ids,
                           shared_genres[0..3] AS entity_names,
                           seed.weight * CASE
                               WHEN size(shared_genres) >= 3 THEN 1.0
                               ELSE toFloat(size(shared_genres)) / 3.0
                           END AS strength,
                           size(shared_genres) AS hits
                }
                RETURN mid, relation, entity_ids, entity_names, sum(strength) AS strength, sum(hits) AS hits
                ORDER BY strength DESC
                LIMIT $query_limit
                """,
                seeds=seeds,
                actor_order_limit=actor_order_limit,
                query_limit=int(self._config["one_hop_query_limit"]),
            )
            for row in one_hop_rows:
                candidate_evidence[str(row["mid"])].append(
                    {
                        "relation": row["relation"],
                        "entity_ids": [str(entity_id) for entity_id in row["entity_ids"] if entity_id],
                        "entity_names": [str(name) for name in row["entity_names"] if name],
                        "strength": float(row["strength"]),
                        "hits": int(row["hits"]),
                    }
                )

            two_hop_rows = session.run(
                """
                UNWIND $seeds AS seed
                MATCH (seed_movie:Movie {mid: seed.mid})
                MATCH (seed_movie)<-[seed_act:ACTED_IN]-(p1:Person)-[bridge_in:ACTED_IN]->(bridge:Movie)
                MATCH (bridge)<-[bridge_out:ACTED_IN]-(p2:Person)-[cand_act:ACTED_IN]->(cand:Movie)
                WHERE cand.mid <> seed.mid
                  AND bridge.mid <> seed.mid
                  AND cand.mid <> bridge.mid
                  AND p1 <> p2
                  AND coalesce(seed_act.order, 9999) <= $actor_order_limit
                  AND coalesce(bridge_in.order, 9999) <= $actor_order_limit
                  AND coalesce(bridge_out.order, 9999) <= $actor_order_limit
                  AND coalesce(cand_act.order, 9999) <= $actor_order_limit
                RETURN cand.mid AS mid,
                       'actor_actor' AS relation,
                       [p2.pid] AS entity_ids,
                       [p2.name] AS entity_names,
                       sum(seed.weight) AS strength,
                       count(*) AS hits
                ORDER BY strength DESC
                LIMIT $query_limit
                """,
                seeds=seeds,
                actor_order_limit=actor_order_limit,
                query_limit=int(self._config["two_hop_query_limit"]),
            )
            for row in two_hop_rows:
                candidate_evidence[str(row["mid"])].append(
                    {
                        "relation": row["relation"],
                        "entity_ids": [str(entity_id) for entity_id in row["entity_ids"] if entity_id],
                        "entity_names": [str(name) for name in row["entity_names"] if name],
                        "strength": float(row["strength"]),
                        "hits": int(row["hits"]),
                    }
                )

        return {"candidate_evidence": candidate_evidence}

    def _score_candidates(self, evidence: dict) -> dict:
        weights = {
            REL_DIRECTOR: float(self._config["director_weight"]),
            REL_ACTOR: float(self._config["actor_weight"]),
            REL_GENRE: float(self._config["genre_weight"]),
            "actor_actor": float(self._config["two_hop_weight"]),
        }

        candidate_scores: dict[str, float] = defaultdict(float)
        candidate_paths: dict[str, int] = defaultdict(int)
        candidate_reasons: dict[str, list[str]] = defaultdict(list)
        candidate_reason_scores: dict[str, list[tuple[float, str]]] = defaultdict(list)

        for mid, records in evidence["candidate_evidence"].items():
            for record in records:
                relation = record["relation"]
                if relation == "actor_actor" and not self._config["enable_two_hop"]:
                    continue
                relation_weight = weights.get(relation, 0.0)
                if relation_weight <= 0:
                    continue

                penalty = 1.0
                if self._config["use_degree_penalty"]:
                    penalty = self._entity_penalty(relation, record["entity_ids"])

                contribution = relation_weight * record["strength"] * penalty
                if contribution <= 0:
                    continue

                candidate_scores[mid] += contribution
                candidate_paths[mid] += max(int(record["hits"]), 1)
                candidate_reason_scores[mid].append((contribution, self._reason_for_record(record)))

        for mid, reason_items in candidate_reason_scores.items():
            reason_items.sort(key=lambda item: item[0], reverse=True)
            deduped = []
            seen = set()
            for _, reason in reason_items:
                if reason and reason not in seen:
                    seen.add(reason)
                    deduped.append(reason)
                if len(deduped) >= 3:
                    break
            candidate_reasons[mid] = deduped

        return {
            "candidate_scores": candidate_scores,
            "candidate_paths": candidate_paths,
            "candidate_reasons": candidate_reasons,
        }

    def _entity_penalty(self, relation: str, entity_ids: list[str]) -> float:
        if not entity_ids:
            return 1.0
        base_relation = relation
        if relation == "actor_actor":
            base_relation = REL_ACTOR
        penalties = [
            safe_idf(self._entity_degree(base_relation, entity_id))
            for entity_id in entity_ids
        ]
        penalties = [value for value in penalties if value > 0]
        if not penalties:
            return 1.0
        return sum(penalties) / len(penalties)

    def _entity_degree(self, relation: str, entity_id: str) -> int:
        from app.algorithms.graph_cache import GraphMetadataCache

        return GraphMetadataCache.entity_degree(relation, entity_id)

    def _reason_for_record(self, record: dict) -> str:
        names = record["entity_names"]
        if record["relation"] == REL_DIRECTOR:
            return f"与你喜欢的电影有共同导演 {names[0]}" if names else "与你喜欢的电影有共同导演"
        if record["relation"] == REL_ACTOR:
            return f"有共同演员 {names[0]}" if names else "与你喜欢的电影有共同演员"
        if record["relation"] == REL_GENRE:
            if names:
                return f"同属 {'/'.join(names[:3])} 类型"
            return "与你喜欢的电影类型相近"
        if record["relation"] == "actor_actor":
            return f"通过演员关联发现 {names[0]} 参与的电影" if names else "通过演员二跳关系发现"
        return "基于知识图谱路径关联推荐"
