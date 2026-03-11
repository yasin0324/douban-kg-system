"""
推荐算法注册表 — 所有可用算法的统一入口
"""

from app.algorithms.content_based import ContentBasedRecommender
from app.algorithms.item_cf import ItemCFRecommender
from app.algorithms.kg_path import KGPathRecommender
from app.algorithms.kg_embed import KGEmbedRecommender

# 算法注册表: name -> class
ALGORITHMS = {
    "content": ContentBasedRecommender,
    "item_cf": ItemCFRecommender,
    "kg_path": KGPathRecommender,
    "kg_embed": KGEmbedRecommender,
}

ALGORITHM_NAMES = list(ALGORITHMS.keys())

__all__ = ["ALGORITHMS", "ALGORITHM_NAMES"]
