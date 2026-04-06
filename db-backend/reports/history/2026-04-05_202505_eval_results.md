# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 99_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['cfkg', 'content', 'item_cf', 'kg_path', 'kg_embed']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.4095 ± 0.0037 | 0.3721 ± 0.0044 |
| 基于内容的推荐 | 0.2220 ± 0.0172 | 0.1376 ± 0.0078 |
| 基于物品的协同过滤 | 0.8185 ± 0.0064 | 0.6601 ± 0.0094 |
| 基于知识图谱路径的推荐 | 0.2525 ± 0.0042 | 0.2097 ± 0.0022 |
| 基于知识图谱嵌入的推荐 | 0.4210 ± 0.0083 | 0.3172 ± 0.0068 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.4745 ± 0.0037 | 0.3933 ± 0.0039 |
| 基于内容的推荐 | 0.3540 ± 0.0121 | 0.1804 ± 0.0072 |
| 基于物品的协同过滤 | 0.8610 ± 0.0034 | 0.6743 ± 0.0100 |
| 基于知识图谱路径的推荐 | 0.3370 ± 0.0066 | 0.2371 ± 0.0038 |
| 基于知识图谱嵌入的推荐 | 0.5600 ± 0.0118 | 0.3621 ± 0.0057 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.5235 ± 0.0046 | 0.4058 ± 0.0029 |
| 基于内容的推荐 | 0.5455 ± 0.0064 | 0.2286 ± 0.0048 |
| 基于物品的协同过滤 | 0.8895 ± 0.0019 | 0.6815 ± 0.0098 |
| 基于知识图谱路径的推荐 | 0.4040 ± 0.0054 | 0.2542 ± 0.0023 |
| 基于知识图谱嵌入的推荐 | 0.7305 ± 0.0056 | 0.4050 ± 0.0060 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |
|------|-------------|--------------|--------------|
| CFKG 主链路推荐 | 0.0378 ± 0.0001 | 0.8893 ± 0.0013 | 12.6521 |
| 基于内容的推荐 | 0.0393 ± 0.0000 | 0.8210 ± 0.0008 | 0.2798 |
| 基于物品的协同过滤 | 0.0376 ± 0.0001 | 0.9063 ± 0.0011 | 1.0131 |
| 基于知识图谱路径的推荐 | 0.0381 ± 0.0001 | 0.8931 ± 0.0010 | 4.6056 |
| 基于知识图谱嵌入的推荐 | 0.0396 ± 0.0001 | 0.8344 ± 0.0016 | 8.1203 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"item_cf_recall": 300, "item_cf_weight": 0.6, "kg_embed_weight": 0.3, "kg_path_weight": 0.1}`
- **基于内容的推荐 (content)**: `{}`
- **基于物品的协同过滤 (item_cf)**: `{}`
- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_order_limit": 3, "actor_weight": 0.8, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.4, "use_degree_penalty": true}`
- **基于知识图谱嵌入的推荐 (kg_embed)**: `{"centroid_weight": 0.2, "entity_overlap_weight": 0.6, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 1-hop | 0.3245 ± 0.0048 | 0.2221 ± 0.0049 | `{"actor_order_limit": 3, "actor_weight": 0.8, "director_weight": 0.8, "enable_two_hop": false, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.4, "use_degree_penalty": false}` |
| +2-hop | 0.3370 ± 0.0066 | 0.2299 ± 0.0040 | `{"actor_order_limit": 3, "actor_weight": 0.8, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.4, "use_degree_penalty": false}` |
| +IDF weighting | 0.3370 ± 0.0066 | 0.2371 ± 0.0038 | `{"actor_order_limit": 3, "actor_weight": 0.8, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.4, "use_degree_penalty": true}` |

### 基于知识图谱嵌入的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 原始三关系 | 0.4510 ± 0.0075 | 0.2656 ± 0.0091 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": false, "use_fusion_ranking": false}` |
| 扩图三元组 | 0.4620 ± 0.0087 | 0.2762 ± 0.0050 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": true, "use_fusion_ranking": false}` |
| 扩图三元组+融合排序 | 0.5400 ± 0.0069 | 0.3376 ± 0.0044 | `{"centroid_weight": 0.4, "entity_overlap_weight": 0.4, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}` |
