"""
Path-based KG recommender with batched Cypher retrieval and cached evidence.
"""

from __future__ import annotations

from collections import defaultdict

from app.algorithms.base import BaseRecommender
from app.algorithms.graph_cache import (
    GraphMetadataCache,
    REL_ACTOR,
    REL_DIRECTOR,
    REL_GENRE,
    safe_idf,
)
from app.db.mysql import get_connection


class KGPathRecommender(BaseRecommender):
    name = "kg_path"
    display_name = "基于知识图谱路径的推荐"

    DEFAULT_CONFIG = {
        "director_weight": 1.0,
        "actor_weight": 0.6,
        "genre_weight": 0.4,
        "two_hop_weight": 0.2,
        "actor_order_limit": 5,
        "director_per_seed_limit": 30,
        "actor_per_seed_limit": 50,
        "genre_per_seed_limit": 50,
        "two_hop_per_seed_limit": 30,
        "genre_seed_entity_limit": 1,
        "genre_max_degree": 15000,
        "enable_two_hop": True,
        "use_degree_penalty": True,
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
                    "raw_score": score,
                    "score": round(score / max_score, 4),
                    "reason": reasons[0] if reasons else "基于知识图谱路径关联推荐",
                    "path_count": candidate_paths.get(mid, 0),
                }
            )

        results.sort(key=lambda item: (item["raw_score"], item["path_count"]), reverse=True)
        for item in results:
            item.pop("raw_score", None)
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
        cache_key = (
            user_id,
            tuple(sorted(exclude_from_training)),
            actor_order_limit,
            bool(self._config["enable_two_hop"]) and float(self._config["two_hop_weight"]) > 0,
            int(self._config["director_per_seed_limit"]),
            int(self._config["actor_per_seed_limit"]),
            int(self._config["genre_per_seed_limit"]),
            int(self._config["two_hop_per_seed_limit"]),
            int(self._config["genre_seed_entity_limit"]),
            int(self._config["genre_max_degree"]),
        )
        if cache_key in self._evidence_cache:
            return self._score_candidates(self._evidence_cache[cache_key])

        seeds = [
            {
                "mid": str(movie["mid"]),
                "weight": float(movie["rating"]) / 5.0,
            }
            for movie in positive_movies
        ]

        evidence = self._fetch_evidence_from_graph(
            seeds,
            actor_order_limit,
            include_two_hop=bool(self._config["enable_two_hop"]) and float(self._config["two_hop_weight"]) > 0,
        )
        self._evidence_cache[cache_key] = evidence
        return self._score_candidates(evidence)

    def _fetch_evidence_from_graph(
        self,
        seeds: list[dict],
        actor_order_limit: int,
        *,
        include_two_hop: bool,
    ) -> dict:
        candidate_evidence: dict[str, list[dict]] = defaultdict(list)
        profiles = GraphMetadataCache.movie_profiles()
        actor_index = GraphMetadataCache.inverted_index(REL_ACTOR)
        director_index = GraphMetadataCache.inverted_index(REL_DIRECTOR)
        genre_index = GraphMetadataCache.inverted_index(REL_GENRE)

        for seed in seeds:
            seed_mid = seed["mid"]
            seed_profile = profiles.get(seed_mid)
            if not seed_profile:
                continue
            seed_weight = float(seed["weight"])

            self._append_rows(
                candidate_evidence,
                self._build_one_hop_records(
                    relation=REL_DIRECTOR,
                    seed_mid=seed_mid,
                    seed_weight=seed_weight,
                    seed_entity_ids=seed_profile.directors,
                    inverted_index=director_index,
                    per_seed_limit=int(self._config["director_per_seed_limit"]),
                ),
            )
            self._append_rows(
                candidate_evidence,
                self._build_one_hop_records(
                    relation=REL_ACTOR,
                    seed_mid=seed_mid,
                    seed_weight=seed_weight,
                    seed_entity_ids=seed_profile.actor_ids(actor_order_limit),
                    inverted_index=actor_index,
                    per_seed_limit=int(self._config["actor_per_seed_limit"]),
                    candidate_profiles=profiles,
                    actor_order_limit=actor_order_limit,
                ),
            )
            self._append_rows(
                candidate_evidence,
                self._build_one_hop_records(
                    relation=REL_GENRE,
                    seed_mid=seed_mid,
                    seed_weight=seed_weight,
                    seed_entity_ids=self._select_genres(seed_profile.genres),
                    inverted_index=genre_index,
                    per_seed_limit=int(self._config["genre_per_seed_limit"]),
                ),
            )
            if include_two_hop:
                self._append_rows(
                    candidate_evidence,
                    self._build_two_hop_records(
                        seed_mid=seed_mid,
                        seed_profile=seed_profile,
                        seed_weight=seed_weight,
                        actor_index=actor_index,
                        profiles=profiles,
                        per_seed_limit=int(self._config["two_hop_per_seed_limit"]),
                        actor_order_limit=actor_order_limit,
                    ),
                )

        return {"candidate_evidence": candidate_evidence}

    def _build_one_hop_records(
        self,
        *,
        relation: str,
        seed_mid: str,
        seed_weight: float,
        seed_entity_ids: set[str],
        inverted_index: dict[str, set[str]],
        per_seed_limit: int,
        candidate_profiles: dict[str, object] | None = None,
        actor_order_limit: int | None = None,
    ) -> list[dict]:
        candidate_entities: dict[str, set[str]] = defaultdict(set)
        for entity_id in seed_entity_ids:
            for cand_mid in inverted_index.get(entity_id, set()):
                if cand_mid == seed_mid:
                    continue
                if relation == REL_ACTOR and candidate_profiles and actor_order_limit is not None:
                    cand_profile = candidate_profiles.get(cand_mid)
                    if not cand_profile or cand_profile.actor_orders.get(entity_id, 9999) > actor_order_limit:
                        continue
                candidate_entities[cand_mid].add(entity_id)

        records = []
        for cand_mid, shared_entities in candidate_entities.items():
            shared_ids = sorted(shared_entities)
            shared_count = len(shared_ids)
            if shared_count <= 0:
                continue

            if relation == REL_GENRE:
                strength = seed_weight * min(shared_count / 3.0, 1.0)
                entity_ids = shared_ids[:3]
            else:
                strength = seed_weight * float(shared_count)
                entity_ids = shared_ids[:5]

            records.append(
                {
                    "mid": cand_mid,
                    "relation": relation,
                    "entity_ids": entity_ids,
                    "entity_names": [self._entity_name(relation, entity_id) for entity_id in entity_ids],
                    "strength": strength,
                    "hits": shared_count,
                }
            )

        records.sort(key=lambda item: (item["strength"], item["hits"], item["mid"]), reverse=True)
        return records[:per_seed_limit]

    def _build_two_hop_records(
        self,
        *,
        seed_mid: str,
        seed_profile,
        seed_weight: float,
        actor_index: dict[str, set[str]],
        profiles: dict[str, object],
        per_seed_limit: int,
        actor_order_limit: int,
    ) -> list[dict]:
        candidate_entities: dict[str, set[str]] = defaultdict(set)
        seed_actors = seed_profile.actor_ids(actor_order_limit)
        for seed_actor in seed_actors:
            for bridge_mid in actor_index.get(seed_actor, set()):
                if bridge_mid == seed_mid:
                    continue
                bridge_profile = profiles.get(bridge_mid)
                if not bridge_profile:
                    continue
                if bridge_profile.actor_orders.get(seed_actor, 9999) > actor_order_limit:
                    continue
                for bridge_actor in bridge_profile.actor_ids(actor_order_limit):
                    if bridge_actor == seed_actor:
                        continue
                    for cand_mid in actor_index.get(bridge_actor, set()):
                        if cand_mid in {seed_mid, bridge_mid}:
                            continue
                        cand_profile = profiles.get(cand_mid)
                        if not cand_profile or cand_profile.actor_orders.get(bridge_actor, 9999) > actor_order_limit:
                            continue
                        candidate_entities[cand_mid].add(bridge_actor)

        records = []
        for cand_mid, shared_entities in candidate_entities.items():
            entity_ids = sorted(shared_entities)[:3]
            shared_count = len(shared_entities)
            if shared_count <= 0:
                continue
            records.append(
                {
                    "mid": cand_mid,
                    "relation": "actor_actor",
                    "entity_ids": entity_ids,
                    "entity_names": [self._entity_name(REL_ACTOR, entity_id) for entity_id in entity_ids],
                    "strength": seed_weight * float(shared_count),
                    "hits": shared_count,
                }
            )

        records.sort(key=lambda item: (item["strength"], item["hits"], item["mid"]), reverse=True)
        return records[:per_seed_limit]

    def _append_rows(self, candidate_evidence: dict[str, list[dict]], rows: list[dict]) -> None:
        for row in rows:
            entity_ids = [str(entity_id) for entity_id in row["entity_ids"] if entity_id]
            if not entity_ids:
                continue
            candidate_evidence[str(row["mid"])].append(
                {
                    "relation": row["relation"],
                    "entity_ids": entity_ids,
                    "entity_names": [str(name) for name in row["entity_names"] if name],
                    "strength": float(row["strength"]),
                    "hits": int(row["hits"]),
                }
            )

    def _select_genres(self, genres: set[str]) -> set[str]:
        if not genres:
            return set()

        max_degree = int(self._config["genre_max_degree"])
        ordered = sorted(
            genres,
            key=lambda genre: (GraphMetadataCache.entity_degree(REL_GENRE, genre), genre),
        )
        filtered = [
            genre
            for genre in ordered
            if GraphMetadataCache.entity_degree(REL_GENRE, genre) <= max_degree
        ]
        if not filtered:
            filtered = ordered[:1]
        return set(filtered[: int(self._config["genre_seed_entity_limit"])])

    def _entity_name(self, relation: str, entity_id: str) -> str:
        if relation in {REL_DIRECTOR, REL_ACTOR}:
            return GraphMetadataCache.person_name(entity_id)
        return entity_id

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
