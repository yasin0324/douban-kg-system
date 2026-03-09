# 前端开发规划书（MVP 阶段）

**版本**: v1.2 | **日期**: 2026-02-28 | **最后更新**: 2026-03-07

---

## 1. 项目概述

### 1.1 目标

基于已完成的后端 MVP，开发 Vue3 前端应用，实现豆瓣电影知识图谱的**可视化浏览、搜索、探索与个性化推荐**功能。

### 1.2 MVP 范围

- ✅ 实现：电影搜索与浏览、电影/影人详情、知识图谱可视化、统计看板、用户认证、用户偏好（喜欢/想看/评分）、推荐系统前端
- ❌ 推迟：管理后台（admin 界面暂不做前端，通过 API 管理）

### 1.3 技术栈

| 技术         | 版本 | 用途                                           |
| ------------ | ---- | ---------------------------------------------- |
| Vue 3        | 3.4+ | 前端框架（Composition API + `<script setup>`） |
| Vite         | 5.x  | 构建工具                                       |
| Vue Router   | 4.x  | 路由管理                                       |
| Pinia        | 2.x  | 状态管理（用户认证状态）                       |
| Axios        | 1.x  | HTTP 客户端                                    |
| Element Plus | 2.x  | UI 组件库                                      |
| ECharts      | 5.x  | 知识图谱可视化（graph 类型）                   |
| SCSS         | -    | 样式预处理                                     |

---

## 2. 页面结构与路由

### 2.1 路由表

```
/                         → 首页（高分电影 + 统计概览）
/search?q=xxx             → 搜索结果页
/movies/filter            → 电影筛选页（类型/年代/评分）
/movies/:mid              → 电影详情页
/recommend                → 推荐页（推荐中心）
/persons/:pid             → 影人详情页
/graph/movie/:mid         → 电影关联图谱
/graph/person/:pid        → 影人关联图谱
/graph/path               → 最短路径查询
/stats                    → 统计看板
/login                    → 登录页
/register                 → 注册页
/profile                  → 个人中心（偏好/评分列表）
```

### 2.2 布局结构

```
┌─────────────────────────────────────────────┐
│  顶部导航栏（Logo / 搜索框 / 用户头像）       │
├─────────────────────────────────────────────┤
│                                             │
│               主内容区域                     │
│         <router-view />                     │
│                                             │
├─────────────────────────────────────────────┤
│  底部（版权信息）                             │
└─────────────────────────────────────────────┘
```

---

## 3. 页面功能详细设计

### 3.1 首页 `/`

**对接 API**：

- `GET /api/movies/top?limit=12` — 高分电影
- `GET /api/stats/overview` — 总体统计
- `GET /api/movies/genres` — 类型列表（快速筛选入口）

**UI 组件**：

- 顶部 Hero 区域：搜索框 + 数据概览（电影数/影人数/关系数）
- 高分电影轮播/卡片网格（封面、标题、评分、年代）
- 类型标签云（点击跳转筛选页）

---

### 3.2 搜索结果页 `/search?q=xxx`

**对接 API**：

- `GET /api/movies/search?q={q}&page={page}&size=20` — 电影搜索
- `GET /api/persons/search?q={q}&page=1&size=10` — 影人搜索

**UI 组件**：

- Tab 切换：电影 / 影人
- 电影结果列表（封面缩略图、标题、评分、年代、类型标签）
- 影人结果列表（姓名、职业）
- 分页器

---

### 3.3 电影筛选页 `/movies/filter`

**对接 API**：

- `GET /api/movies/filter?genre=&year_from=&year_to=&rating_min=&page=&size=`
- `GET /api/movies/genres` — 类型列表

**UI 组件**：

- 左侧/顶部筛选栏：类型（checkbox/tag）、年代范围（slider）、最低评分（slider）
- 右侧电影卡片网格
- 分页器

---

### 3.4 电影详情页 `/movies/:mid`

**对接 API**：

- `GET /api/movies/{mid}` — 电影详情
- `GET /api/movies/{mid}/credits` — 演职人员
- `GET /api/users/preferences/check/{mid}` — 偏好状态（登录后）
- `GET /api/users/ratings/{mid}` — 用户评分（登录后）
- `POST /api/users/preferences` — 添加偏好
- `POST /api/users/ratings` — 添加评分

