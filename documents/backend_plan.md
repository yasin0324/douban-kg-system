# 后端实现说明

**状态**: 当前实现说明，取代旧版后端规划书
**修订日期**: 2026-05-01

旧版文档中与当前实现不一致的推荐状态、早期算法主链路和未验证性能目标已删除。正式论文以后端代码、测试和报告为准。

## 1. 后端定位

后端位于 `db-backend/`，使用 FastAPI 连接 MySQL 与 Neo4j，为前端提供数据查询、图谱探索、统计分析、用户认证、用户行为、推荐算法和管理接口。

启动入口为 `db-backend/app/main.py`，生命周期中初始化 MySQL 连接池、Neo4j Driver，并预热推荐图谱缓存与 KG-Embed 工件。

## 2. API 模块

当前路由覆盖以下模块：

| 模块 | 文件 | 主要能力 |
|---|---|---|
| 系统 | `app/main.py` | `/health` 健康检查 |
| 认证 | `app/routers/auth.py` | 注册、登录、登出、刷新 Token、当前用户 |
| 用户行为 | `app/routers/users.py` | 喜欢、想看、评分、画像分析、画像图谱 |
| 管理员认证 | `app/routers/admin_auth.py` | 管理员登录与登出 |
| 管理员用户 | `app/routers/admin_users.py` | 用户列表、详情、封禁、解封、强制下线 |
| 电影 | `app/routers/movies.py` | 搜索、类型、高分榜、筛选、详情、演职员 |
| 影人 | `app/routers/persons.py` | 搜索、详情、作品、合作者 |
| 图谱 | `app/routers/graph.py` | 电影图、影人图、全局概览、最短路径、共同电影 |
| 统计 | `app/routers/stats.py` | 类型、年代、评分、合作网络、趋势和散点统计 |
| 推荐 | `app/routers/recommend.py` | 个性化推荐、解释、算法列表、离线评估报告 |
| 代理 | `app/routers/proxy.py` | 图片代理 |

## 3. 推荐算法

当前推荐算法注册在 `db-backend/app/algorithms/__init__.py`：

| 算法标识 | 实现文件 | 说明 |
|---|---|---|
| `content` | `content_based.py` | 基于内容特征的推荐 |
| `item_cf` | `item_cf.py` | 基于物品的协同过滤 |
| `kg_path` | `kg_path.py` | 基于知识图谱路径的推荐 |
| `kg_embed` | `kg_embed.py` | 基于知识图谱嵌入的推荐 |
| `cfkg` | `cfkg.py` | 融合 `kg_embed` 与 `item_cf` 的主链路推荐 |

正式评测口径使用 `db-backend/reports/eval_results_neg499.md`。该报告采用 `1 positive + 499 negatives`，验证集 `100` 用户，测试集 `400` 用户；其中 CFKG 在 `K=10` 下达到 `HR@10=0.7910`、`NDCG@10=0.5240`。

## 4. 测试与验收

- 单元与回归测试位于 `db-backend/tests/`。
- 在线链路验收报告为 `db-backend/reports/online_acceptance_kg_2026-04-12_v2.md`，记录 `46/46` 场景通过。
- 论文第 5 章可写功能测试、回归测试、在线链路验收和离线推荐评测；不得写未执行的压力测试、生产 QPS、P95 或并发承载结果。
