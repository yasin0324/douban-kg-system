"""
图原生混合调度调度中心 (Graph-Hybrid Manager)
与老方案的预加热不同，本方案完全依赖图数据库引擎的即时运算。
Manager 主要职责为并行调度，将分数归一化，根据权重进行聚合并选出 Top-N。
"""
import asyncio
from typing import List, Dict, Any

from app.algorithms.graph_content import get_graph_content_recommendations
from app.algorithms.graph_cf import get_graph_cf_recommendations
from app.algorithms.graph_ppr import get_graph_ppr_recommendations


class HybridRecommendationManager:
    """混合推荐调度器单例"""
    
    def __init__(self):
        # 定义权重：PPR 30%, Content 30%, CF 40%
        self.weights = {
            "graph_ppr": 0.3,
            "graph_content": 0.3,
            "graph_cf": 0.4
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

    async def get_hybrid_recommendations(self, user_id: int, seed_movie_ids: List[str], limit: int = 20) -> List[Dict[str, Any]]:
        """主入口，提供混合推荐"""
        
        # 1. 并发请求三路图原生推荐
        cf_task = get_graph_cf_recommendations(user_id=user_id, limit=limit*2)
        content_task = get_graph_content_recommendations(user_id=user_id, seed_movie_ids=seed_movie_ids, limit=limit*2)
        ppr_task = get_graph_ppr_recommendations(user_id=user_id, seed_movie_ids=seed_movie_ids, limit=limit*2)
        
        cf_raw, content_raw, ppr_raw = await asyncio.gather(cf_task, content_task, ppr_task)
        
        # 2. 分别归一化
        cf_norm = self.normalize_scores(cf_raw)
        content_norm = self.normalize_scores(content_raw)
        ppr_norm = self.normalize_scores(ppr_raw)
        
        # 3. 结果合并聚合
        movie_dict: Dict[str, Dict[str, Any]] = {}
        
        # 内部处理函数
        def _merge(norm_list: List[Dict], weight: float):
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
                    
        _merge(cf_norm, self.weights["graph_cf"])
        _merge(content_norm, self.weights["graph_content"])
        _merge(ppr_norm, self.weights["graph_ppr"])
        
        # 4. 转换并排序
        hybrid_list = list(movie_dict.values())
        # 将 set 原因转成 list
        for m in hybrid_list:
            m["reasons"] = list(m["reasons"])
            
        hybrid_list.sort(key=lambda x: x["final_score"], reverse=True)
        
        return hybrid_list[:limit]

# 全局单例
manager = HybridRecommendationManager()