**UI 组件**：

- 电影海报 + 基本信息（标题、评分、年代、类型、地区）
- 剧情简介
- 导演/演员列表（头像卡片，点击跳转影人详情）
- 操作栏：❤️ 喜欢 / 📌 想看 / ⭐ 评分
- 「查看知识图谱」和「豆瓣链接」按钮

---

### 3.5 影人详情页 `/persons/:pid`

**对接 API**：

- `GET /api/persons/{pid}` — 影人详情
- `GET /api/persons/{pid}/movies` — 参演/执导电影
- `GET /api/persons/{pid}/collaborators?limit=10` — 合作者

**UI 组件**：

- 影人基本信息（姓名、性别、出生日期、出生地、职业）
- 个人简介
- 参演/执导电影列表（Tab 切换：全部/导演/演员、按年份倒排）
- 合作关系卡片
- 「查看知识图谱」按钮

---

### 3.6 知识图谱页 `/graph/movie/:mid` 和 `/graph/person/:pid`

**对接 API**：

- `GET /api/graph/movie/{mid}?depth=1&node_limit=150&edge_limit=300`
- `GET /api/graph/person/{pid}?depth=1&node_limit=150&edge_limit=300`

**UI 组件**：

- **ECharts graph** 力引导布局，节点按类型着色：
    - 🎬 Movie → 蓝色
    - 🧑 Person → 绿色
    - 🏷️ Genre → 橙色
- 节点大小按 rating/连接数缩放
- 控制面板：depth 切换（1/2 跳）、node_limit 滑块、图例开关
- 悬浮提示：节点名称 + 额外属性（评分、年代等）
- 点击节点 → 跳转到详情页或以该节点为中心重新展开
- 右侧信息面板：选中节点的详细信息
- 查询状态：加载动画 + 用时显示 + 截断提示

---

### 3.7 最短路径页 `/graph/path`

**对接 API**：

- `GET /api/graph/path?from={id}&to={id}&max_hops=6`
- `GET /api/graph/common?person1={pid}&person2={pid}&limit=50`

**UI 组件**：

- 双搜索框（起点/终点，支持搜索电影或影人进行选择）
- ECharts 展示路径图
- 路径长度信息 + 用时
- 共同电影列表（两个影人之间的合作电影）

---

### 3.8 统计看板 `/stats`

**对接 API**：

- `GET /api/stats/overview` — 总体统计
- `GET /api/stats/genre-distribution` — 类型分布
- `GET /api/stats/year-distribution` — 年代分布
- `GET /api/stats/top-actors?limit=20` — 参演最多演员
- `GET /api/stats/top-directors?limit=20` — 执导最多导演
- `GET /api/stats/rating-distribution` — 评分分布

**UI 组件**：

- 统计卡片：电影数/影人数/类型数/关系总数
- ECharts 图表：
    - 饼图：类型分布
    - 折线图：年代分布
    - 柱状图：评分分布
    - 横向柱状图：Top 演员 / Top 导演

---

### 3.9 登录 / 注册 `/login` `/register`

**对接 API**：

- `POST /api/auth/login` — 登录
- `POST /api/auth/register` — 注册
- `POST /api/auth/logout` — 登出
- `POST /api/auth/refresh` — 刷新 Token
- `GET /api/auth/me` — 获取当前用户

**状态管理 (Pinia)**：

- `useAuthStore`：token 存储（localStorage）、用户信息、登录/登出/刷新
- Axios 拦截器：自动附 Bearer Token、401 自动刷新或跳转登录

---

### 3.10 个人中心 `/profile`

**对接 API**：

- `GET /api/users/preferences?pref_type=like&page=&size=` — 喜欢列表
- `GET /api/users/preferences?pref_type=want_to_watch&page=&size=` — 想看列表
- `GET /api/users/ratings?page=&size=` — 评分列表
- `DELETE /api/users/preferences/{mid}` — 取消偏好
- `DELETE /api/users/ratings/{mid}` — 删除评分

**UI 组件**：

- 用户信息卡片（用户名/昵称/注册时间）
- Tab 切换：❤️ 喜欢 / 📌 想看 / ⭐ 评分
- 电影列表（支持取消/删除操作）

---

## 4. 项目目录结构

