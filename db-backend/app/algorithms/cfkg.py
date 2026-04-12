"""
CFKG mainline recommender: item_cf + kg_embed candidate generation with kg_path reranking.
"""

from __future__ import annotations

import logging

from app.algorithms.base import BaseRecommender
from app.algorithms.content_based import ContentBasedRecommender
from app.algorithms.item_cf import ItemCFRecommender
from app.algorithms.kg_embed import KGEmbedRecommender
from app.algorithms.kg_path import KGPathRecommender

logger = logging.getLogger(__name__)

DEFAULT_KG_EMBED_INIT_KWARGS = {
    "use_expanded_relations": True,
    "use_fusion_ranking": True,
    "use_user_rating_relations": True,
    "user_relation_weight": 0.6,
    "entity_overlap_weight": 0.2,
    "centroid_weight": 0.1,
    "max_seed_weight": 0.1,
}

DEFAULT_KG_PATH_INIT_KWARGS = {
    "use_user_behavior_paths": True,
    "use_expanded_relations": True,
    "shared_audience_weight": 0.6,
    "director_weight": 0.2,
    "actor_weight": 0.2,
    "genre_weight": 0.2,
    "two_hop_weight": 0.1,
    "region_weight": 0.1,
    "language_weight": 0.1,
    "content_type_weight": 0.05,
    "year_bucket_weight": 0.05,
    "enable_two_hop": True,
    "use_degree_penalty": True,
    "use_user_activity_penalty": True,
}


