# db-backend — 豆瓣电影知识图谱后端

基于 **FastAPI** 的后端服务，提供电影/影人查询、知识图谱探索、用户认证与偏好管理等 API。

## 技术栈

- **Python 3.11+** / FastAPI / Pydantic
- **MySQL** — 电影、影人、用户数据存储
- **Neo4j** — 知识图谱（电影-影人-类型关系）
- **JWT** — 用户认证（access + refresh token）

## 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置环境变量

复制 `.env.example` 或直接编辑 `.env`：

```env
# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=douban_crawler
DB_PASS=your_password
DB_NAME=douban

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=your_password

# JWT
JWT_SECRET=your-secret-key
```

### 3. 启动服务

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后访问 http://localhost:8000/docs 查看 API 文档。

## 项目结构

```
app/
├── config.py          # 配置（环境变量）
├── main.py            # FastAPI 入口（中间件、路由注册）
├── dependencies.py    # 依赖注入（数据库连接）
├── db/                # 数据库连接管理
│   ├── mysql.py
│   └── neo4j.py
├── models/            # Pydantic 数据模型
│   ├── movie.py
│   ├── person.py
│   └── user.py
├── routers/           # API 路由
│   ├── auth.py        # 认证（登录/注册/刷新）
│   ├── movies.py      # 电影（搜索/筛选/详情/演职）
│   ├── persons.py     # 影人（搜索/详情/作品/合作）
│   ├── graph.py       # 图谱（关联/路径/共同）
│   ├── stats.py       # 统计（概览/分布/排行）
│   ├── users.py       # 用户行为（偏好/评分）
│   └── proxy.py       # 图片代理（豆瓣 CDN 防盗链）
└── services/          # 业务逻辑层
```

## API 概览

| 模块 | 路径前缀       | 说明                                |
| ---- | -------------- | ----------------------------------- |
| 认证 | `/api/auth`    | 注册、登录、登出、Token 刷新        |
| 电影 | `/api/movies`  | 搜索、筛选、Top、详情、演职人员     |
| 影人 | `/api/persons` | 搜索、详情、作品列表、合作者        |
| 图谱 | `/api/graph`   | 电影/影人关联图、最短路径、共同电影 |
| 统计 | `/api/stats`   | 概览、类型/年代/评分分布、排行      |
| 用户 | `/api/users`   | 喜欢、想看、评分管理                |
| 代理 | `/api/proxy`   | 豆瓣图片代理                        |
