# 推荐实验结果快照

用于保留毕设优化过程中的关键评估结果，避免后续重复运行覆盖默认报告文件。

## 时间线

### 2026-03-11 初版采样评估

- 主报告 JSON: `2026-03-11_sampled-loo_initial.json`
- 主报告 Markdown: `2026-03-11_sampled-loo_initial.md`
- 说明:
  - 使用旧版 sampled leave-one-out 评估流程
  - 该阶段尚未引入验证集调参 + 5-seed 聚合报告
  - 对应你最早那次 `kg_path` 很高、`kg_embed` 很低的结果

### 2026-03-12 优化后验证集 + 5-seed 评估

- 主报告 JSON: `2026-03-12_validation-5seed_after-optimization.json`
- 主报告 Markdown: `2026-03-12_validation-5seed_after-optimization.md`
- Legacy JSON: `2026-03-12_validation-5seed_after-optimization_legacy.json`
- Legacy Markdown: `2026-03-12_validation-5seed_after-optimization_legacy.md`
- 说明:
  - 使用验证集调参 + 测试集 5-seed sampled leave-one-out
  - 包含 coverage、diversity、avg_time 和消融实验
  - 对应当前优化后的正式对比口径
