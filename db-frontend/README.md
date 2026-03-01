# db-frontend — 豆瓣电影知识图谱前端

基于 **Vue 3 + Vite** 的前端应用，提供电影浏览、影人查询、知识图谱可视化等功能。

## 技术栈

- **Vue 3** (Composition API + `<script setup>`)
- **Vite 5** — 构建工具
- **Vue Router 4** — 路由管理（懒加载 + 登录守卫）
- **Pinia 2** — 状态管理（用户认证）
- **Element Plus** — UI 组件库（暗色主题）
- **ECharts 5** — 知识图谱可视化
- **Axios** — HTTP 客户端
- **SCSS** — 样式预处理

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 配置环境变量

编辑 `.env`：

```env
VITE_API_BASE=http://localhost:8000
```

### 3. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173 查看应用。

> **注意**：需要先启动后端服务（端口 8000），Vite 开发代理会将 `/api` 请求转发到后端。

### 4. 生产构建

```bash
npm run build
```

## 页面功能

| 页面      | 路由                 | 状态                                |
| --------- | -------------------- | ----------------------------------- |
| 首页      | `/`                  | ✅ 统计概览 + 类型标签云 + 高分电影 |
| 搜索      | `/search?q=xxx`      | ✅ 电影/影人双 Tab + 分页           |
| 电影库    | `/movies/filter`     | ✅ 类型/年代/评分筛选               |
| 电影详情  | `/movies/:mid`       | ✅ 海报 + 评分 + 演职 + 偏好操作    |
| 影人详情  | `/persons/:pid`      | ✅ 信息 + 作品列表 + 合作者         |
| 电影图谱  | `/graph/movie/:mid`  | 🚧 Phase 3                          |
| 影人图谱  | `/graph/person/:pid` | 🚧 Phase 3                          |
| 最短路径  | `/graph/path`        | 🚧 Phase 3                          |
| 统计看板  | `/stats`             | 🚧 Phase 4                          |
| 登录/注册 | `/login` `/register` | 🚧 Phase 4                          |
| 个人中心  | `/profile`           | 🚧 Phase 4                          |

## 项目结构

```
src/
├── api/                # API 封装（Axios 实例 + 6 个模块）
├── assets/styles/      # 全局 SCSS 暗色主题
├── components/         # 通用组件
│   ├── layout/         #   AppHeader / AppFooter
│   ├── movie/          #   MovieCard / MovieList
│   └── person/         #   PersonCard
├── router/             # 路由配置
├── stores/             # Pinia 状态管理
├── utils/              # 工具函数（图片代理等）
└── views/              # 页面视图（11 个）
```
