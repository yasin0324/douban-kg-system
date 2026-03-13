"""
CFKG mainline recommender: collaborative recall with KG reranking.
"""

from __future__ import annotations

import logging

from app.algorithms.base import BaseRecommender
from app.algorithms.content_based import ContentBasedRecommender
from app.algorithms.item_cf import ItemCFRecommender
from app.algorithms.kg_embed import KGEmbedRecommender
from app.algorithms.kg_path import KGPathRecommender

logger = logging.getLogger(__name__)

BEST_KG_PATH_PARAMS = {
    "actor_order_limit": 5,
    "actor_weight": 0.8,
    "director_weight": 1.0,
    "enable_two_hop": True,
    "genre_weight": 0.6,
    "two_hop_weight": 0.4,
    "use_degree_penalty": True,
}

BEST_KG_EMBED_PARAMS = {
    "centroid_weight": 0.2,
    "entity_overlap_weight": 0.6,
    "max_seed_weight": 0.2,
    "use_expanded_relations": True,
    "use_fusion_ranking": True,
}


class CFKGRecommender(BaseRecommender):
    name = "cfkg"
    display_name = "CFKG 主链路推荐"

    DEFAULT_CONFIG = {
        "item_cf_weight": 0.6,
        "kg_embed_weight": 0.3,
        "kg_path_weight": 0.1,
        "item_cf_recall": 300,
        "kg_embed_recall": 200,
        "kg_path_recall": 100,
        "content_recall": 100,
        "content_fallback_weight": 0.05,
        "min_candidate_pool": 150,
    }

    def __init__(self, **config):
        self._config = {**self.DEFAULT_CONFIG, **config}
        self._item_cf = ItemCFRecommender()
        self._kg_embed = KGEmbedRecommender(**BEST_KG_EMBED_PARAMS)
        self._kg_path = KGPathRecommender(**BEST_KG_PATH_PARAMS)
        self._content = ContentBasedRecommender()

    def set_params(self, **params):
        if params:
            self._config.update(params)

    @classmethod
    def parameter_grid(cls) -> list[dict]:
        grid = []
        for item_cf_weight, kg_embed_weight, kg_path_weight in (
            (0.60, 0.30, 0.10),
            (0.55, 0.35, 0.10),
            (0.60, 0.25, 0.15),
            (0.50, 0.40, 0.10),
        ):
            for item_cf_recall in (200, 300):
                grid.append(
                    {
                        "item_cf_weight": item_cf_weight,
                        "kg_embed_weight": kg_embed_weight,
                        "kg_path_weight": kg_path_weight,
                        "item_cf_recall": item_cf_recall,
                    }
                )
        return grid

    def recommend(
        self,
        user_id: int,
        n: int = 20,
        exclude_mids: set | None = None,
        exclude_from_training: set | None = None,
    ) -> list[dict]:
        exclude_mids = exclude_mids or set()
        exclude_from_training = exclude_from_training or set()

        branch_results = {
            "item_cf": self._safe_recommend(
                branch_name="item_cf",
                recommender=self._item_cf,
                user_id=user_id,
                n=int(self._config["item_cf_recall"]),
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
            "kg_embed": self._safe_recommend(
                branch_name="kg_embed",
                recommender=self._kg_embed,
                user_id=user_id,
                n=int(self._config["kg_embed_recall"]),
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
            "kg_path": self._safe_recommend(
                branch_name="kg_path",
                recommender=self._kg_path,
                user_id=user_id,
                n=int(self._config["kg_path_recall"]),
                exclude_mids=exclude_mids,
                exclude_from_training=exclude_from_training,
            ),
        }

        candidate_map = self._merge_branch_results(branch_results)
        content_results = []
        if not branch_results["item_cf"] or len(candidate_map) < int(self._config["min_candidate_pool"]):
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

        ranked = []
        for mid, payload in candidate_map.items():
            weighted_contributions = {}
            for branch_name, weight in active_weights.items():
                score = float(payload["scores"].get(branch_name, 0.0))
                if score > 0:
                    weighted_contributions[branch_name] = score * weight

            raw_score = sum(weighted_contributions.values())
            if raw_score <= 0:
                content_score = float(payload["scores"].get("content", 0.0))
                if content_score <= 0:
                    continue
                weighted_contributions["content"] = content_score * float(self._config["content_fallback_weight"])
                raw_score = weighted_contributions["content"]

            reasons = self._ordered_reasons(payload)
            source_algorithms = self._ordered_sources(weighted_contributions)
            if not reasons or not source_algorithms:
                continue

            ranked.append(
                {
                    "mid": mid,
                    "raw_score": raw_score,
                    "reason": reasons[0],
                    "reasons": reasons,
                    "source_algorithms": source_algorithms,
                }
            )

        if not ranked:
            return self._content_only_results(content_results, n)

        ranked.sort(
            key=lambda item: (
                item["raw_score"],
                len(item["source_algorithms"]),
                item["mid"],
            ),
            reverse=True,
        )
        max_score = max(item["raw_score"] for item in ranked)
        if max_score <= 0:
            return []

        results = []
        for item in ranked[:n]:
            results.append(
                {
                    "mid": item["mid"],
                    "score": round(item["raw_score"] / max_score, 4),
                    "reason": item["reason"],
                    "reasons": item["reasons"],
                    "source_algorithms": item["source_algorithms"],
                }
            )
        return results

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

    def _resolve_branch_weights(self, branch_results: dict[str, list[dict]]) -> dict[str, float]:
        configured = {
            "item_cf": float(self._config["item_cf_weight"]),
            "kg_embed": float(self._config["kg_embed_weight"]),
            "kg_path": float(self._config["kg_path_weight"]),
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
        for branch_name in ("item_cf", "kg_embed", "kg_path"):
            for row in branch_results.get(branch_name, []):
                self._merge_result_row(merged, branch_name, row)
        return merged

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

    def _ordered_reasons(self, payload: dict) -> list[str]:
        ordered = []
        for branch_name in ("kg_path", "kg_embed", "item_cf", "content"):
            reason = payload["reasons"].get(branch_name)
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
