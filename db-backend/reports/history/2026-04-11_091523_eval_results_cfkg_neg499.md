# 推荐算法离线评估报告

- 协议版本: **v2**
- 评估方法: **validation_and_test_sampled_leave_one_out (1_positive + 499_negatives)**
- 用户来源: **公开豆瓣用户（douban_public_*)**
- 负采样 seeds: **[42, 52, 62, 72, 82]**
- 选定算法: **['cfkg']**
- 验证集用户数: **100**
- 测试集用户数: **400**
- 全流程总耗时: **41763.07s**
- 指标说明: **当前评估采用 sampled leave-one-out，每个用户仅保留 1 个测试正样本；因此 Recall@K 与 Hit Rate@K 数值恒等，报告主表默认仅展示更常见的 HR@K 与 NDCG@K。**

## K = 5

| 算法 | HR@5 | NDCG@5 |
|------|------|------|
| CFKG 主链路推荐 | 0.6480 ± 0.0090 | 0.4757 ± 0.0110 |

## K = 10

| 算法 | HR@10 | NDCG@10 |
|------|------|------|
| CFKG 主链路推荐 | 0.7940 ± 0.0025 | 0.5234 ± 0.0098 |

## K = 20

| 算法 | HR@20 | NDCG@20 |
|------|------|------|
| CFKG 主链路推荐 | 0.8745 ± 0.0051 | 0.5440 ± 0.0099 |

## Coverage / Diversity / Time

| 算法 | Coverage@20 | Diversity@10 | Avg Main Test Time (s) | Total Elapsed (s) |
|------|-------------|--------------|-------------------------|-------------------|
| CFKG 主链路推荐 | 0.0318 ± 0.0002 | 0.8977 ± 0.0008 | 11.1655 | 41735.70 |

## Best Params

- **CFKG 主链路推荐 (cfkg)**: `{"agreement_bonus": 0.05, "content_fallback_weight": 0.05, "item_cf_recall": 400, "item_cf_weight": 0.3, "kg_embed_recall": 300, "kg_embed_weight": 0.7, "kg_path_rerank_topn": 100, "kg_path_rerank_weight": 0.05}`

## Ablations

### CFKG 主链路推荐

| 消融 | HR@10 | NDCG@10 | Params |
|------|-------|---------|--------|
| 双分支主排序 | 0.7940 ± 0.0025 | 0.5251 ± 0.0074 | `{"agreement_bonus": 0.05, "content_fallback_weight": 0.05, "item_cf_recall": 400, "item_cf_weight": 0.3, "kg_embed_recall": 300, "kg_embed_weight": 0.7, "kg_path_rerank_topn": 100, "kg_path_rerank_weight": 0.0}` |
| +kg_path 小范围重排 | 0.7940 ± 0.0025 | 0.5234 ± 0.0098 | `{"agreement_bonus": 0.05, "content_fallback_weight": 0.05, "item_cf_recall": 400, "item_cf_weight": 0.3, "kg_embed_recall": 300, "kg_embed_weight": 0.7, "kg_path_rerank_topn": 100, "kg_path_rerank_weight": 0.05}` |
| 全量主链路 | 0.7940 ± 0.0025 | 0.5234 ± 0.0098 | `{"agreement_bonus": 0.05, "content_fallback_weight": 0.05, "item_cf_recall": 400, "item_cf_weight": 0.3, "kg_embed_recall": 300, "kg_embed_weight": 0.7, "kg_path_rerank_topn": 100, "kg_path_rerank_weight": 0.05}` |