class CFKGRecommender(BaseRecommender):
    name = "cfkg"
    display_name = "CFKG 主链路推荐"
    EVAL_USE_CANDIDATE_SCORING = True
    DELIVERABLE_CONFIG = {
        "item_cf_weight": 0.3,
        "kg_embed_weight": 0.7,
        "agreement_bonus": 0.02,
        "consensus_weight": 0.0,
        "item_cf_recall": 400,
        "kg_embed_recall": 300,
        "kg_path_rerank_topn": 100,
        "kg_path_rerank_weight": 0.0,
        "content_recall": 100,
        "content_fallback_weight": 0.0,
        "min_candidate_pool": 200,
        "use_kg_path_explanations": True,
        "kg_path_explain_topn": 20,
    }

    DEFAULT_CONFIG = dict(DELIVERABLE_CONFIG)

    def __init__(self, **config):
        kg_embed_init_kwargs = dict(config.pop("kg_embed_init_kwargs", {}) or {})
        kg_path_init_kwargs = dict(config.pop("kg_path_init_kwargs", {}) or {})
        self._config = {**self.DEFAULT_CONFIG, **config}
        self._kg_embed_init_kwargs = {
            **DEFAULT_KG_EMBED_INIT_KWARGS,
            **kg_embed_init_kwargs,
        }
        self._kg_path_init_kwargs = {
            **DEFAULT_KG_PATH_INIT_KWARGS,
            **kg_path_init_kwargs,
        }
        self._item_cf = ItemCFRecommender()
        self._kg_embed = KGEmbedRecommender(**self._kg_embed_init_kwargs)
        self._kg_path = KGPathRecommender(**self._kg_path_init_kwargs)
        self._content = ContentBasedRecommender()

    def set_params(self, **params):
        if params:
            self._config.update(params)

    def clear_runtime_caches(self):
        self._item_cf.clear_runtime_caches()
        self._kg_embed.clear_runtime_caches()
        self._kg_path.clear_runtime_caches()
        self._content.clear_runtime_caches()

    def get_user_positive_movies(
        self,
        conn,
        user_id: int,
        threshold: float = 3.5,
        exclude_mids: set | None = None,
    ) -> list[dict]:
        return self._kg_embed.get_user_positive_movies(
            conn,
            user_id,
            threshold=threshold,
            exclude_mids=exclude_mids,
        )

    @classmethod
    def parameter_grid(cls) -> list[dict]:
        return [
            {
                "item_cf_weight": cls.DELIVERABLE_CONFIG["item_cf_weight"],
                "kg_embed_weight": cls.DELIVERABLE_CONFIG["kg_embed_weight"],
                "agreement_bonus": cls.DELIVERABLE_CONFIG["agreement_bonus"],
                "consensus_weight": cls.DELIVERABLE_CONFIG["consensus_weight"],
                "item_cf_recall": cls.DELIVERABLE_CONFIG["item_cf_recall"],
                "kg_embed_recall": cls.DELIVERABLE_CONFIG["kg_embed_recall"],
                "kg_path_rerank_topn": cls.DELIVERABLE_CONFIG["kg_path_rerank_topn"],
                "kg_path_rerank_weight": cls.DELIVERABLE_CONFIG["kg_path_rerank_weight"],
                "content_fallback_weight": cls.DELIVERABLE_CONFIG["content_fallback_weight"],
                "use_kg_path_explanations": cls.DELIVERABLE_CONFIG["use_kg_path_explanations"],
                "kg_path_explain_topn": cls.DELIVERABLE_CONFIG["kg_path_explain_topn"],
            }
        ]

    @classmethod
    def ablation_configs(cls) -> dict[str, dict]:
        return {
            "kg_embed 主导直排": {
                "item_cf_weight": 0.0,
                "kg_embed_weight": 1.0,
                "agreement_bonus": 0.0,
                "consensus_weight": 0.0,
                "use_kg_path_explanations": False,
            },
            "+item_cf 线性辅助": {
                "consensus_weight": 0.0,
                "use_kg_path_explanations": False,
            },
            "+kg_path 解释": {},
        }

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
        candidate_mids = list(candidate_mids or [])
        if not candidate_mids:
            return []

        branch_results = {
            "item_cf": self._safe_score_candidates(
                branch_name="item_cf",
                recommender=self._item_cf,
                user_id=user_id,
                candidate_mids=candidate_mids,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
            "kg_embed": self._safe_score_candidates(
                branch_name="kg_embed",
                recommender=self._kg_embed,
                user_id=user_id,
                candidate_mids=candidate_mids,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
        }

        candidate_map = self._merge_branch_results(branch_results)
        ranked = self._build_direct_candidate_ranked(candidate_map)
        if not ranked:
            return []

        if self._config["use_kg_path_explanations"]:
            self._attach_kg_path_explanations(
                candidate_map=candidate_map,
                ranked=ranked,
                user_id=user_id,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            )

        max_score = max(item["final_score"] for item in ranked)
        if max_score <= 0:
            return []

        results = []
        output_items = ranked if n is None else ranked[:n]
        for item in output_items:
            payload = candidate_map.get(item["mid"], {})
            include_kg_path_reason = bool(payload.get("reasons", {}).get("kg_path"))
            reasons = self._ordered_reasons(payload, include_kg_path=include_kg_path_reason)
            if not reasons:
                continue
            results.append(
                {
                    "mid": item["mid"],
                    "score": round(item["final_score"] / max_score, 4),
                    "reason": reasons[0],
                    "reasons": reasons,
                    "source_algorithms": self._ordered_sources(item["weighted_contributions"]),
                }
            )
        return results

    def recommend(
        self,
        user_id: int,
        n: int = 20,
        exclude_mids: set | None = None,
        exclude_from_training: set | None = None,
    ) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()
        item_cf_request_n = self._branch_request_n(int(self._config["item_cf_recall"]), n)
        kg_embed_request_n = self._branch_request_n(int(self._config["kg_embed_recall"]), n)

        branch_results = {
            "item_cf": self._safe_recommend(
                branch_name="item_cf",
                recommender=self._item_cf,
                user_id=user_id,
                n=item_cf_request_n,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
            "kg_embed": self._safe_recommend(
                branch_name="kg_embed",
                recommender=self._kg_embed,
                user_id=user_id,
                n=kg_embed_request_n,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
        }

        candidate_map = self._merge_branch_results(branch_results)
        content_results = []
        if len(candidate_map) < int(self._config["min_candidate_pool"]):
            content_results = self._safe_recommend(
                branch_name="content",
                recommender=self._content,
                user_id=user_id,
                n=int(self._config["content_recall"]),
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            )
            self._merge_content_results(candidate_map, content_results)

        active_weights = self._resolve_branch_weights(branch_results)
        if not active_weights:
            return self._content_only_results(content_results, n)

        stage1_ranked = self._build_stage1_ranked(candidate_map, active_weights)
        if not stage1_ranked:
            return self._content_only_results(content_results, n)

        rerank_weight = float(self._config["kg_path_rerank_weight"])
        if rerank_weight > 0:
            shortlist_mids = [
                item["mid"]
                for item in stage1_ranked[: int(self._config["kg_path_rerank_topn"])]
            ]
            kg_path_results = self._safe_score_candidates(
                branch_name="kg_path",
                recommender=self._kg_path,
                user_id=user_id,
                candidate_mids=shortlist_mids,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            )
            self._merge_scored_branch_results(candidate_map, "kg_path", kg_path_results)

        final_ranked = self._build_final_ranked(stage1_ranked, candidate_map)
        if not final_ranked:
            return self._content_only_results(content_results, n)

        max_score = max(item["final_score"] for item in final_ranked)
        if max_score <= 0:
            return self._content_only_results(content_results, n)

        results = []
        for item in final_ranked[:n]:
            results.append(
                {
                    "mid": item["mid"],
                    "score": round(item["final_score"] / max_score, 4),
                    "reason": item["reasons"][0],
                    "reasons": item["reasons"],
                    "source_algorithms": item["source_algorithms"],
                }
            )
        return results

    def _branch_request_n(self, configured_recall: int, requested_n: int) -> int:
        # Offline evaluator asks for a very large n and then re-ranks sampled candidates outside the algorithm.
        # In that mode, truncating branch results to a small recall artificially removes the held-out positive.
        if int(requested_n) >= 1000:
            return int(requested_n)
        return max(int(configured_recall), int(requested_n))

    def _safe_recommend(
        self,
        *,
        branch_name: str,
        recommender,
        user_id: int,
        n: int,
        exclude_mids: set[str],
        exclude_from_training: set[str],
    ) -> list[dict]:
        try:
            return recommender.recommend(
                user_id=user_id,
                n=n,
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            )
        except Exception:
            logger.warning("CFKG 分支 %s 执行失败: user_id=%s", branch_name, user_id, exc_info=True)
            return []

    def _safe_score_candidates(
        self,
        *,
        branch_name: str,
        recommender,
        user_id: int,
        candidate_mids: list[str],
        exclude_mids: set[str],
        exclude_from_training: set[str],
    ) -> list[dict]:
        if not candidate_mids:
            return []
        try:
            if hasattr(recommender, "score_candidates"):
                return recommender.score_candidates(
                    user_id=user_id,
                    candidate_mids=candidate_mids,
                    exclude_from_training=exclude_from_training,
                    exclude_mids=exclude_mids,
                    n=len(candidate_mids),
                )
            fallback = recommender.recommend(
                user_id=user_id,
                n=len(candidate_mids),
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            )
            allowed = set(candidate_mids)
            return [row for row in fallback if str(row.get("mid") or "") in allowed]
        except Exception:
            logger.warning("CFKG 分支 %s shortlist 打分失败: user_id=%s", branch_name, user_id, exc_info=True)
            return []

    def _resolve_branch_weights(self, branch_results: dict[str, list[dict]]) -> dict[str, float]:
        configured = {
            "item_cf": float(self._config["item_cf_weight"]),
            "kg_embed": float(self._config["kg_embed_weight"]),
        }
        available = {
            branch_name: weight
            for branch_name, weight in configured.items()
            if weight > 0 and branch_results.get(branch_name)
        }
        total = sum(available.values())
        if total <= 0:
            return {}
        return {
            branch_name: weight / total
            for branch_name, weight in available.items()
        }

    def _merge_branch_results(self, branch_results: dict[str, list[dict]]) -> dict[str, dict]:
        merged: dict[str, dict] = {}
        for branch_name in ("item_cf", "kg_embed"):
            for row in branch_results.get(branch_name, []):
                self._merge_result_row(merged, branch_name, row)
        return merged

    def _merge_scored_branch_results(self, merged: dict[str, dict], branch_name: str, results: list[dict]) -> None:
        for row in results:
            self._merge_result_row(merged, branch_name, row)

    def _merge_content_results(self, merged: dict[str, dict], content_results: list[dict]) -> None:
        for row in content_results:
            self._merge_result_row(merged, "content", row)

    def _merge_result_row(self, merged: dict[str, dict], branch_name: str, row: dict) -> None:
        mid = str(row.get("mid") or "")
        if not mid:
            return
        payload = merged.setdefault(
            mid,
            {
                "scores": {},
                "reasons": {},
            },
        )
        payload["scores"][branch_name] = float(row.get("score") or 0.0)
        reason = str(row.get("reason") or "").strip()
        if reason:
            payload["reasons"][branch_name] = reason

    def _build_stage1_ranked(self, candidate_map: dict[str, dict], active_weights: dict[str, float]) -> list[dict]:
        ranked = []
        agreement_bonus = float(self._config["agreement_bonus"])
        consensus_weight = float(self._config["consensus_weight"])
        content_fallback_weight = float(self._config["content_fallback_weight"])
        item_cf_aux_weight = self._item_cf_aux_weight(active_weights)
        item_cf_fallback_weight = float(active_weights.get("item_cf", 0.0))

        for mid, payload in candidate_map.items():
            stage1_contributions = {}
            stage1_score = 0.0
            kg_embed_score = float(payload["scores"].get("kg_embed", 0.0))
            item_cf_score = float(payload["scores"].get("item_cf", 0.0))

            if kg_embed_score > 0:
                stage1_contributions["kg_embed"] = kg_embed_score
                stage1_score += kg_embed_score
                if item_cf_score > 0 and item_cf_aux_weight > 0:
                    contribution = item_cf_aux_weight * item_cf_score
                    stage1_contributions["item_cf"] = contribution
                    stage1_score += contribution
                if item_cf_score > 0 and consensus_weight > 0:
                    stage1_score += self._consensus_contribution(
                        kg_embed_score=kg_embed_score,
                        item_cf_score=item_cf_score,
                        consensus_weight=consensus_weight,
                    )
            elif item_cf_score > 0 and item_cf_fallback_weight > 0:
                contribution = item_cf_fallback_weight * item_cf_score
                stage1_contributions["item_cf"] = contribution
                stage1_score += contribution

            overlap_flag = int(
                item_cf_score > 0
                and kg_embed_score > 0
            )
            if overlap_flag:
                stage1_score += agreement_bonus

            content_score = float(payload["scores"].get("content", 0.0))
            if content_score > 0:
                content_contribution = content_fallback_weight * content_score
                stage1_contributions["content"] = content_contribution
                stage1_score += content_contribution

            if stage1_score <= 0:
                continue

            ranked.append(
                {
                    "mid": mid,
                    "stage1_score": stage1_score,
                    "stage1_contributions": stage1_contributions,
                }
            )

        ranked.sort(
            key=lambda item: (
                item["stage1_score"],
                len(item["stage1_contributions"]),
                item["mid"],
            ),
            reverse=True,
        )
        return ranked

    def _item_cf_aux_weight(self, active_weights: dict[str, float]) -> float:
        kg_embed_weight = float(active_weights.get("kg_embed", 0.0))
        item_cf_weight = float(active_weights.get("item_cf", 0.0))
        if kg_embed_weight <= 0 or item_cf_weight <= 0:
            return 0.0
        return item_cf_weight / kg_embed_weight

    def _configured_item_cf_aux_weight(self) -> float:
        kg_embed_weight = float(self._config["kg_embed_weight"])
        item_cf_weight = float(self._config["item_cf_weight"])
        if kg_embed_weight <= 0 or item_cf_weight <= 0:
            return 0.0
        return item_cf_weight / kg_embed_weight

    def _build_direct_candidate_ranked(self, candidate_map: dict[str, dict]) -> list[dict]:
        ranked = []
        agreement_bonus = float(self._config["agreement_bonus"])
        consensus_weight = float(self._config["consensus_weight"])
        item_cf_aux_weight = self._configured_item_cf_aux_weight()
        item_cf_fallback_weight = float(self._config["item_cf_weight"])

        for mid, payload in candidate_map.items():
            kg_embed_score = float(payload["scores"].get("kg_embed", 0.0))
            item_cf_score = float(payload["scores"].get("item_cf", 0.0))
            weighted_contributions = {}
            final_score = 0.0

            if kg_embed_score > 0:
                weighted_contributions["kg_embed"] = kg_embed_score
                final_score += kg_embed_score
                if item_cf_score > 0 and item_cf_aux_weight > 0:
                    contribution = item_cf_aux_weight * item_cf_score
                    weighted_contributions["item_cf"] = contribution
                    final_score += contribution
                if item_cf_score > 0 and consensus_weight > 0:
                    final_score += self._consensus_contribution(
                        kg_embed_score=kg_embed_score,
                        item_cf_score=item_cf_score,
                        consensus_weight=consensus_weight,
                    )
                if item_cf_score > 0 and agreement_bonus > 0:
                    final_score += agreement_bonus
            elif item_cf_score > 0 and item_cf_fallback_weight > 0:
                contribution = item_cf_fallback_weight * item_cf_score
                weighted_contributions["item_cf"] = contribution
                final_score += contribution

            if final_score <= 0:
                continue

            ranked.append(
                {
                    "mid": mid,
                    "final_score": final_score,
                    "weighted_contributions": weighted_contributions,
                }
            )

        ranked.sort(
            key=lambda item: (
                item["final_score"],
                len(item["weighted_contributions"]),
                item["mid"],
            ),
            reverse=True,
        )
        return ranked

    def _consensus_contribution(
        self,
        *,
        kg_embed_score: float,
        item_cf_score: float,
        consensus_weight: float,
    ) -> float:
        if consensus_weight <= 0 or kg_embed_score <= 0 or item_cf_score <= 0:
            return 0.0
        return consensus_weight * min(kg_embed_score, item_cf_score)

    def _attach_kg_path_explanations(
        self,
        *,
        candidate_map: dict[str, dict],
        ranked: list[dict],
        user_id: int,
        exclude_mids: set[str],
        exclude_from_training: set[str],
    ) -> None:
        shortlist_mids = [item["mid"] for item in ranked[: int(self._config["kg_path_explain_topn"])]]
        if not shortlist_mids:
            return
        kg_path_results = self._safe_score_candidates(
            branch_name="kg_path",
            recommender=self._kg_path,
            user_id=user_id,
            candidate_mids=shortlist_mids,
            exclude_mids=exclude_mids,
            exclude_from_training=exclude_from_training,
        )
        for row in kg_path_results:
            mid = str(row.get("mid") or "")
            reason = str(row.get("reason") or "").strip()
            if not mid or not reason:
                continue
            payload = candidate_map.setdefault(mid, {"scores": {}, "reasons": {}})
            payload["reasons"]["kg_path"] = reason

    def _build_final_ranked(self, stage1_ranked: list[dict], candidate_map: dict[str, dict]) -> list[dict]:
        rerank_weight = float(self._config["kg_path_rerank_weight"])
        ranked = []

        for item in stage1_ranked:
            mid = item["mid"]
            payload = candidate_map.get(mid, {})
            stage1_score = float(item["stage1_score"])
            stage1_contributions = dict(item["stage1_contributions"])
            kg_path_score = float(payload.get("scores", {}).get("kg_path", 0.0))

            if rerank_weight > 0 and kg_path_score > 0:
                final_contributions = {
                    branch_name: contribution * (1.0 - rerank_weight)
                    for branch_name, contribution in stage1_contributions.items()
                }
                final_contributions["kg_path"] = rerank_weight * kg_path_score
                final_score = sum(final_contributions.values())
            else:
                final_contributions = stage1_contributions
                final_score = stage1_score

            reasons = self._ordered_reasons(payload, include_kg_path=kg_path_score > 0)
            source_algorithms = self._ordered_sources(final_contributions)
            if not reasons or not source_algorithms or final_score <= 0:
                continue

            ranked.append(
                {
                    "mid": mid,
                    "final_score": final_score,
                    "reasons": reasons,
                    "source_algorithms": source_algorithms,
                }
            )

        ranked.sort(
            key=lambda item: (
                item["final_score"],
                len(item["source_algorithms"]),
                item["mid"],
            ),
            reverse=True,
        )
        return ranked

    def _ordered_reasons(self, payload: dict, *, include_kg_path: bool) -> list[str]:
        ordered = []
        priority = []
        if include_kg_path:
            priority.append("kg_path")
        priority.extend(["kg_embed", "item_cf", "content"])
        for branch_name in priority:
            reason = payload.get("reasons", {}).get(branch_name)
            if reason and reason not in ordered:
                ordered.append(reason)
        return ordered

    def _ordered_sources(self, weighted_contributions: dict[str, float]) -> list[str]:
        ordered = sorted(
            weighted_contributions.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        return [branch_name for branch_name, contribution in ordered if contribution > 0]

    def _content_only_results(self, content_results: list[dict], n: int) -> list[dict]:
        if not content_results:
            return []

        max_score = max(float(row.get("score") or 0.0) for row in content_results)
        if max_score <= 0:
            return []

        results = []
        for row in content_results[:n]:
            raw_score = float(row.get("score") or 0.0)
            if raw_score <= 0:
                continue
            reason = str(row.get("reason") or "基于你的观影偏好特征匹配")
            results.append(
                {
                    "mid": str(row["mid"]),
                    "score": round(raw_score / max_score, 4),
                    "reason": reason,
                    "reasons": [reason],
                    "source_algorithms": ["content"],
                }
            )
        return results