```
db-frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── api/                     # API 封装
│   │   ├── index.js             # Axios 实例 + 拦截器（Token 自动附加、401 自动刷新）
│   │   ├── auth.js              # 认证相关 API
│   │   ├── movies.js            # 电影相关 API
│   │   ├── persons.js           # 影人相关 API
│   │   ├── graph.js             # 图谱相关 API
│   │   ├── stats.js             # 统计相关 API
│   │   └── users.js             # 用户行为 API
│   ├── assets/
│   │   └── styles/
│   │       └── main.scss        # 全局样式（CSS 变量 + 暗色主题 + Element Plus 覆盖）
│   ├── components/              # 通用组件
│   │   ├── layout/
│   │   │   ├── AppHeader.vue    # 顶部导航（Logo/搜索/用户/毛玻璃效果）
│   │   │   └── AppFooter.vue    # 底部版权
│   │   ├── movie/
│   │   │   ├── MovieCard.vue    # 电影卡片（封面+评分角标+hover 上浮）
│   │   │   └── MovieList.vue    # 电影响应式网格
│   │   ├── person/
│   │   │   └── PersonCard.vue   # 影人卡片（头像+角色+合作次数）
│   │   └── graph/
│   │       └── GraphView.vue    # ECharts 图谱（待实现）
│   ├── router/
│   │   └── index.js             # 路由配置（12 条路由 + 懒加载 + 登录守卫）
│   ├── stores/
│   │   └── auth.js              # 认证状态管理（token/refreshToken/user + localStorage 持久化）
│   ├── utils/
│   │   └── image.js             # 图片代理工具（proxyImage — 解决豆瓣 CDN 防盗链）
│   ├── views/                   # 页面视图
│   │   ├── HomeView.vue         # ✅ 首页（Hero+统计+标签云+高分电影）
│   │   ├── SearchView.vue       # ✅ 搜索结果（电影/影人双 Tab+分页）
│   │   ├── MovieFilterView.vue  # ✅ 电影筛选（类型/年代/评分+分页）
│   │   ├── MovieDetailView.vue  # ✅ 电影详情（海报+评分+演职+偏好操作）
│   │   ├── PersonDetailView.vue # ✅ 影人详情（信息+作品+合作者）
│   │   ├── GraphView.vue        # 占位（Phase 3）
│   │   ├── PathView.vue         # 占位（Phase 3）
│   │   ├── StatsView.vue        # ✅ 统计看板（5 ECharts 图表）
│   │   ├── LoginView.vue        # ✅ 登录页（表单验证+redirect）
│   │   ├── RegisterView.vue     # ✅ 注册页（5 字段+密码验证）
│   │   ├── ProfileView.vue      # ✅ 个人中心（三 Tab+偏好/评分管理）
│   │   └── RecommendView.vue    # ✅ 推荐中心（算法切换+解释抽屉+重刷）
│   ├── App.vue                  # 根组件（Header+router-view 过渡动画+Footer）
│   └── main.js                  # 入口（Vue+Pinia+Router+ElementPlus+暗色主题）
├── .env                         # VITE_API_BASE=http://localhost:8000
├── index.html                   # lang=zh-CN, dark 主题, SEO meta
├── package.json
└── vite.config.js               # 开发代理 /api → localhost:8000
```

---

## 5. 分阶段实施计划

### Phase 1：工程骨架（0.5 天）✅ 已完成 (2026-02-25)

- ✅ Vite 创建 Vue3 项目（`create-vue@latest --router --pinia --bare`）
- ✅ 安装 Element Plus / ECharts / Axios / Pinia / Vue Router / Sass
- ✅ 配置 Vite 代理（开发时转发 `/api` → `http://localhost:8000`）
- ✅ 搭建 Layout（AppHeader 毛玻璃导航 + AppFooter + router-view 过渡动画）
- ✅ 配置路由表（11 条路由，全部懒加载 + 登录守卫）
- ✅ 编写 Axios 实例 + 6 个 API 模块（auth/movies/persons/graph/stats/users）
- ✅ 编写 Pinia auth store（token 持久化 + 自动刷新）
- ✅ 全局 SCSS 暗色主题（CSS 变量 + Element Plus 覆盖）

