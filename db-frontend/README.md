# db-frontend

基于 Vue 3 + Vite 的电影知识图谱推荐系统前端，提供电影浏览、影人查询、知识图谱可视化、统计看板、用户中心和个性化推荐功能。

## 技术栈

- Vue 3
- Vite 5
- Vue Router 4
- Pinia 2
- Element Plus
- ECharts 5
- Axios
- SCSS

## 快速开始

```bash
npm install
npm run dev
```

开发环境默认访问 http://localhost:5173。需要先启动后端服务，Vite 代理会将 `/api` 请求转发到后端。

生产构建：

```bash
npm run build
```

## 页面功能

路由来源：`src/router/index.js`。

| 页面 | 路由 | 状态 |
|---|---|---|
| 首页 | `/` | 已实现：统计概览、高分电影、推荐入口 |
| 搜索 | `/search` | 已实现：电影/影人搜索 |
| 电影库 | `/movies/filter` | 已实现：类型、年代、评分、内容形式和排序筛选 |
| 推荐中心 | `/recommend` | 已实现：算法切换、推荐列表、评测报告、解释入口 |
| 电影详情 | `/movies/:mid` | 已实现：海报、评分、演职员、喜欢/想看/评分 |
| 影人详情 | `/persons/:pid` | 已实现：影人信息、作品列表、合作者 |
| 电影图谱 | `/graph/movie/:mid` | 已实现：电影关联图谱 |
| 影人图谱 | `/graph/person/:pid` | 已实现：影人关联图谱 |
| 图谱探索 | `/graph/explore` | 已实现：全局探索、路径查询、共同电影 |
| 统计看板 | `/stats` | 已实现：类型、年代、评分、趋势和散点图 |
| 登录 | `/login` | 已实现 |
| 注册 | `/register` | 已实现 |
| 个人中心 | `/profile` | 已实现：偏好/评分、画像分析、观影图谱 |

## 项目结构

```text
src/
├── api/                # API 封装
├── assets/styles/      # 全局 SCSS
├── components/         # 布局、电影、影人、图谱和推荐组件
├── composables/        # 推荐与交互状态逻辑
├── router/             # 路由配置
├── stores/             # Pinia 状态管理
├── utils/              # 工具函数
└── views/              # 页面视图
```
