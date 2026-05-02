# 基于知识图谱的电影推荐系统

本仓库是一个端到端电影推荐系统，当前主线为：

`Playwright 数据采集 -> MySQL 原始数据与用户行为 -> 数据清洗 -> Neo4j 知识图谱 -> FastAPI 后端 -> Vue3 前端 -> 推荐评测与解释`

## 当前范围

- 数据采集：`db-spiders/` 使用 Playwright 采集电影与影人数据，支持任务状态、失败标记和断点恢复。
- 数据处理：`data_processing/` 负责数据质量分析、清洗和 MySQL 到 Neo4j 的 ETL。
- 后端服务：`db-backend/` 提供电影、影人、图谱、统计、认证、用户行为、推荐和推荐解释接口。
- 前端应用：`db-frontend/` 提供搜索、电影库、详情、图谱探索、统计看板、登录注册、个人中心和推荐页。
- 推荐系统：实现 `content`、`item_cf`、`kg_path`、`kg_embed`、`cfkg` 五类推荐算法，并提供离线评测报告与推荐解释接口。

## 论文证据口径

正式写作优先引用以下材料：

- 数据规模与质量：[data_processing/reports/data_quality_report.md](data_processing/reports/data_quality_report.md)
- 知识图谱 ETL：[data_processing/etl_to_neo4j.py](data_processing/etl_to_neo4j.py)
- 后端入口与路由：[db-backend/app/main.py](db-backend/app/main.py)
- 前端路由：[db-frontend/src/router/index.js](db-frontend/src/router/index.js)
- 正式推荐评测：[db-backend/reports/eval_results_neg499.md](db-backend/reports/eval_results_neg499.md)
- 在线验收：[db-backend/reports/online_acceptance_kg_2026-04-12_v2.md](db-backend/reports/online_acceptance_kg_2026-04-12_v2.md)

不把旧规划中的智能问答、HanLP 实体抽取、生产级 QPS/P95 压测、已移除推荐接口等内容作为正文依据。

## 快速入口

```bash
# 后端
cd db-backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd db-frontend
npm install
npm run dev
```