### Phase 2：核心浏览（1-1.5 天）✅ 已完成 (2026-02-25)

- ✅ 通用组件：MovieCard（封面+评分+hover 动效）、MovieList（响应式网格）、PersonCard（头像+角色）
- ✅ 首页（Hero 搜索框 + 统计概览 13.6 万电影/19.8 万影人 + 32 个类型标签云 + 高分电影卡片）
- ✅ 搜索结果页（电影/影人双 Tab + 分页器）
- ✅ 电影筛选页（类型标签选择 + 年代 Slider + 评分 Slider + 重置 + 94480 部电影网格）
- ✅ 电影详情页（海报 + 评分星级 + 剧情简介 + 导演/演员列表 + 喜欢/想看/评分/图谱/豆瓣链接）
- ✅ 影人详情页（基本信息 + 统计徽章 + 作品列表全部/导演/演员 Tab + 合作者网格）
- ✅ **补充**：后端图片代理 `/api/proxy/image`（解决豆瓣 CDN Referer 防盗链 418 问题）
- ✅ **补充**：前端 `utils/image.js` proxyImage 工具函数

### Phase 3：图谱可视化（1 天）✅ 已完成 (2026-03-01)

- ✅ KnowledgeGraph 通用组件封装（ECharts graph 力引导布局 + 线性布局）
- ✅ 电影/影人图谱页（复用 GraphView，包含控制面板与状态栏）
- ✅ 最短路径查询页（双搜索框联想防抖修复 + 路径图 + 共同电影列表）
- ✅ 图谱交互（多边标签合并、点击跳转、深度切换、图例过滤）
- ✅ **补充优化**：后端 2 跳图谱查询性能优化（Cypher 分步查询防路径爆炸，超时容错）
- ✅ **补充优化**：图谱 UI 细节重构（解决 ECharts 塌陷、等距 padding/gap 弹性布局、标题左对齐约束）

### Phase 4：用户系统 + 收尾（0.5-1 天）✅ 已完成 (2026-03-05)

- ✅ 登录页（Element Plus 表单验证 + redirect 支持 + 毛玻璃卡片居中布局）
- ✅ 注册页（5 字段表单 + 密码一致性验证 + 与登录页风格统一）
- ✅ 个人中心（用户信息卡片 + 喜欢/想看/评分三 Tab + 电影封面批量加载 + 取消/删除操作 + 分页）
- ✅ 统计看板（4 概览卡片 + 5 个 ECharts 图表：类型饼图、年代折线图、评分柱状图、Top 演员/导演横向柱状图）
- ✅ 全局 loading / 错误处理（Axios 拦截器 401 自动刷新 + ElMessage 全局提示）
- ✅ 响应式适配（移动端单列布局）

### Phase 5：智能推荐（1 天）✅ 已完成 (2026-03-07)

- ✅ 首页“为你推荐”占位区域替换为真实推荐预览
- ✅ `/recommend` 从占位页升级为推荐中心
- ✅ 对接 `GET /api/recommend/personal`，支持 `algorithm / limit / exclude_movie_ids / reroll_token`
- ✅ 对接 `GET /api/recommend/explain`，用于解释抽屉的证据小图与画像解释
- ✅ 首页与推荐页统一采用“用户画像驱动”口径，不展示主界面的显式依据电影
- ✅ 首页与推荐页当前固定使用 `CFKG` 默认主链路；多算法参数保留在后端接口层供实验与调试
- ✅ 推荐卡片支持轻量反馈：`喜欢 / 想看 / 去评分`
- ✅ 解释抽屉支持三层信息：推荐理由、关系可视化、算法指标
- ✅ 浏览器端实现“30 分钟内、按算法独立”的推荐重刷历史，仅在“重新生成”时避让上一批结果

---

## 6. 对接 API 清单

下表列出前端需要对接的全部后端 API：

