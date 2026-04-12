# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 499_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['kg_path']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 全流程总耗时: **138600.70s**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| 基于知识图谱路径的推荐 | 0.4950 ± 0.0016 | 0.3886 ± 0.0036 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| 基于知识图谱路径的推荐 | 0.5200 ± 0.0016 | 0.3970 ± 0.0031 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| 基于知识图谱路径的推荐 | 0.5270 ± 0.0019 | 0.3988 ± 0.0034 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Main Test Time (s) | Total Elapsed (s) |
|------|-------------|--------------|-------------------------|-------------------|
| 基于知识图谱路径的推荐 | 0.0324 ± 0.0001 | 0.9084 ± 0.0007 | 56.4411 | 138573.91 |

## Best Params

- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_weight": 0.2, "content_type_weight": 0.05, "director_weight": 0.2, "enable_two_hop": true, "genre_weight": 0.2, "language_weight": 0.1, "region_weight": 0.1, "shared_audience_weight": 0.6, "two_hop_weight": 0.1, "use_degree_penalty": true, "use_expanded_relations": true, "use_user_activity_penalty": true, "use_user_behavior_paths": true, "year_bucket_weight": 0.05}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 结构路径 | 0.2165 ± 0.0012 | 0.1495 ± 0.0019 | `{"actor_weight": 0.2, "content_type_weight": 0.05, "director_weight": 0.2, "enable_two_hop": true, "genre_weight": 0.2, "language_weight": 0.1, "region_weight": 0.1, "shared_audience_weight": 0.6, "two_hop_weight": 0.1, "use_degree_penalty": false, "use_expanded_relations": false, "use_user_activity_penalty": false, "use_user_behavior_paths": false, "year_bucket_weight": 0.05}` |
| 结构路径+协同用户路径 | 0.5185 ± 0.0012 | 0.3954 ± 0.0034 | `{"actor_weight": 0.2, "content_type_weight": 0.05, "director_weight": 0.2, "enable_two_hop": true, "genre_weight": 0.2, "language_weight": 0.1, "region_weight": 0.1, "shared_audience_weight": 0.6, "two_hop_weight": 0.1, "use_degree_penalty": false, "use_expanded_relations": false, "use_user_activity_penalty": false, "use_user_behavior_paths": true, "year_bucket_weight": 0.05}` |
| 全量融合 | 0.5200 ± 0.0016 | 0.3970 ± 0.0031 | `{"actor_weight": 0.2, "content_type_weight": 0.05, "director_weight": 0.2, "enable_two_hop": true, "genre_weight": 0.2, "language_weight": 0.1, "region_weight": 0.1, "shared_audience_weight": 0.6, "two_hop_weight": 0.1, "use_degree_penalty": true, "use_expanded_relations": true, "use_user_activity_penalty": true, "use_user_behavior_paths": true, "year_bucket_weight": 0.05}` |
