"""
Knowledge-graph embedding recommender with expanded structural triples.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from collections import defaultdict
from threading import Lock
from typing import ClassVar

import numpy as np

from app.algorithms.base import BaseRecommender
from app.algorithms.graph_cache import (
    CORE_RELATIONS,
    EXPANDED_RELATIONS,
    GraphMetadataCache,
    RATED_POSITIVE_RELATION,
    REL_ACTOR,
    REL_CONTENT_TYPE,
    REL_DIRECTOR,
    REL_GENRE,
    REL_LANGUAGE,
    REL_REGION,
    REL_YEAR_BUCKET,
    safe_idf,
)
from app.config import settings
from app.db.mysql import get_connection

logger = logging.getLogger(__name__)

EMBED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "embeddings")


def _signal_weight(row: dict) -> float:
    value = row.get("signal_weight")
    if value is not None:
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            return 0.0
    rating = row.get("rating")
    if rating is None:
        return 0.0
    try:
        return max(float(rating) / 5.0, 0.0)
    except (TypeError, ValueError):
        return 0.0


class KGEmbedRecommender(BaseRecommender):
    name = "kg_embed"
    display_name = "基于知识图谱嵌入的推荐"
    _shared_artifacts_by_scope: ClassVar[dict[str, dict]] = {}
    _shared_artifacts_lock: ClassVar[Lock] = Lock()

    EMBED_DIM = 64
    LEARNING_RATE = 0.01
    MARGIN = 1.0
    MAX_EPOCHS = 200
    BATCH_SIZE = 4096
    VALIDATION_RATIO = 0.1
    EARLY_STOP_PATIENCE = 3
    EARLY_STOP_EVAL_EVERY = 5
    RANDOM_SEED = 42
    OVERLAP_RELATION_WEIGHTS = {
        REL_DIRECTOR: 1.0,
        REL_ACTOR: 0.6,
        REL_GENRE: 0.4,
        REL_REGION: 0.2,
        REL_LANGUAGE: 0.2,
        REL_CONTENT_TYPE: 0.1,
        REL_YEAR_BUCKET: 0.1,
    }
    DEFAULT_CONFIG = {
        "use_expanded_relations": True,
        "use_fusion_ranking": True,
        "centroid_weight": 0.4,
        "max_seed_weight": 0.2,
        "entity_overlap_weight": 0.4,
        "use_user_rating_relations": False,
        "user_relation_weight": 0.0,
        "artifact_profile": None,
        "behavior_user_source": "all",
        "max_positive_rating_seeds": 30,
        "max_like_seeds": 10,
        "max_wish_seeds": 0,
    }

    def __init__(self, **config):
        self._config = {**self.DEFAULT_CONFIG, **config}
        self._user_component_cache: dict[tuple[str, int, tuple[str, ...]], dict] = {}
        self._user_context_cache: dict[tuple[int, tuple[str, ...]], tuple[list[dict], set[str]] | None] = {}

    def set_params(self, **params):
        if not params:
            return
        prev_scope = self._scope_name()
        self._config.update(params)
        if prev_scope != self._scope_name():
            # Scope change requires different embedding artifacts, but caches of other scopes remain reusable.
            return

    def clear_runtime_caches(self):
        self._user_component_cache.clear()
        self._user_context_cache.clear()

    @classmethod
    def parameter_grid(cls) -> list[dict]:
        grid = []
        for user_relation_weight in (0.4, 0.6, 0.8):
            for entity_overlap_weight in (0.1, 0.2, 0.3):
                for centroid_weight in (0.0, 0.1, 0.2):
                    max_seed_weight = round(
                        1.0 - user_relation_weight - entity_overlap_weight - centroid_weight,
                        4,
                    )
                    if max_seed_weight < 0:
                        continue
                    grid.append(
                        {
                            "use_expanded_relations": True,
                            "use_fusion_ranking": True,
                            "use_user_rating_relations": True,
                            "user_relation_weight": user_relation_weight,
                            "centroid_weight": centroid_weight,
                            "max_seed_weight": max_seed_weight,
                            "entity_overlap_weight": entity_overlap_weight,
                        }
                    )
        return grid

    @classmethod
    def ablation_configs(cls) -> dict[str, dict]:
        return {
            "结构嵌入": {
                "use_expanded_relations": True,
                "use_fusion_ranking": True,
                "use_user_rating_relations": False,
                "user_relation_weight": 0.0,
                "centroid_weight": 0.4,
                "max_seed_weight": 0.2,
                "entity_overlap_weight": 0.4,
            },
            "结构嵌入+用户三元组": {
                "use_expanded_relations": True,
                "use_fusion_ranking": True,
                "use_user_rating_relations": True,
                "user_relation_weight": 1.0,
                "centroid_weight": 0.0,
                "max_seed_weight": 0.0,
                "entity_overlap_weight": 0.0,
            },
            "全量融合": {
                "use_expanded_relations": True,
                "use_fusion_ranking": True,
                "use_user_rating_relations": True,
                "user_relation_weight": 0.6,
                "centroid_weight": 0.1,
                "max_seed_weight": 0.1,
                "entity_overlap_weight": 0.2,
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
        return self.score_candidates(
            user_id=user_id,
            candidate_mids=None,
            exclude_from_training=exclude_from_training,
            exclude_mids=exclude_mids,
            n=n,
        )

    def score_candidates(
        self,
        user_id: int,
        candidate_mids: list[str] | set[str] | tuple[str, ...] | None,
        exclude_from_training: set | None = None,
        *,
        exclude_mids: set | None = None,
        n: int | None = None,
    ) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()

        artifacts = self._load_or_train()
        if not artifacts:
            return []

        user_context = self._get_user_context(user_id, exclude_from_training)
        if user_context is None:
            return []

        positive_movies, rated_mids = user_context
        exclude_all = rated_mids | exclude_mids
        user_components = self._get_user_components(user_id, positive_movies, exclude_from_training, artifacts)
        if user_components is None:
            return []

        movie_mids = artifacts["movie_mid_list"]
        valid_mask = np.ones(len(movie_mids), dtype=bool)
        if candidate_mids is not None:
            allowed_mids = {str(mid) for mid in candidate_mids if mid}
            valid_mask[:] = False
            for mid in allowed_mids:
                idx = artifacts["mid_to_movie_idx"].get(mid)
                if idx is not None:
                    valid_mask[idx] = True
        for mid in exclude_all:
            idx = artifacts["mid_to_movie_idx"].get(mid)
            if idx is not None:
                valid_mask[idx] = False

        return self._build_ranked_results(
            artifacts=artifacts,
            user_components=user_components,
            valid_mask=valid_mask,
            n=n,
        )

    def _build_ranked_results(
        self,
        *,
        artifacts: dict,
        user_components: dict,
        valid_mask: np.ndarray,
        n: int | None,
    ) -> list[dict]:
        if not np.any(valid_mask):
            return []

        movie_mids = artifacts["movie_mid_list"]
        user_relation_scores = self._normalize_vector(user_components["user_relation_scores"], valid_mask)
        centroid_scores = self._normalize_vector(user_components["centroid_scores"], valid_mask)
        max_seed_scores = self._normalize_vector(user_components["max_seed_scores"], valid_mask)
        overlap_scores = self._normalize_vector(user_components["entity_overlap_scores"], valid_mask)

        if self._config["use_fusion_ranking"]:
            final_scores = (
                float(self._config["user_relation_weight"]) * user_relation_scores
                + float(self._config["centroid_weight"]) * centroid_scores
                + float(self._config["max_seed_weight"]) * max_seed_scores
                + float(self._config["entity_overlap_weight"]) * overlap_scores
            )
        else:
            final_scores = centroid_scores

        results = []
        for idx, final_score in enumerate(final_scores):
            if not valid_mask[idx] or final_score <= 0:
                continue
            mid = movie_mids[idx]
            results.append(
                {
                    "mid": mid,
                    "score": round(float(final_score), 4),
                    "reason": self._reason_for_movie(
                        mid=mid,
                        user_relation_score=float(user_relation_scores[idx]),
                        centroid_score=float(centroid_scores[idx]),
                        max_seed_score=float(max_seed_scores[idx]),
                        overlap_score=float(overlap_scores[idx]),
                        overlap_reasons=user_components["top_overlap_reasons"].get(mid, []),
                    ),
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        if n is None:
            return results
        return results[:n]

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
            max_positive_ratings=int(self._config["max_positive_rating_seeds"]),
            max_likes=int(self._config["max_like_seeds"]),
            max_wishes=int(self._config["max_wish_seeds"]),
        )

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

    def _get_user_components(
        self,
        user_id: int,
        positive_movies: list[dict],
        exclude_from_training: set[str],
        artifacts: dict,
    ) -> dict | None:
        cache_key = (self._scope_name(), user_id, tuple(sorted(exclude_from_training)))
        if cache_key in self._user_component_cache:
            return self._user_component_cache[cache_key]

        positive_mids = [str(movie["mid"]) for movie in positive_movies]
        seed_indices = [
            artifacts["mid_to_movie_idx"][mid]
            for mid in positive_mids
            if mid in artifacts["mid_to_movie_idx"]
        ]
        if not seed_indices:
            return None

        seed_weights = np.array(
            [
                _signal_weight(movie)
                for movie in positive_movies
                if str(movie["mid"]) in artifacts["mid_to_movie_idx"]
            ],
            dtype=np.float32,
        )
        if seed_weights.sum() <= 0:
            return None
        seed_weights = seed_weights / seed_weights.sum()

        seed_vectors = artifacts["movie_matrix"][seed_indices]
        user_vec = np.average(seed_vectors, axis=0, weights=seed_weights)
        user_norm = np.linalg.norm(user_vec)
        if user_norm <= 0:
            return None
        user_vec = user_vec / user_norm

        centroid_scores = np.maximum(artifacts["movie_matrix"] @ user_vec, 0.0)
        seed_sims = np.maximum(artifacts["movie_matrix"] @ seed_vectors.T, 0.0)
        max_seed_scores = np.max(seed_sims * seed_weights[np.newaxis, :], axis=1)
        overlap_scores, overlap_reasons = self._entity_overlap_components(
            positive_movies=positive_movies,
            artifacts=artifacts,
        )
        user_relation_scores = self._user_relation_components(
            user_id=user_id,
            artifacts=artifacts,
            exclude_from_training=exclude_from_training,
        )

        payload = {
            "user_relation_scores": user_relation_scores,
            "centroid_scores": centroid_scores,
            "max_seed_scores": max_seed_scores,
            "entity_overlap_scores": overlap_scores,
            "top_overlap_reasons": overlap_reasons,
        }
        self._user_component_cache[cache_key] = payload
        return payload

    def _user_relation_components(
        self,
        *,
        user_id: int,
        artifacts: dict,
        exclude_from_training: set[str],
    ) -> np.ndarray:
        scores = np.zeros(len(artifacts["movie_mid_list"]), dtype=np.float32)
        if not self._config["use_user_rating_relations"]:
            return scores
        if exclude_from_training and not self._artifact_supports_holdout(user_id, exclude_from_training, artifacts):
            return scores

        user_idx = artifacts.get("entity_to_idx", {}).get(f"user_{user_id}")
        relation_idx = artifacts.get("relation_to_idx", {}).get(RATED_POSITIVE_RELATION)
        entity_embeddings = artifacts.get("entity_embeddings")
        relation_embeddings = artifacts.get("relation_embeddings")
        if (
            user_idx is None
            or relation_idx is None
            or entity_embeddings is None
            or relation_embeddings is None
        ):
            return scores

        target_vec = entity_embeddings[user_idx] + relation_embeddings[relation_idx]
        target_norm = float(np.linalg.norm(target_vec))
        if target_norm <= 0:
            return scores
        target_vec = target_vec / target_norm
        return np.maximum(artifacts["movie_matrix"] @ target_vec, 0.0)

    def _artifact_supports_holdout(
        self,
        user_id: int,
        exclude_from_training: set[str],
        artifacts: dict,
    ) -> bool:
        if not exclude_from_training:
            return True
        expected_mid = (artifacts.get("holdout_positive_by_user") or {}).get(str(user_id))
        if not expected_mid:
            return False
        return {str(expected_mid)} == {str(mid) for mid in exclude_from_training if mid}

    def _entity_overlap_components(self, positive_movies: list[dict], artifacts: dict) -> tuple[np.ndarray, dict[str, list[str]]]:
        scores = np.zeros(len(artifacts["movie_mid_list"]), dtype=np.float32)
        top_reason_scores: dict[str, dict[str, float]] = defaultdict(dict)
        relations = EXPANDED_RELATIONS if self._config["use_expanded_relations"] else CORE_RELATIONS
        profiles = GraphMetadataCache.movie_profiles()

        for movie in positive_movies:
            mid = str(movie["mid"])
            profile = profiles.get(mid)
            if not profile:
                continue
            rating_weight = _signal_weight(movie)
            if rating_weight <= 0:
                continue

            for relation in relations:
                entity_ids = profile.relation_entities(
                    relation,
                    actor_top_only=(relation == REL_ACTOR),
                )
                relation_weight = self.OVERLAP_RELATION_WEIGHTS[relation]
                for entity_id in entity_ids:
                    contribution = rating_weight * relation_weight * safe_idf(
                        GraphMetadataCache.entity_degree(relation, entity_id)
                    )
                    if contribution <= 0:
                        continue
                    for candidate_mid in GraphMetadataCache.inverted_index(relation).get(entity_id, set()):
                        idx = artifacts["mid_to_movie_idx"].get(candidate_mid)
                        if idx is None:
                            continue
                        scores[idx] += contribution
                        reason = self._overlap_reason(relation, entity_id)
                        prev = top_reason_scores[candidate_mid].get(reason, 0.0)
                        if contribution > prev:
                            top_reason_scores[candidate_mid][reason] = contribution

        overlap_reasons: dict[str, list[str]] = {}
        for mid, reason_scores in top_reason_scores.items():
            ordered = sorted(reason_scores.items(), key=lambda item: item[1], reverse=True)
            overlap_reasons[mid] = [reason for reason, _ in ordered[:3]]

        return scores, overlap_reasons

    def _overlap_reason(self, relation: str, entity_id: str) -> str:
        entity_name = str(entity_id)
        if relation in {REL_DIRECTOR, REL_ACTOR}:
            entity_name = GraphMetadataCache.person_name(str(entity_id))

        if relation == REL_DIRECTOR:
            return f"偏好相同导演 {entity_name}"
        if relation == REL_ACTOR:
            return f"偏好相同演员 {entity_name}"
        if relation == REL_GENRE:
            return f"偏好相同类型 {entity_name}"
        if relation == REL_REGION:
            return f"偏好相同地区 {entity_name}"
        if relation == REL_LANGUAGE:
            return f"偏好相同语言 {entity_name}"
        if relation == REL_CONTENT_TYPE:
            return f"偏好相同内容形式 {entity_name}"
        if relation == REL_YEAR_BUCKET:
            return f"偏好相近年代 {entity_name}"
        return "图谱实体重叠"

    def _reason_for_movie(
        self,
        *,
        mid: str,
        user_relation_score: float,
        centroid_score: float,
        max_seed_score: float,
        overlap_score: float,
        overlap_reasons: list[str],
    ) -> str:
        if user_relation_score >= max(centroid_score, max_seed_score, overlap_score):
            return "与具有相似正反馈轨迹的用户兴趣一致"
        if self._config["use_fusion_ranking"] and overlap_score >= max(centroid_score, max_seed_score):
            if overlap_reasons:
                return f"基于知识图谱实体重叠推荐：{overlap_reasons[0]}"
            return "基于知识图谱实体重叠推荐"
        if max_seed_score > centroid_score:
            return "与您高评分电影在知识图谱嵌入空间中最相近"
        if overlap_reasons:
            return f"综合嵌入语义和实体关系推荐：{overlap_reasons[0]}"
        return "基于知识图谱嵌入空间的语义相似性推荐"

    def _normalize_vector(self, values: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
        normalized = np.zeros_like(values, dtype=np.float32)
        valid_values = values[valid_mask]
        if valid_values.size == 0:
            return normalized
        max_value = float(np.max(valid_values))
        min_value = float(np.min(valid_values))
        if max_value - min_value <= 1e-8:
            normalized[valid_mask] = (valid_values > 0).astype(np.float32)
            return normalized
        normalized[valid_mask] = (valid_values - min_value) / (max_value - min_value)
        normalized[~valid_mask] = 0.0
        return normalized

    def _scope_name(self) -> str:
        return self._artifact_scope()

    def _artifact_scope(self, *, use_expanded_relations: bool | None = None) -> str:
        base = "expanded" if (
            self._config["use_expanded_relations"] if use_expanded_relations is None else use_expanded_relations
        ) else "core"
        profile = self._resolved_artifact_profile()
        if not profile["include_user_positive_relations"]:
            return base

        digest = hashlib.sha1(
            json.dumps(
                profile,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:12]
        return (
            f"{base}_userpos_{profile['user_source']}_"
            f"{profile['holdout_strategy']}_{profile['version']}_{digest}"
        )

    def _resolved_artifact_profile(self) -> dict:
        raw_profile = self._config.get("artifact_profile") or {}
        holdout_positive_by_user = {
            str(user_id): str(mid)
            for user_id, mid in sorted(
                (raw_profile.get("holdout_positive_by_user") or {}).items(),
                key=lambda item: (str(item[0]), str(item[1])),
            )
            if mid
        }
        return {
            "version": str(raw_profile.get("version", "v1")),
            "user_source": str(raw_profile.get("user_source", self._config["behavior_user_source"])),
            "holdout_strategy": str(raw_profile.get("holdout_strategy", "none")),
            "include_user_positive_relations": bool(
                raw_profile.get("include_user_positive_relations", self._config["use_user_rating_relations"])
            ),
            "holdout_positive_by_user": holdout_positive_by_user,
        }

    def _artifact_paths(self, scope: str) -> tuple[str, str]:
        os.makedirs(EMBED_DIR, exist_ok=True)
        return (
            os.path.join(EMBED_DIR, f"transe_embeddings_{scope}.npz"),
            os.path.join(EMBED_DIR, f"transe_meta_{scope}.json"),
        )

    @classmethod
    def clear_shared_artifacts(cls):
        with cls._shared_artifacts_lock:
            cls._shared_artifacts_by_scope = {}

    @classmethod
    def preload_artifacts(
        cls,
        *,
        allow_training: bool | None = None,
        artifact_profile: dict | None = None,
    ) -> dict[str, bool]:
        profile = artifact_profile or {}
        recommender = cls(
            artifact_profile=artifact_profile,
            use_user_rating_relations=bool(
                profile.get(
                    "include_user_positive_relations",
                    profile.get("holdout_positive_by_user"),
                )
            ),
            behavior_user_source=str(profile.get("user_source", "all")),
        )
        readiness = {}
        for use_expanded_relations in (False, True):
            scope = recommender._artifact_scope(use_expanded_relations=use_expanded_relations)
            readiness[scope] = (
                recommender._load_or_train(
                    use_expanded_relations=use_expanded_relations,
                    allow_training=allow_training,
                )
                is not None
            )
        return readiness

    @classmethod
    def preload_existing_artifacts(cls, *, artifact_profile: dict | None = None):
        return cls.preload_artifacts(allow_training=False, artifact_profile=artifact_profile)

    def _load_or_train(
        self,
        *,
        use_expanded_relations: bool | None = None,
        allow_training: bool | None = None,
    ) -> dict | None:
        scope = self._artifact_scope(use_expanded_relations=use_expanded_relations)
        with self._shared_artifacts_lock:
            artifacts = self._shared_artifacts_by_scope.get(scope)
        if artifacts is not None:
            return artifacts

        embed_path, meta_path = self._artifact_paths(scope)
        if os.path.exists(embed_path) and os.path.exists(meta_path):
            logger.info("加载已有 %s TransE 嵌入向量...", scope)
            artifacts = self._load_artifacts(embed_path, meta_path)
            with self._shared_artifacts_lock:
                self._shared_artifacts_by_scope[scope] = artifacts
            return artifacts

        if allow_training is None:
            allow_training = bool(settings.RECOMMEND_ENABLE_ONLINE_EMBED_TRAINING)
        if not allow_training:
            logger.warning("未找到 %s TransE 嵌入文件，且已禁用在线训练，跳过 KG-Embed 初始化", scope)
            return None

        logger.info("未找到 %s TransE 嵌入文件，开始训练...", scope)
        artifacts = self._train_transe(
            use_expanded_relations=(
                self._config["use_expanded_relations"]
                if use_expanded_relations is None
                else use_expanded_relations
            )
        )
        if artifacts is None:
            return None
        with self._shared_artifacts_lock:
            self._shared_artifacts_by_scope[scope] = artifacts
        return artifacts

    def _load_artifacts(self, embed_path: str, meta_path: str) -> dict:
        data = np.load(embed_path)
        with open(meta_path, "r", encoding="utf-8") as file_obj:
            meta = json.load(file_obj)

        entity_embeddings = data["entity_embeddings"].astype(np.float32)
        relation_embeddings = (
            data["relation_embeddings"].astype(np.float32)
            if "relation_embeddings" in data
            else None
        )
        entity_to_idx = meta["entity_to_idx"]
        relation_to_idx = meta.get("relation_to_idx", {})
        idx_to_entity = {int(key): value for key, value in meta["idx_to_entity"].items()}
        movie_mid_list = meta["movie_mid_list"]

        movie_indices = []
        filtered_movie_mids = []
        for mid in movie_mid_list:
            entity_key = f"movie_{mid}"
            idx = entity_to_idx.get(entity_key)
            if idx is None:
                continue
            filtered_movie_mids.append(mid)
            movie_indices.append(idx)

        movie_matrix = entity_embeddings[movie_indices]
        movie_norms = np.linalg.norm(movie_matrix, axis=1, keepdims=True)
        movie_norms = np.maximum(movie_norms, 1e-8)
        movie_matrix = movie_matrix / movie_norms

        return {
            "entity_embeddings": entity_embeddings,
            "relation_embeddings": relation_embeddings,
            "entity_to_idx": entity_to_idx,
            "relation_to_idx": relation_to_idx,
            "idx_to_entity": idx_to_entity,
            "movie_mid_list": filtered_movie_mids,
            "mid_to_movie_idx": {mid: idx for idx, mid in enumerate(filtered_movie_mids)},
            "movie_matrix": movie_matrix.astype(np.float32),
            "artifact_profile": meta.get("artifact_profile", {}),
            "holdout_positive_by_user": (meta.get("artifact_profile", {}) or {}).get("holdout_positive_by_user", {}),
        }

    def _train_transe(self, *, use_expanded_relations: bool) -> dict | None:
        triples, movie_mids, entity_types, relation_types = self._export_triples(
            use_expanded_relations=use_expanded_relations
        )
        if not triples:
            logger.warning("没有可用三元组数据，无法训练 TransE")
            return None

        rng = np.random.default_rng(self.RANDOM_SEED)

        entities = sorted(entity_types)
        relations = sorted(relation_types)
        entity_to_idx = {entity: idx for idx, entity in enumerate(entities)}
        relation_to_idx = {relation: idx for idx, relation in enumerate(relations)}
        idx_to_entity = {idx: entity for entity, idx in entity_to_idx.items()}
        relation_idx_to_types = {
            relation_to_idx[relation]: relation_types[relation] for relation in relations
        }

        entity_type_by_idx = {entity_to_idx[entity]: entity_types[entity] for entity in entities}
        type_to_entity_indices: dict[str, np.ndarray] = {}
        for entity_type in sorted(set(entity_type_by_idx.values())):
            indices = [idx for idx, cur_type in entity_type_by_idx.items() if cur_type == entity_type]
            type_to_entity_indices[entity_type] = np.array(indices, dtype=np.int32)

        triple_indices = np.array(
            [(entity_to_idx[h], relation_to_idx[r], entity_to_idx[t]) for h, r, t in triples],
            dtype=np.int32,
        )
        rng.shuffle(triple_indices)
        split_idx = max(1, int(len(triple_indices) * (1.0 - self.VALIDATION_RATIO)))
        train_triples = triple_indices[:split_idx]
        val_triples = triple_indices[split_idx:]
        if len(val_triples) == 0:
            val_triples = train_triples[: min(1024, len(train_triples))]

        d = self.EMBED_DIM
        entity_emb = rng.uniform(-6.0 / math.sqrt(d), 6.0 / math.sqrt(d), (len(entities), d)).astype(np.float32)
        relation_emb = rng.uniform(-6.0 / math.sqrt(d), 6.0 / math.sqrt(d), (len(relations), d)).astype(np.float32)

        entity_emb = self._normalize_rows(entity_emb)
        best_entity_emb = entity_emb.copy()
        best_relation_emb = relation_emb.copy()
        best_val_loss = float("inf")
        patience = 0

        scope = self._artifact_scope(use_expanded_relations=use_expanded_relations)
        logger.info(
            "开始训练 %s TransE: triples=%s, train=%s, val=%s",
            scope,
            len(triple_indices),
            len(train_triples),
            len(val_triples),
        )

        for epoch in range(1, self.MAX_EPOCHS + 1):
            shuffled = train_triples[rng.permutation(len(train_triples))]
            total_loss = 0.0

            for start in range(0, len(shuffled), self.BATCH_SIZE):
                batch = shuffled[start : start + self.BATCH_SIZE]
                (
                    batch_loss,
                    entity_emb,
                    relation_emb,
                ) = self._train_batch(
                    batch=batch,
                    entity_emb=entity_emb,
                    relation_emb=relation_emb,
                    relation_idx_to_types=relation_idx_to_types,
                    type_to_entity_indices=type_to_entity_indices,
                    rng=rng,
                )
                total_loss += batch_loss

            if epoch % self.EARLY_STOP_EVAL_EVERY != 0:
                continue

            val_loss = self._margin_loss(
                triples=val_triples,
                entity_emb=entity_emb,
                relation_emb=relation_emb,
                relation_idx_to_types=relation_idx_to_types,
                type_to_entity_indices=type_to_entity_indices,
                rng=rng,
            )
            logger.info(
                "  Epoch %s/%s, train_loss=%.4f, val_loss=%.4f",
                epoch,
                self.MAX_EPOCHS,
                total_loss / max(len(train_triples), 1),
                val_loss,
            )

            if val_loss + 1e-6 < best_val_loss:
                best_val_loss = val_loss
                best_entity_emb = entity_emb.copy()
                best_relation_emb = relation_emb.copy()
                patience = 0
            else:
                patience += 1
                if patience >= self.EARLY_STOP_PATIENCE:
                    logger.info("  验证集无提升，提前停止训练")
                    break

        embed_path, meta_path = self._artifact_paths(scope)
        np.savez(embed_path, entity_embeddings=best_entity_emb, relation_embeddings=best_relation_emb)
        with open(meta_path, "w", encoding="utf-8") as file_obj:
            json.dump(
                {
                    "entity_to_idx": entity_to_idx,
                    "relation_to_idx": relation_to_idx,
                    "idx_to_entity": {str(idx): entity for idx, entity in idx_to_entity.items()},
                    "movie_mid_list": sorted(movie_mids),
                    "artifact_profile": self._resolved_artifact_profile(),
                },
                file_obj,
                ensure_ascii=False,
                indent=2,
            )

        return self._load_artifacts(embed_path, meta_path)

    def _train_batch(
        self,
        *,
        batch: np.ndarray,
        entity_emb: np.ndarray,
        relation_emb: np.ndarray,
        relation_idx_to_types: dict[int, tuple[str, str]],
        type_to_entity_indices: dict[str, np.ndarray],
        rng: np.random.Generator,
    ) -> tuple[float, np.ndarray, np.ndarray]:
        negatives = self._sample_negative_batch(
            batch=batch,
            relation_idx_to_types=relation_idx_to_types,
            type_to_entity_indices=type_to_entity_indices,
            rng=rng,
        )
        h_idx = batch[:, 0]
        r_idx = batch[:, 1]
        t_idx = batch[:, 2]
        nh_idx = negatives[:, 0]
        nt_idx = negatives[:, 2]

        pos_dist = entity_emb[h_idx] + relation_emb[r_idx] - entity_emb[t_idx]
        neg_dist = entity_emb[nh_idx] + relation_emb[r_idx] - entity_emb[nt_idx]
        pos_score = np.sum(pos_dist ** 2, axis=1)
        neg_score = np.sum(neg_dist ** 2, axis=1)
        loss = np.maximum(0.0, self.MARGIN + pos_score - neg_score)
        active = loss > 0

        if not np.any(active):
            return 0.0, entity_emb, relation_emb

        lr = self.LEARNING_RATE
        active_pos_dist = pos_dist[active]
        active_neg_dist = neg_dist[active]
        active_h = h_idx[active]
        active_t = t_idx[active]
        active_r = r_idx[active]
        active_nh = nh_idx[active]
        active_nt = nt_idx[active]

        np.subtract.at(entity_emb, active_h, 2 * lr * active_pos_dist)
        np.add.at(entity_emb, active_t, 2 * lr * active_pos_dist)
        np.subtract.at(relation_emb, active_r, 2 * lr * active_pos_dist)

        np.add.at(entity_emb, active_nh, 2 * lr * active_neg_dist)
        np.subtract.at(entity_emb, active_nt, 2 * lr * active_neg_dist)
        np.add.at(relation_emb, active_r, 2 * lr * active_neg_dist)

        entity_emb = self._normalize_rows(entity_emb)
        return float(np.sum(loss)), entity_emb, relation_emb

    def _export_triples(
        self,
        *,
        use_expanded_relations: bool | None = None,
    ) -> tuple[list[tuple[str, str, str]], set[str], dict[str, str], dict[str, tuple[str, str]]]:
        scope = self._config["use_expanded_relations"] if use_expanded_relations is None else use_expanded_relations
        artifact_profile = self._resolved_artifact_profile()
        return GraphMetadataCache.build_triples(
            use_expanded_relations=scope,
            include_inverse=True,
            include_user_positive_relations=bool(artifact_profile["include_user_positive_relations"]),
            user_source=artifact_profile["user_source"],
            holdout_positive_by_user=artifact_profile["holdout_positive_by_user"],
        )

    def _margin_loss(
        self,
        *,
        triples: np.ndarray,
        entity_emb: np.ndarray,
        relation_emb: np.ndarray,
        relation_idx_to_types: dict[int, tuple[str, str]],
        type_to_entity_indices: dict[str, np.ndarray],
        rng: np.random.Generator,
    ) -> float:
        negatives = self._sample_negative_batch(
            batch=triples,
            relation_idx_to_types=relation_idx_to_types,
            type_to_entity_indices=type_to_entity_indices,
            rng=rng,
        )
        h_idx = triples[:, 0]
        r_idx = triples[:, 1]
        t_idx = triples[:, 2]
        nh_idx = negatives[:, 0]
        nt_idx = negatives[:, 2]

        pos_dist = entity_emb[h_idx] + relation_emb[r_idx] - entity_emb[t_idx]
        neg_dist = entity_emb[nh_idx] + relation_emb[r_idx] - entity_emb[nt_idx]
        pos_score = np.sum(pos_dist ** 2, axis=1)
        neg_score = np.sum(neg_dist ** 2, axis=1)
        loss = np.maximum(0.0, self.MARGIN + pos_score - neg_score)
        return float(np.mean(loss))

    def _sample_negative_batch(
        self,
        *,
        batch: np.ndarray,
        relation_idx_to_types: dict[int, tuple[str, str]],
        type_to_entity_indices: dict[str, np.ndarray],
        rng: np.random.Generator,
    ) -> np.ndarray:
        negatives = batch.copy()
        replace_head_mask = rng.random(len(batch)) < 0.5

        for relation_idx, (head_type, tail_type) in relation_idx_to_types.items():
            rel_mask = batch[:, 1] == relation_idx
            if not np.any(rel_mask):
                continue

            head_mask = rel_mask & replace_head_mask
            tail_mask = rel_mask & ~replace_head_mask

            if np.any(head_mask):
                pool = type_to_entity_indices[head_type]
                sampled = pool[rng.integers(0, len(pool), np.count_nonzero(head_mask))]
                negatives[head_mask, 0] = sampled
            if np.any(tail_mask):
                pool = type_to_entity_indices[tail_type]
                sampled = pool[rng.integers(0, len(pool), np.count_nonzero(tail_mask))]
                negatives[tail_mask, 2] = sampled

        return negatives

    def _normalize_rows(self, matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        return matrix / norms
