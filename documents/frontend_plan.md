# 前端实现说明

**状态**: 当前实现说明，取代旧版前端规划书
**修订日期**: 2026-05-01

旧版文档中与当前推荐链路不一致的前后端状态说明已删除。当前前端已经包含推荐页、推荐解释抽屉和首页推荐区，后端 `/api/recommend/*` 也有实际算法支持。

## 1. 技术栈

- Vue 3 + Vite
- Vue Router 4
- Pinia
- Element Plus
- Axios
- ECharts
- SCSS

## 2. 路由与页面

路由定义见 `db-frontend/src/router/index.js`。

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | `HomeView.vue` | 首页、统计概览、高分电影、推荐入口 |
| `/search` | `SearchView.vue` | 电影与影人搜索 |
| `/movies/filter` | `MovieFilterView.vue` | 电影库筛选与排序 |
| `/recommend` | `RecommendView.vue` | 推荐中心、算法切换、评测报告展示 |
| `/movies/:mid` | `MovieDetailView.vue` | 电影详情、演职员、用户偏好操作 |
| `/persons/:pid` | `PersonDetailView.vue` | 影人详情、作品与合作者 |
| `/graph/movie/:mid` | `GraphView.vue` | 电影关联图谱 |
| `/graph/person/:pid` | `GraphView.vue` | 影人关联图谱 |
| `/graph/explore` | `KnowledgeGraphExploreView.vue` | 全局图谱探索、路径查询、共同电影 |
| `/stats` | `StatsView.vue` | 统计看板 |
| `/login` | `LoginView.vue` | 登录 |
| `/register` | `RegisterView.vue` | 注册 |
| `/profile` | `ProfileView.vue` | 个人中心、偏好/评分、画像分析、观影图谱 |

## 3. 推荐相关前端证据

- 推荐 API 封装：`db-frontend/src/api/recommend.js`
- 推荐状态组合函数：`db-frontend/src/composables/useRecommendations.js`
- 推荐中心：`db-frontend/src/views/RecommendView.vue`
- 首页推荐区：`db-frontend/src/views/HomeView.vue`
- 推荐解释抽屉：`db-frontend/src/components/recommend/RecommendationDetailDrawer.vue`

论文截图计划中可以使用首页、搜索/筛选、电影详情、图谱探索、统计看板、推荐页、推荐解释抽屉和个人中心。
