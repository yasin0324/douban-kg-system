# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 99_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['kg_path']**
- 验证集用户数: **42**
- 测试集用户数: **168**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| 基于知识图谱路径的推荐 | 0.2595 ± 0.0117 | 0.2240 ± 0.0071 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| 基于知识图谱路径的推荐 | 0.3678 ± 0.0070 | 0.2588 ± 0.0051 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| 基于知识图谱路径的推荐 | 0.4500 ± 0.0029 | 0.2796 ± 0.0042 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Time (s) |
|------|-------------|--------------|--------------|
| 基于知识图谱路径的推荐 | 0.0230 ± 0.0000 | 0.8984 ± 0.0020 | 3.0617 |

## Best Params

- **基于知识图谱路径的推荐 (kg_path)**: `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": true}`

## Ablations

### 基于知识图谱路径的推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 1-hop | 0.3643 ± 0.0044 | 0.2461 ± 0.0058 | `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": false, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +2-hop | 0.3678 ± 0.0070 | 0.2517 ± 0.0080 | `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": false}` |
| +IDF weighting | 0.3678 ± 0.0070 | 0.2588 ± 0.0051 | `{"actor_order_limit": 5, "actor_weight": 0.8, "director_weight": 1.0, "enable_two_hop": true, "genre_weight": 0.6, "two_hop_bridge_actor_limit": 3, "two_hop_seed_actor_limit": 3, "two_hop_weight": 0.2, "use_degree_penalty": true}` |
