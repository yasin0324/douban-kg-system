# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 499_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['kg_embed']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 全流程总耗时: **41505.57s**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| 基于知识图谱嵌入的推荐 | 0.6025 ± 0.0148 | 0.4352 ± 0.0104 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| 基于知识图谱嵌入的推荐 | 0.7405 ± 0.0075 | 0.4800 ± 0.0071 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| 基于知识图谱嵌入的推荐 | 0.8430 ± 0.0043 | 0.5063 ± 0.0068 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Main Test Time (s) | Total Elapsed (s) |
|------|-------------|--------------|-------------------------|-------------------|
| 基于知识图谱嵌入的推荐 | 0.0342 ± 0.0002 | 0.8825 ± 0.0003 | 8.6879 | 35119.83 |

## Best Params

- **基于知识图谱嵌入的推荐 (kg_embed)**: `{"centroid_weight": 0.1, "entity_overlap_weight": 0.2, "max_seed_weight": 0.1, "use_expanded_relations": true, "use_fusion_ranking": true, "use_user_rating_relations": true, "user_relation_weight": 0.6}`

## Ablations

### 基于知识图谱嵌入的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 结构嵌入 | 0.2760 ± 0.0089 | 0.1726 ± 0.0072 | `{"centroid_weight": 0.4, "entity_overlap_weight": 0.4, "max_seed_weight": 0.2, "use_expanded_relations": true, "use_fusion_ranking": true, "use_user_rating_relations": false, "user_relation_weight": 0.0}` |
| 结构嵌入+用户三元组 | 0.7320 ± 0.0083 | 0.4653 ± 0.0066 | `{"centroid_weight": 0.0, "entity_overlap_weight": 0.0, "max_seed_weight": 0.0, "use_expanded_relations": true, "use_fusion_ranking": true, "use_user_rating_relations": true, "user_relation_weight": 1.0}` |
| 全量融合 | 0.7405 ± 0.0075 | 0.4800 ± 0.0071 | `{"centroid_weight": 0.1, "entity_overlap_weight": 0.2, "max_seed_weight": 0.1, "use_expanded_relations": true, "use_fusion_ranking": true, "use_user_rating_relations": true, "user_relation_weight": 0.6}` |
