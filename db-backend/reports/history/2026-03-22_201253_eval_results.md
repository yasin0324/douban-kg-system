# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 99_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 验证集用户数: **42**
- 测试集用户数: **168**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.3381 ± 0.0152 | 0.2828 ± 0.0081 |
| 基于内容的推荐 | 0.1988 ± 0.0089 | 0.1277 ± 0.0050 |
| 基于物品的协同过滤 | 0.7595 ± 0.0163 | 0.5834 ± 0.0110 |
| 基于知识图谱路径的推荐 | 0.2595 ± 0.0097 | 0.2219 ± 0.0038 |
| 基于知识图谱嵌入的推荐 | 0.3988 ± 0.0113 | 0.2900 ± 0.0093 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.4393 ± 0.0095 | 0.3156 ± 0.0064 |
| 基于内容的推荐 | 0.3512 ± 0.0119 | 0.1767 ± 0.0067 |
| 基于物品的协同过滤 | 0.8083 ± 0.0069 | 0.5992 ± 0.0071 |
| 基于知识图谱路径的推荐 | 0.3702 ± 0.0070 | 0.2573 ± 0.0022 |
| 基于知识图谱嵌入的推荐 | 0.5333 ± 0.0208 | 0.3330 ± 0.0100 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.4988 ± 0.0045 | 0.3309 ± 0.0056 |
| 基于内容的推荐 | 0.5536 ± 0.0084 | 0.2278 ± 0.0034 |
| 基于物品的协同过滤 | 0.8583 ± 0.0045 | 0.6118 ± 0.0077 |
| 基于知识图谱路径的推荐 | 0.4476 ± 0.0045 | 0.2768 ± 0.0015 |
| 基于知识图谱嵌入的推荐 | 0.7369 ± 0.0148 | 0.3844 ± 0.0080 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |
|------|-------------|--------------|--------------|
| CFKG 主链路推荐 | 0.0234 ± 0.0001 | 0.8935 ± 0.0020 | 28.5298 |
| 基于内容的推荐 | 0.0238 ± 0.0000 | 0.8249 ± 0.0027 | 0.2308 |
| 基于物品的协同过滤 | 0.0233 ± 0.0001 | 0.9046 ± 0.0013 | 0.4992 |
| 基于知识图谱路径的推荐 | 0.0235 ± 0.0001 | 0.8984 ± 0.0017 | 3.4764 |
| 基于知识图谱嵌入的推荐 | 0.0239 ± 0.0001 | 0.8370 ± 0.0023 | 6.5293 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"item_cf_recall": 300, "item_cf_weight": 0.6, "kg_embed_weight": 0.25, "kg_path_weight": 0.15}`
- **基于内容的推荐 (content)**: `{}`
- **基于物品的协同过滤 (item_cf)**: `{}`
- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_weight": 0.2, "use_degree_penalty": true}`
- **基于知识图谱嵌入的推荐 (kg_embed)**: `{"centroid_weight": 0.2, "entity_overlap_weight": 0.6, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 1-hop | 0.3595 ± 0.0072 | 0.2448 ± 0.0045 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": false, "genre_weight": 0.2, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +2-hop | 0.3702 ± 0.0070 | 0.2524 ± 0.0016 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +IDF weighting | 0.3702 ± 0.0070 | 0.2573 ± 0.0022 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_weight": 0.2, "use_degree_penalty": true}` |

### 基于知识图谱嵌入的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 原始三关系 | 0.3869 ± 0.0192 | 0.2243 ± 0.0084 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": false, "use_fusion_ranking": false}` |
| 扩图三元组 | 0.4845 ± 0.0071 | 0.2720 ± 0.0144 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": true, "use_fusion_ranking": false}` |
| 扩图三元组+融合排序 | 0.5250 ± 0.0069 | 0.3142 ± 0.0076 | `{"centroid_weight": 0.4, "entity_overlap_weight": 0.4, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}` |
