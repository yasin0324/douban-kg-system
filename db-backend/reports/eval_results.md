# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 99_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['cfkg', 'content', 'item_cf', 'kg_path', 'kg_embed']**
- 验证集用户数: **42**
- 测试集用户数: **168**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.3714 ± 0.0111 | 0.3155 ± 0.0080 |
| 基于内容的推荐 | 0.1941 ± 0.0139 | 0.1216 ± 0.0041 |
| 基于物品的协同过滤 | 0.7560 ± 0.0065 | 0.5848 ± 0.0095 |
| 基于知识图谱路径的推荐 | 0.2548 ± 0.0070 | 0.2213 ± 0.0063 |
| 基于知识图谱嵌入的推荐 | 0.3988 ± 0.0141 | 0.2884 ± 0.0115 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.4726 ± 0.0061 | 0.3482 ± 0.0064 |
| 基于内容的推荐 | 0.3369 ± 0.0081 | 0.1677 ± 0.0049 |
| 基于物品的协同过滤 | 0.8119 ± 0.0061 | 0.6032 ± 0.0081 |
| 基于知识图谱路径的推荐 | 0.3690 ± 0.0038 | 0.2584 ± 0.0049 |
| 基于知识图谱嵌入的推荐 | 0.5381 ± 0.0122 | 0.3332 ± 0.0100 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.5250 ± 0.0045 | 0.3615 ± 0.0063 |
| 基于内容的推荐 | 0.5441 ± 0.0123 | 0.2200 ± 0.0044 |
| 基于物品的协同过滤 | 0.8631 ± 0.0038 | 0.6161 ± 0.0080 |
| 基于知识图谱路径的推荐 | 0.4500 ± 0.0029 | 0.2790 ± 0.0052 |
| 基于知识图谱嵌入的推荐 | 0.7357 ± 0.0117 | 0.3833 ± 0.0077 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |
|------|-------------|--------------|--------------|
| CFKG 主链路推荐 | 0.0228 ± 0.0001 | 0.8939 ± 0.0018 | 20.6325 |
| 基于内容的推荐 | 0.0232 ± 0.0001 | 0.8192 ± 0.0037 | 0.2421 |
| 基于物品的协同过滤 | 0.0228 ± 0.0001 | 0.9044 ± 0.0007 | 0.5213 |
| 基于知识图谱路径的推荐 | 0.0229 ± 0.0001 | 0.8982 ± 0.0015 | 2.9928 |
| 基于知识图谱嵌入的推荐 | 0.0233 ± 0.0001 | 0.8396 ± 0.0011 | 7.1223 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"item_cf_recall": 300, "item_cf_weight": 0.6, "kg_embed_weight": 0.3, "kg_path_weight": 0.1}`
- **基于内容的推荐 (content)**: `{}`
- **基于物品的协同过滤 (item_cf)**: `{}`
- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": true}`
- **基于知识图谱嵌入的推荐 (kg_embed)**: `{"centroid_weight": 0.2, "entity_overlap_weight": 0.6, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 1-hop | 0.3595 ± 0.0061 | 0.2448 ± 0.0031 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": false, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +2-hop | 0.3690 ± 0.0038 | 0.2526 ± 0.0045 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +IDF weighting | 0.3690 ± 0.0038 | 0.2584 ± 0.0049 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": true}` |

### 基于知识图谱嵌入的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 原始三关系 | 0.3905 ± 0.0089 | 0.2291 ± 0.0053 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": false, "use_fusion_ranking": false}` |
| 扩图三元组 | 0.4809 ± 0.0095 | 0.2711 ± 0.0101 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": true, "use_fusion_ranking": false}` |
| 扩图三元组+融合排序 | 0.5393 ± 0.0122 | 0.3192 ± 0.0090 | `{"centroid_weight": 0.4, "entity_overlap_weight": 0.4, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}` |
