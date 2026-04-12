# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 499_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['cfkg']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 全流程总耗时: **24689.86s**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.6440 ± 0.0110 | 0.4757 ± 0.0073 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.7910 ± 0.0051 | 0.5240 ± 0.0049 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.8705 ± 0.0033 | 0.5444 ± 0.0060 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Main Test Time (s) | Total Elapsed (s) |
|------|-------------|--------------|-------------------------|-------------------|
| CFKG 主链路推荐 | 0.0323 ± 0.0001 | 0.8957 ± 0.0007 | 8.7649 | 24662.74 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"agreement_bonus": 0.02, "content_fallback_weight": 0.0, "item_cf_weight": 0.3, "kg_embed_weight": 0.7, "kg_path_rerank_weight": 0.0}`

## Ablations

### CFKG 主链路推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| kg_embed 主导直排 | 0.7415 ± 0.0072 | 0.4801 ± 0.0061 | `{"agreement_bonus": 0.0, "content_fallback_weight": 0.0, "item_cf_weight": 0.0, "kg_embed_weight": 1.0, "kg_path_rerank_weight": 0.0, "use_kg_path_explanations": false}` |
| +item_cf 辅助打分 | 0.7910 ± 0.0051 | 0.5240 ± 0.0049 | `{"agreement_bonus": 0.02, "content_fallback_weight": 0.0, "item_cf_weight": 0.3, "kg_embed_weight": 0.7, "kg_path_rerank_weight": 0.0, "use_kg_path_explanations": false}` |
| +kg_path 解释 | 0.7910 ± 0.0051 | 0.5240 ± 0.0049 | `{"agreement_bonus": 0.02, "content_fallback_weight": 0.0, "item_cf_weight": 0.3, "kg_embed_weight": 0.7, "kg_path_rerank_weight": 0.0}` |