| 模块 | 方法   | 路径                                 | 页面              |
| ---- | ------ | ------------------------------------ | ----------------- |
| 认证 | POST   | `/api/auth/register`                 | 注册页            |
| 认证 | POST   | `/api/auth/login`                    | 登录页            |
| 认证 | POST   | `/api/auth/logout`                   | 导航栏            |
| 认证 | POST   | `/api/auth/refresh`                  | Axios 拦截器      |
| 认证 | GET    | `/api/auth/me`                       | 全局              |
| 用户 | POST   | `/api/users/preferences`             | 电影详情          |
| 用户 | DELETE | `/api/users/preferences/{mid}`       | 电影详情/个人中心 |
| 用户 | GET    | `/api/users/preferences`             | 个人中心          |
| 用户 | GET    | `/api/users/preferences/check/{mid}` | 电影详情          |
| 用户 | POST   | `/api/users/ratings`                 | 电影详情          |
| 用户 | DELETE | `/api/users/ratings/{mid}`           | 电影详情/个人中心 |
| 用户 | GET    | `/api/users/ratings`                 | 个人中心          |
| 用户 | GET    | `/api/users/ratings/{mid}`           | 电影详情          |
| 电影 | GET    | `/api/movies/search`                 | 搜索页            |
| 电影 | GET    | `/api/movies/genres`                 | 首页/筛选页       |
| 电影 | GET    | `/api/movies/top`                    | 首页              |
| 电影 | GET    | `/api/movies/filter`                 | 筛选页            |
| 电影 | GET    | `/api/movies/{mid}`                  | 电影详情          |
| 电影 | GET    | `/api/movies/{mid}/credits`          | 电影详情          |
| 影人 | GET    | `/api/persons/search`                | 搜索页            |
| 影人 | GET    | `/api/persons/{pid}`                 | 影人详情          |
| 影人 | GET    | `/api/persons/{pid}/movies`          | 影人详情          |
| 影人 | GET    | `/api/persons/{pid}/collaborators`   | 影人详情          |
| 图谱 | GET    | `/api/graph/movie/{mid}`             | 图谱页            |
| 图谱 | GET    | `/api/graph/person/{pid}`            | 图谱页            |
| 图谱 | GET    | `/api/graph/path`                    | 路径页            |
| 图谱 | GET    | `/api/graph/common`                  | 路径页            |
| 统计 | GET    | `/api/stats/overview`                | 首页/统计页       |
| 统计 | GET    | `/api/stats/genre-distribution`      | 统计页            |
| 统计 | GET    | `/api/stats/year-distribution`       | 统计页            |
| 统计 | GET    | `/api/stats/top-actors`              | 统计页            |
| 统计 | GET    | `/api/stats/top-directors`           | 统计页            |
| 统计 | GET    | `/api/stats/rating-distribution`     | 统计页            |
| 推荐 | GET    | `/api/recommend/personal`            | 首页/推荐页       |
| 推荐 | GET    | `/api/recommend/explain`             | 首页/推荐页抽屉   |
| 代理 | GET    | `/api/proxy/image?url={url}`         | 全局（图片代理）  |

共计 **36 个 API** 对接（含 1 个图片代理接口）。

---

## 7. 设计风格

| 设计要素 | 方案                                                                   |
| -------- | ---------------------------------------------------------------------- |
| 色调     | 深色模式为主（#1a1a2e 背景 + #16213e 卡片），辅以豆瓣绿色(#00b51d)点缀 |
| 圆角     | 8-12px 圆角卡片                                                        |
| 动效     | 页面切换过渡、卡片 hover 浮起、图谱力引导动画                          |
| 字体     | 系统字体栈（`-apple-system, "Noto Sans SC", sans-serif`）              |
| 间距     | 8px 基础单位网格                                                       |
| 响应式   | ≥1200px 最大宽度，移动端适配（单列布局）                               |

---

## 8. 性能目标

| 指标                  | 目标值  |
| --------------------- | ------- |
| 首页加载 (FCP)        | < 1.5s  |
| 搜索延迟 (输入→结果)  | < 500ms |
| 图谱渲染（150 nodes） | < 2s    |
| 打包体积 (gzip)       | < 300KB |
| Lighthouse Score      | ≥ 80    |

---

## 9. 验证计划

### 自动验证

- `npm run build` 构建成功
- 无 TypeScript/ESLint 错误
- 开发服务器无控制台错误

### 手动验证

- 搜索 → 结果 → 详情 → 图谱 完整流程
- 注册 → 登录 → 喜欢 → 评分 → 个人中心 用户流程
- 图谱交互：节点点击、深度切换、缩放拖拽
- 统计页 6 个图表正确渲染
- 移动端响应式布局检查
