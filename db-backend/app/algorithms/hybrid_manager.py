"""
图原生混合调度调度中心 (Graph-Hybrid Manager)
与老方案的预加热不同，本方案完全依赖图数据库引擎的即时运算。
Manager 主要职责为并行调度，将分数归一化，根据权重进行聚合并选出 Top-N。
"""
import asyncio
import logging
import time
from typing import List, Dict, Any

from app.algorithms.graph_content import get_graph_content_recommendations
from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_ppr import get_graph_ppr_recommendations

logger = logging.getLogger(__name__)


class HybridRecommendationManager:
    """混合推荐调度器单例"""
    
    def __init__(self, weights: Dict[str, float] | None = None, branch_timeouts_ms: Dict[str, int] | None = None):
        self.weights = weights or {
            "graph_ppr": 0.1,
            "graph_content": 0.2,
            "graph_cf": 0.7,
        }
        self.branch_timeouts_ms = branch_timeouts_ms or {
            "graph_ppr": 1200,
            "graph_content": 800,
            "graph_cf": 800,
        }
        self.min_candidates = {
            "graph_ppr": 3,
            "graph_content": 3,
            "graph_cf": 1,
        }
        
    def normalize_scores(self, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Min-Max 归一化单一源传来的原始分数到 [0, 1] 区间"""
        if not raw_results:
            return []
            
        scores = [item["score"] for item in raw_results]
        min_s = min(scores)
        max_s = max(scores)
        
        normalized = []
        for item in raw_results:
            n_item = item.copy()
            if max_s > min_s:
                n_item["score"] = (item["score"] - min_s) / (max_s - min_s)
            else:
                n_item["score"] = 1.0  # 全是相同分数时都给满分
            normalized.append(n_item)
            
        return normalized

    async def _call_branch(self, name: str, coroutine):
        start = time.perf_counter()
        try:
            results = await asyncio.wait_for(coroutine, timeout=self.branch_timeouts_ms[name] / 1000)
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.info("推荐分支 %s 返回 %s 条候选 (%sms)", name, len(results), duration_ms)
            return results
        except asyncio.TimeoutError:
            logger.warning("推荐分支 %s 超时，已自动降级", name)
        except Exception as exc:
            logger.warning("推荐分支 %s 异常，已自动降级: %s", name, exc)
        return []

    def resolve_branch_weights(self, branch_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
        active_weights = {}
        for name, weight in self.weights.items():
            if len(branch_results.get(name, [])) >= self.min_candidates[name]:
                active_weights[name] = weight

        total_weight = sum(active_weights.values())
        if total_weight <= 0:
            return {}

        return {name: weight / total_weight for name, weight in active_weights.items()}

    async def get_hybrid_recommendations(
        self,
        user_id: int,
        seed_movie_ids: List[str],
        seen_movie_ids: List[str] | None = None,
        exclude_mock_users: bool = True,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """主入口，提供带超时降级与动态门控的混合推荐。"""
        tasks = {
            "graph_cf": asyncio.create_task(self._call_branch(
                "graph_cf",
                get_graph_cf_recommendations(
                    user_id=user_id,
                    seed_movie_ids=seed_movie_ids,
                    seen_movie_ids=seen_movie_ids,
                    exclude_mock_users=exclude_mock_users,
                    limit=limit * 2,
                    timeout_ms=self.branch_timeouts_ms["graph_cf"],
                ),
            )),
            "graph_content": asyncio.create_task(self._call_branch(
                "graph_content",
                get_graph_content_recommendations(
                    user_id=user_id,
                    seed_movie_ids=seed_movie_ids,
                    seen_movie_ids=seen_movie_ids,
                    exclude_mock_users=exclude_mock_users,
                    limit=limit * 2,
                    timeout_ms=self.branch_timeouts_ms["graph_content"],
                ),
            )),
            "graph_ppr": asyncio.create_task(self._call_branch(
                "graph_ppr",
                get_graph_ppr_recommendations(
                    user_id=user_id,
                    seed_movie_ids=seed_movie_ids,
                    seen_movie_ids=seen_movie_ids,
                    exclude_mock_users=exclude_mock_users,
                    limit=limit * 2,
                    timeout_ms=self.branch_timeouts_ms["graph_ppr"],
                ),
            )),
        }
        branch_values = await asyncio.gather(*tasks.values())
        branch_results = dict(zip(tasks.keys(), branch_values))

        active_weights = self.resolve_branch_weights(branch_results)
        if not active_weights:
            return []

        normalized_results = {
            name: self.normalize_scores(results)
            for name, results in branch_results.items()
            if name in active_weights
        }

        movie_dict: Dict[str, Dict[str, Any]] = {}
        
        def _merge(norm_list: List[Dict[str, Any]], weight: float):
            for item in norm_list:
                mid = item["movie_id"]
                if mid not in movie_dict:
                    movie_dict[mid] = {
                        "movie_id": mid,
                        "title": item.get("title", ""),
                        "final_score": 0.0,
                        "reasons": set()
                    }
                movie_dict[mid]["final_score"] += item["score"] * weight
                for reason in item.get("reasons", []):
                    movie_dict[mid]["reasons"].add(reason)
                    
        for branch_name, weight in active_weights.items():
            _merge(normalized_results[branch_name], weight)
        
        hybrid_list = list(movie_dict.values())
        for m in hybrid_list:
            m["reasons"] = list(m["reasons"])
            
        hybrid_list.sort(key=lambda x: x["final_score"], reverse=True)
        
        return hybrid_list[:limit]

# 全局单例
manager = HybridRecommendationManager()
