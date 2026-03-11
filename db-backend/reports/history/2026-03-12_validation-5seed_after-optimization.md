# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 99_negatives)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 验证集用户数: **40**
- 测试集用户数: **161**

## K = 5

| 算法 | Recall@5 | NDCG@5 | Hit@5 | Precision@5 |
|------|------|------|------|------|
| 基于内容的推荐 | 0.2832 ± 0.0165 | 0.1727 ± 0.0088 | 0.2832 ± 0.0165 | 0.0566 ± 0.0033 |
| 基于物品的协同过滤 | 0.8162 ± 0.0030 | 0.8077 ± 0.0033 | 0.8162 ± 0.0030 | 0.1632 ± 0.0006 |
| 基于知识图谱路径的推荐 | 0.0745 ± 0.0088 | 0.0430 ± 0.0055 | 0.0745 ± 0.0088 | 0.0149 ± 0.0018 |
| 基于知识图谱嵌入的推荐 | 0.4012 ± 0.0150 | 0.2722 ± 0.0092 | 0.4012 ± 0.0150 | 0.0803 ± 0.0030 |

## K = 10

| 算法 | Recall@10 | NDCG@10 | Hit@10 | Precision@10 |
|------|------|------|------|------|
| 基于内容的推荐 | 0.4186 ± 0.0145 | 0.2162 ± 0.0065 | 0.4186 ± 0.0145 | 0.0419 ± 0.0014 |
| 基于物品的协同过滤 | 0.8335 ± 0.0025 | 0.8131 ± 0.0030 | 0.8335 ± 0.0025 | 0.0833 ± 0.0003 |
| 基于知识图谱路径的推荐 | 0.2025 ± 0.0030 | 0.0835 ± 0.0034 | 0.2025 ± 0.0030 | 0.0203 ± 0.0003 |
| 基于知识图谱嵌入的推荐 | 0.5938 ± 0.0145 | 0.3339 ± 0.0055 | 0.5938 ± 0.0145 | 0.0594 ± 0.0014 |

## K = 20

| 算法 | Recall@20 | NDCG@20 | Hit@20 | Precision@20 |
|------|------|------|------|------|
| 基于内容的推荐 | 0.6162 ± 0.0127 | 0.2658 ± 0.0048 | 0.6162 ± 0.0127 | 0.0308 ± 0.0006 |
| 基于物品的协同过滤 | 0.8609 ± 0.0031 | 0.8202 ± 0.0029 | 0.8609 ± 0.0031 | 0.0431 ± 0.0001 |
| 基于知识图谱路径的推荐 | 0.3503 ± 0.0084 | 0.1208 ± 0.0036 | 0.3503 ± 0.0084 | 0.0175 ± 0.0004 |
| 基于知识图谱嵌入的推荐 | 0.7764 ± 0.0141 | 0.3805 ± 0.0076 | 0.7764 ± 0.0141 | 0.0388 ± 0.0007 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |
|------|-------------|--------------|--------------|
| 基于内容的推荐 | 0.0231 ± 0.0001 | 0.8416 ± 0.0018 | 0.2248 |
| 基于物品的协同过滤 | 0.0225 ± 0.0001 | 0.8928 ± 0.0011 | 0.0109 |
| 基于知识图谱路径的推荐 | 0.0225 ± 0.0001 | 0.8963 ± 0.0011 | 1.6609 |
| 基于知识图谱嵌入的推荐 | 0.0231 ± 0.0000 | 0.8416 ± 0.0021 | 3.8148 |

## Best Params

- **基于内容的推荐 (content)**: `{}`
- **基于物品的协同过滤 (item_cf)**: `{}`
- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_weight": 0.4, "use_degree_penalty": true}`
- **基于知识图谱嵌入的推荐 (kg_embed)**: `{"centroid_weight": 0.2, "entity_overlap_weight": 0.6, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | Recall@10 | NDCG@10 | Hit@10 | Params |
|------|-----------|---------|--------|--------|
| 1-hop | 0.2025 ± 0.0030 | 0.0802 ± 0.0027 | 0.2025 ± 0.0030 | `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": false, "genre_weight": 0.6, "two_hop_weight": 0.4, "use_degree_penalty": false}` |
| +2-hop | 0.2025 ± 0.0030 | 0.0828 ± 0.0028 | 0.2025 ± 0.0030 | `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_weight": 0.4, "use_degree_penalty": false}` |
| +IDF weighting | 0.2025 ± 0.0030 | 0.0835 ± 0.0034 | 0.2025 ± 0.0030 | `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_weight": 0.4, "use_degree_penalty": true}` |

### 基于知识图谱嵌入的推荐

| 消融 | Recall@10 | NDCG@10 | Hit@10 | Params |
|------|-----------|---------|--------|--------|
| 原始三关系 | 0.4683 ± 0.0165 | 0.2557 ± 0.0130 | 0.4683 ± 0.0165 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": false, "use_fusion_ranking": false}` |
| 扩图三元组 | 0.4633 ± 0.0063 | 0.2436 ± 0.0058 | 0.4633 ± 0.0063 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": true, "use_fusion_ranking": false}` |
| 扩图三元组+融合排序 | 0.5615 ± 0.0145 | 0.3116 ± 0.0047 | 0.5615 ± 0.0145 | `{"centroid_weight": 0.4, "entity_overlap_weight": 0.4, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}` |
