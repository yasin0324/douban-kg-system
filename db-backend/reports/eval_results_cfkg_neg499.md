# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 499_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['cfkg']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 全流程总耗时: **30058.79s**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.6350 ± 0.0136 | 0.4689 ± 0.0099 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.7905 ± 0.0040 | 0.5195 ± 0.0055 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.8725 ± 0.0016 | 0.5405 ± 0.0062 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Main Test Time (s) | Total Elapsed (s) |
|------|-------------|--------------|-------------------------|-------------------|
| CFKG 主链路推荐 | 0.0320 ± 0.0002 | 0.8985 ± 0.0008 | 8.6149 | 30030.25 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"agreement_bonus": 0.0, "consensus_weight": 0.15, "content_fallback_weight": 0.0, "item_cf_weight": 0.35, "kg_embed_weight": 0.65, "kg_path_rerank_weight": 0.0}`

## Ablations

### CFKG 主链路推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| kg_embed 主导直排 | 0.7415 ± 0.0072 | 0.4801 ± 0.0061 | `{"agreement_bonus": 0.0, "consensus_weight": 0.0, "content_fallback_weight": 0.0, "item_cf_weight": 0.0, "kg_embed_weight": 1.0, "kg_path_rerank_weight": 0.0, "use_kg_path_explanations": false}` |
| +item_cf 线性辅助 | 0.7895 ± 0.0060 | 0.5232 ± 0.0050 | `{"agreement_bonus": 0.0, "consensus_weight": 0.0, "content_fallback_weight": 0.0, "item_cf_weight": 0.35, "kg_embed_weight": 0.65, "kg_path_rerank_weight": 0.0, "use_kg_path_explanations": false}` |
| +共识强化 | 0.7905 ± 0.0040 | 0.5195 ± 0.0055 | `{"agreement_bonus": 0.0, "consensus_weight": 0.15, "content_fallback_weight": 0.0, "item_cf_weight": 0.35, "kg_embed_weight": 0.65, "kg_path_rerank_weight": 0.0, "use_kg_path_explanations": false}` |
