# 推荐与验收报告说明

正式论文以当前目录下的 `eval_results_neg499.md` 和 `online_acceptance_kg_2026-04-12_v2.md` 为主证据。

## 主报告

- `eval_results_neg499.md`: 正式推荐算法对比报告，协议为 `1 positive + 499 negatives`，验证集 `100` 用户，测试集 `400` 用户。
- `online_acceptance_kg_2026-04-12_v2.md`: 在线链路验收报告，`46/46` 场景通过。

## 历史报告

- `*_legacy.*` 和 `history/` 中的报告用于记录实验演进，不作为论文主结论。
- 旧版 `1 positive + 99 negatives` 结果可作为算法调优过程说明，但不能替代正式 `neg499` 口径。
- 如果正文需要写“耗时、覆盖率、多样性、消融实验”，以 `eval_results_neg499.md` 的表格为准。
