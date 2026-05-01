# 开发计划材料归档说明

**状态**: 已归档，仅保留当前论文取材边界
**修订日期**: 2026-05-01

旧版 `development_plan.md` 是早期八周开发设想，包含 Scrapy、HanLP、PPR、GCN、LightGCN、压力测试、生产级 P95 等未落到当前仓库实现或未完成验证的内容。为避免后续论文正文误用，旧内容已从活跃文档中删除。

## 当前可写开发阶段

1. 数据采集阶段：基于 Playwright 的电影与影人采集，任务状态、失败标记、断点恢复和代理/直连模式。
2. 数据处理阶段：数据质量报告、清洗流水线、MySQL 到 Neo4j 的 ETL。
3. 图谱构建阶段：`Movie`、`Person`、`Genre`、`Region`、`Language`、`ContentType`、`YearBucket` 节点与 7 类关系。
4. 后端实现阶段：FastAPI 路由、服务层、MySQL/Neo4j 连接、认证与用户行为管理。
5. 前端实现阶段：Vue3 页面、路由、状态管理、ECharts 图谱与统计图。
6. 推荐与评测阶段：`content`、`item_cf`、`kg_path`、`kg_embed`、`cfkg` 推荐算法，`1 positive + 499 negatives` 离线评测和在线链路验收。

## 禁止继续作为正文依据的旧项

- Scrapy 作为当前核心爬虫框架。
- HanLP 命名实体识别或通用实体抽取模块。
- 智能问答、语义问答或影评舆情分析功能。
- GCN、LightGCN、PPR/Hybrid 作为当前正式算法实现。
- 未运行的 100 并发压力测试、QPS、P50/P95 或生产部署效果。
- LLM 生成模拟评分数据作为正式评测数据来源。

## 正式材料入口

- 当前系统说明：`README.md`
- 图谱 Schema：`documents/schema_design.md`
- 后端实现：`documents/backend_plan.md`
- 前端实现：`documents/frontend_plan.md`
- 爬虫实现：`documents/spiders_plan.md`
- 推荐评测：`db-backend/reports/eval_results_neg499.md`
- 在线验收：`db-backend/reports/online_acceptance_kg_2026-04-12_v2.md`
