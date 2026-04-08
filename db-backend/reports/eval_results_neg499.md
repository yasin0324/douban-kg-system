# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 499_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['cfkg', 'content', 'item_cf', 'kg_path', 'kg_embed']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.3565 ± 0.0012 | 0.3210 ± 0.0037 |
| 基于内容的推荐 | 0.0505 ± 0.0089 | 0.0316 ± 0.0047 |
| 基于物品的协同过滤 | 0.5385 ± 0.0075 | 0.4022 ± 0.0052 |
| 基于知识图谱路径的推荐 | 0.2010 ± 0.0046 | 0.1628 ± 0.0045 |
| 基于知识图谱嵌入的推荐 | 0.2250 ± 0.0079 | 0.1689 ± 0.0072 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.3600 ± 0.0000 | 0.3221 ± 0.0033 |
| 基于内容的推荐 | 0.1080 ± 0.0029 | 0.0499 ± 0.0019 |
| 基于物品的协同过滤 | 0.6935 ± 0.0075 | 0.4522 ± 0.0036 |
| 基于知识图谱路径的推荐 | 0.2170 ± 0.0010 | 0.1682 ± 0.0035 |
| 基于知识图谱嵌入的推荐 | 0.3050 ± 0.0119 | 0.1946 ± 0.0082 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.3985 ± 0.0030 | 0.3315 ± 0.0034 |
| 基于内容的推荐 | 0.1910 ± 0.0030 | 0.0708 ± 0.0027 |
| 基于物品的协同过滤 | 0.8225 ± 0.0057 | 0.4852 ± 0.0050 |
| 基于知识图谱路径的推荐 | 0.2380 ± 0.0029 | 0.1732 ± 0.0040 |
| 基于知识图谱嵌入的推荐 | 0.3985 ± 0.0041 | 0.2180 ± 0.0059 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |
|------|-------------|--------------|--------------|
| CFKG 主链路推荐 | 0.0283 ± 0.0001 | 0.8981 ± 0.0010 | 12.5865 |
| 基于内容的推荐 | 0.0365 ± 0.0002 | 0.7563 ± 0.0013 | 0.2664 |
| 基于物品的协同过滤 | 0.0285 ± 0.0002 | 0.9086 ± 0.0010 | 1.0031 |
| 基于知识图谱路径的推荐 | 0.0315 ± 0.0001 | 0.9060 ± 0.0006 | 4.2278 |
| 基于知识图谱嵌入的推荐 | 0.0383 ± 0.0002 | 0.7945 ± 0.0021 | 7.7175 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"item_cf_recall": 300, "item_cf_weight": 0.5, "kg_embed_weight": 0.4, "kg_path_weight": 0.1}`
- **基于内容的推荐 (content)**: `{}`
- **基于物品的协同过滤 (item_cf)**: `{}`
- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": true}`
- **基于知识图谱嵌入的推荐 (kg_embed)**: `{"centroid_weight": 0.2, "entity_overlap_weight": 0.6, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 1-hop | 0.1925 ± 0.0000 | 0.1540 ± 0.0041 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": false, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +2-hop | 0.2165 ± 0.0012 | 0.1634 ± 0.0039 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +IDF weighting | 0.2170 ± 0.0010 | 0.1682 ± 0.0035 | `{"actor_order_limit": 5, "actor_weight": 0.6, "director_weight": 0.8, "enable_two_hop": true, "genre_weight": 0.2, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": true}` |

### 基于知识图谱嵌入的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 原始三关系 | 0.2045 ± 0.0029 | 0.1103 ± 0.0054 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": false, "use_fusion_ranking": false}` |
| 扩图三元组 | 0.2265 ± 0.0073 | 0.1195 ± 0.0069 | `{"centroid_weight": 1.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": true, "use_fusion_ranking": false}` |
| 扩图三元组+融合排序 | 0.2760 ± 0.0089 | 0.1726 ± 0.0072 | `{"centroid_weight": 0.4, "entity_overlap_weight": 0.4, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true}` |
