# 后端开发规划书

**项目**: douban-kg-system 后端服务  
**框架**: FastAPI + Neo4j + MySQL  
**日期**: 2026-02-24

---

## 1. 后端定位与目标

后端是连接"知识图谱数据层"与"前端展示层"的桥梁，负责四大核心能力：

1. **数据查询服务**：提供电影搜索、详情、分类浏览等基础数据接口
2. **图谱查询服务**：封装 Neo4j Cypher 查询，提供关系探索和图谱可视化数据
3. **推荐引擎服务**：实现多种推荐算法，支持单电影推荐和基于用户偏好的个性化推荐
4. **用户与管理服务**：用户注册/登录/评分/偏好管理（喜欢/想看）以及管理员登录与用户管理

```
+-------------------------------------------------------------+
|  Vue3 前端                                                    |
|  （登录注册 / 电影搜索 / 详情 / 喜欢想看评分 / 推荐 / 图谱 / 管理后台）|
+-----------------+-------------------------------------------+
                  |  REST API (JSON) + JWT Token
+-----------------+-------------------------------------------+
|  FastAPI 后端                                                |
|  +----------+ +----------+ +----------+ +--------------+    |
|  | 用户API  | | 电影API  | | 图谱API  | | 推荐引擎API  |    |
|  +----+-----+ +----+-----+ +----+-----+ +------+-------+    |
|       |            |            |               |            |
|  +----+------------+------------+---------------+--------+   |
|  |                  服务层 (Service Layer)                |   |
|  |  UserService / MovieService / GraphService /           |   |
|  |  RecommendService（含个性化推荐）                      |   |
|  +----+------------+--------------------+----------------+   |
|       |            |                    |                    |
|  +----+--------+ +-+----------+ +-------+---------------+   |
|  | MySQL 连接  | | Neo4j 连接 | | 推荐算法引擎             |   |
|  | (用户+电影) | | (图谱查询) | | (PPR/Content/CF/Hybrid) |   |
|  +-------------+ +------------+ +-----------------------+   |
+-------------------------------------------------------------+
```

---

## 2. 项目结构设计

```
db-backend/
+-- app/
|   +-- __init__.py
|   +-- main.py                 # FastAPI 应用入口，注册路由和中间件
|   +-- config.py               # 配置管理（数据库连接、环境变量）
|   +-- dependencies.py         # 依赖注入（数据库 session、Neo4j driver、JWT）
|   |
|   +-- models/                 # Pydantic 数据模型（请求/响应 Schema）
|   |   +-- __init__.py
|   |   +-- movie.py            # MovieBase, MovieDetail, MovieListResponse
|   |   +-- person.py           # PersonBase, PersonDetail
|   |   +-- graph.py            # GraphNode, GraphEdge, GraphResponse
|   |   +-- recommend.py        # RecommendRequest, RecommendResponse
|   |   +-- user.py             # UserRegister, UserLogin, UserPreference
|   |   +-- admin.py            # AdminLogin, AdminUserUpdate, AdminActionLog
|   |
|   +-- routers/                # 路由层（API 端点定义）
|   |   +-- __init__.py
|   |   +-- auth.py             # /api/auth/...（注册、登录）
|   |   +-- admin_auth.py       # /api/admin/auth/...（管理员登录、登出）
|   |   +-- admin_users.py      # /api/admin/users/...（用户管理）
|   |   +-- users.py            # /api/users/...（偏好管理）
|   |   +-- movies.py           # /api/movies/...
|   |   +-- persons.py          # /api/persons/...
|   |   +-- graph.py            # /api/graph/...
|   |   +-- recommend.py        # /api/recommend/...
|   |   +-- stats.py            # /api/stats/...
|   |
|   +-- services/               # 业务逻辑层
|   |   +-- __init__.py
|   |   +-- auth_service.py     # 注册、登录、JWT 管理
|   |   +-- user_service.py     # 用户行为（喜欢/想看/评分）管理
|   |   +-- admin_service.py    # 管理员鉴权与用户管理
|   |   +-- movie_service.py    # 电影查询、搜索、筛选
|   |   +-- person_service.py   # 影人查询
|   |   +-- graph_service.py    # 图谱关系探索
|   |   +-- recommend_service.py # 推荐引擎调度（含个性化推荐）
|   |
|   +-- algorithms/             # 推荐算法实现
|   |   +-- __init__.py
|   |   +-- base.py             # 推荐算法基类
|   |   +-- ppr.py              # Personalized PageRank
|   |   +-- content_based.py    # 基于内容的推荐
|   |   +-- collaborative_filtering.py # 协同过滤（ItemCF/UserCF）
|   |   +-- hybrid.py           # 混合推荐策略
|   |
|   +-- db/                     # 数据库连接管理
|       +-- __init__.py
|       +-- mysql.py            # MySQL 连接池
|       +-- neo4j.py            # Neo4j Driver 管理
|
+-- tests/                      # 测试
|   +-- test_movies.py
|   +-- test_graph.py
|   +-- test_recommend.py
|   +-- test_auth.py
|
+-- .env                        # 环境变量
+-- pyproject.toml              # 依赖管理
+-- README.md
```

---

## 3. API 接口设计

### 3.1 电影查询 API (`/api/movies`)

| 方法 | 路径                                                                    | 说明                 | 数据源 |
| ---- | ----------------------------------------------------------------------- | -------------------- | ------ |
| GET  | `/api/movies/search?q={keyword}&page=1&size=20`                         | 关键词搜索电影       | MySQL  |
| GET  | `/api/movies/{mid}`                                                     | 获取电影详情         | Neo4j  |
| GET  | `/api/movies/{mid}/credits`                                             | 获取电影演职人员     | Neo4j  |
| GET  | `/api/movies/top?genre={genre}&limit=20`                                | 获取高分电影排行     | Neo4j  |
| GET  | `/api/movies/genres`                                                    | 获取所有电影类型列表 | Neo4j  |
| GET  | `/api/movies/filter?genre=&year_from=&year_to=&rating_min=&page=&size=` | 多条件筛选电影       | Neo4j  |

**设计理由**：

- 搜索接口使用 MySQL 的 `LIKE` 或全文索引，因为搜索是扫描性操作，MySQL 有成熟的索引优化
- 详情和关系接口使用 Neo4j，因为需要高效获取关联的导演、演员和类型信息

**响应示例** (`GET /api/movies/1292052`)：

```json
{
    "mid": "1292052",
    "title": "肖申克的救赎 The Shawshank Redemption",
    "rating": 9.7,
    "year": 1994,
    "content_type": "movie",
    "genres": ["剧情", "犯罪"],
    "regions": "美国",
    "cover": "https://img...",
    "storyline": "一个银行家被冤枉入狱...",
    "url": "https://movie.douban.com/subject/1292052/",
    "directors": [
        { "pid": "1047973", "name": "弗兰克·德拉邦特 Frank Darabont" }
    ],
    "actors": [
        { "pid": "1054521", "name": "蒂姆·罗宾斯 Tim Robbins", "order": 1 },
        { "pid": "1054534", "name": "摩根·弗里曼 Morgan Freeman", "order": 2 }
    ]
}
```

### 3.2 影人查询 API (`/api/persons`)

| 方法 | 路径                                             | 说明                    | 数据源 |
| ---- | ------------------------------------------------ | ----------------------- | ------ |
| GET  | `/api/persons/search?q={keyword}&page=1&size=20` | 搜索影人                | MySQL  |
| GET  | `/api/persons/{pid}`                             | 影人详情                | Neo4j  |
| GET  | `/api/persons/{pid}/movies`                      | 影人参演/执导的电影列表 | Neo4j  |
| GET  | `/api/persons/{pid}/collaborators?limit=10`      | 影人的常见合作者        | Neo4j  |

**响应示例** (`GET /api/persons/1054521`)：

```json
{
    "pid": "1054521",
    "name": "蒂姆·罗宾斯 Tim Robbins",
    "sex": "男",
    "birth": "1958-10-16",
    "birthplace": "美国,加利福尼亚州,西科维纳",
    "profession": "演员/导演/编剧/制片人",
    "biography": "蒂姆·罗宾斯出生于...",
    "movie_count": 42,
    "directed_count": 5
}
```

### 3.3 图谱探索 API (`/api/graph`)

这组 API 是前端**图谱可视化组件**的数据接口，返回标准的 `nodes + edges` 格式。

| 方法 | 路径                                                                                         | 说明                               |
| ---- | -------------------------------------------------------------------------------------------- | ---------------------------------- |
| GET  | `/api/graph/movie/{mid}?depth=1&node_limit=150&edge_limit=300`                              | 以电影为中心，展开 N 跳关联图      |
| GET  | `/api/graph/person/{pid}?depth=1&node_limit=150&edge_limit=300`                             | 以影人为中心，展开 N 跳关联图      |
| GET  | `/api/graph/path?from={id1}&to={id2}&max_hops=6`                                             | 查找两个实体之间的最短路径         |
| GET  | `/api/graph/common?person1={pid1}&person2={pid2}&limit=50`                                  | 查找两位影人的合作电影             |
| GET  | `/api/graph/movie/{mid}?depth=2&node_limit=300&edge_limit=600&timeout_ms=1500`             | 2 跳查询（仅高级模式，默认关闭）   |

**稳定性约束（必须）**：

- `depth` 默认 `1`，最大 `2`；未授权或未显式开启时拒绝 2 跳
- `node_limit` 默认 `150`，最大 `500`
- `edge_limit` 默认 `300`，最大 `1000`
- `timeout_ms` 默认 `1200`，最大 `3000`，超时返回可部分展示的数据并标记截断

**响应格式**（适配 ECharts / D3.js 图可视化）：

```json
{
    "nodes": [
        {
            "id": "movie_1292052",
            "label": "肖申克的救赎",
            "type": "Movie",
            "properties": { "rating": 9.7 }
        },
        {
            "id": "person_1047973",
            "label": "弗兰克·德拉邦特",
            "type": "Person"
        },
        { "id": "genre_剧情", "label": "剧情", "type": "Genre" }
    ],
    "edges": [
        {
            "source": "person_1047973",
            "target": "movie_1292052",
            "type": "DIRECTED"
        },
        {
            "source": "movie_1292052",
            "target": "genre_剧情",
            "type": "HAS_GENRE"
        }
    ],
    "meta": {
        "depth": 1,
        "node_count": 3,
        "edge_count": 2,
        "truncated": false,
        "query_time_ms": 46
    }
}
```

### 3.4 用户认证 API (`/api/auth`)

| 方法 | 路径                 | 说明                     | 认证 |
| ---- | -------------------- | ------------------------ | ---- |
| POST | `/api/auth/register` | 用户注册                 | 无需 |
| POST | `/api/auth/login`    | 用户登录，返回 JWT Token | 无需 |
| POST | `/api/auth/logout`   | 用户登出（撤销会话）     | 需要 |
| POST | `/api/auth/refresh`  | 刷新 Access Token        | 需要 |
| GET  | `/api/auth/me`       | 获取当前登录用户信息     | 需要 |

**注册请求**：

```json
{ "username": "zhangsan", "password": "123456", "nickname": "张三" }
```

**登录响应**：

```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": { "id": 1, "username": "zhangsan", "nickname": "张三" }
}
```

**认证机制**：采用 **JWT（JSON Web Token）** 无状态认证：

- 用户登录成功后，服务端签发 `access_token`（建议 15~30 分钟）和可选 `refresh_token`
- 默认使用 **HttpOnly + Secure + SameSite** Cookie 传输 token（降低 XSS 窃取风险）
- 若前后端分离必须使用 Bearer Token，再由前端在 Header 中携带 `Authorization: Bearer <token>`
- 服务端验证 Token 签名并提取用户身份，无需维护 Session 状态
- refresh token 存储于 `user_sessions`，支持轮换和手动注销

**密码安全**：使用 `bcrypt` 算法对密码进行哈希存储，即使数据库被攻破也无法还原明文密码。

### 3.5 用户行为 API (`/api/users`)

| 方法   | 路径                                   | 说明                       | 认证 |
| ------ | -------------------------------------- | -------------------------- | ---- |
| POST   | `/api/users/preferences`               | 添加偏好（喜欢/想看）      | 需要 |
| DELETE | `/api/users/preferences/{mid}`         | 取消偏好                   | 需要 |
| GET    | `/api/users/preferences?type=like`     | 获取用户偏好列表           | 需要 |
| GET    | `/api/users/preferences/check/{mid}`   | 检查某电影偏好状态         | 需要 |
| POST   | `/api/users/ratings`                   | 创建/更新用户评分          | 需要 |
| DELETE | `/api/users/ratings/{mid}`             | 删除用户评分               | 需要 |
| GET    | `/api/users/ratings`                   | 获取用户评分列表           | 需要 |
| GET    | `/api/users/ratings/{mid}`             | 获取用户对某电影评分       | 需要 |
| GET    | `/api/users/search-history?page=&size=` | 获取用户搜索历史（可选）   | 需要 |

**偏好请求示例**：

```json
{ "mid": "1292052", "pref_type": "like" }
```

`pref_type` 可选值：

- `like`（喜欢）：表示用户已看过并喜欢这部电影，推荐权重高（0.7）
- `want_to_watch`（想看）：表示用户感兴趣但还没看，推荐权重低（0.3）

**评分请求示例**：

```json
{ "mid": "1292052", "rating": 4.5, "comment_short": "剧情扎实，节奏很好" }
```

评分范围建议：`0.5` 到 `5.0`，步长 `0.5`。

### 3.6 管理员 API (`/api/admin`)

| 方法  | 路径                            | 说明                 | 认证 |
| ----- | ------------------------------- | -------------------- | ---- |
| POST  | `/api/admin/auth/login`         | 管理员登录           | 无需 |
| POST  | `/api/admin/auth/logout`        | 管理员登出           | 需要 |
| GET   | `/api/admin/users?page=&size=`  | 用户列表（筛选状态） | 需要 |
| GET   | `/api/admin/users/{uid}`        | 用户详情             | 需要 |
| PATCH | `/api/admin/users/{uid}`        | 更新用户状态/资料    | 需要 |
| POST  | `/api/admin/users/{uid}/ban`    | 封禁用户             | 需要 |
| POST  | `/api/admin/users/{uid}/unban`  | 解封用户             | 需要 |
| POST  | `/api/admin/users/{uid}/logout` | 强制用户下线         | 需要 |

**管理员能力边界**：

- 管理员只能管理普通用户，不可操作其他管理员账号
- 所有高风险操作（封禁、解封、强制下线、重置密码）写入审计日志
- 建议角色：`super_admin` / `admin` / `auditor`

**应用层 MySQL 表设计（用户 + 管理员）**：

```sql
-- 普通用户
CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(50) NULL,
    avatar_url VARCHAR(500) NULL,
    status ENUM('active', 'banned', 'deleted') NOT NULL DEFAULT 'active',
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_users_status_created (status, created_at)
);

-- 用户会话（登录/登出）
CREATE TABLE user_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL UNIQUE,
    user_agent VARCHAR(255) NULL,
    ip_address VARCHAR(45) NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_sessions_user (user_id, created_at),
    INDEX idx_user_sessions_expires (expires_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 用户偏好（喜欢/想看）
CREATE TABLE user_movie_prefs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    mid VARCHAR(20) NOT NULL COMMENT '映射 movies.douban_id',
    pref_type ENUM('like', 'want_to_watch') NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_mid (user_id, mid),
    INDEX idx_user_pref_type (user_id, pref_type),
    INDEX idx_mid_pref_type (mid, pref_type),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 用户评分
CREATE TABLE user_movie_ratings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    mid VARCHAR(20) NOT NULL COMMENT '映射 movies.douban_id',
    rating DECIMAL(2,1) NOT NULL COMMENT '0.5 - 5.0',
    comment_short VARCHAR(500) NULL,
    rated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_mid_rating (user_id, mid),
    INDEX idx_mid_rating (mid, rating),
    INDEX idx_user_rated_at (user_id, rated_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 用户搜索历史（可选）
CREATE TABLE user_search_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NULL,
    query_text VARCHAR(255) NOT NULL,
    result_count INT NOT NULL DEFAULT 0,
    searched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_searched_at (user_id, searched_at),
    INDEX idx_query_text (query_text)
);

-- 管理员账号
CREATE TABLE admins (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('super_admin', 'admin', 'auditor') NOT NULL DEFAULT 'admin',
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_admin_status_role (status, role)
);

-- 管理员会话
CREATE TABLE admin_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL UNIQUE,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_sessions_admin (admin_id, created_at),
    FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
);

-- 管理员操作审计
CREATE TABLE admin_user_actions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    target_user_id BIGINT NOT NULL,
    action_type ENUM(
        'ban_user', 'unban_user', 'force_logout',
        'reset_password', 'update_profile', 'delete_user'
    ) NOT NULL,
    reason VARCHAR(255) NULL,
    metadata_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_action_time (admin_id, created_at),
    INDEX idx_target_action_time (target_user_id, created_at),
    FOREIGN KEY (admin_id) REFERENCES admins(id),
    FOREIGN KEY (target_user_id) REFERENCES users(id)
);
```

电影搜索索引建议（复用 `movies` 表）：

```sql
ALTER TABLE movies ADD FULLTEXT INDEX ft_name_alias (name, alias);
CREATE INDEX idx_movies_year ON movies(year);
CREATE INDEX idx_movies_score ON movies(douban_score);
```

### 3.7 推荐 API (`/api/recommend`)

| 方法 | 路径                                                   | 说明                         | 认证     |
| ---- | ------------------------------------------------------ | ---------------------------- | -------- |
| GET  | `/api/recommend/movie/{mid}?algorithm=hybrid&limit=10` | 基于单部电影的相似推荐       | 无需     |
| GET  | `/api/recommend/personal?algorithm=hybrid&limit=10`    | **基于用户偏好的个性化推荐** | **需要** |
| GET  | `/api/recommend/person/{pid}?limit=10`                 | 根据影人推荐电影             | 无需     |
| GET  | `/api/recommend/algorithms`                            | 获取可用的推荐算法列表       | 无需     |

**`algorithm` 参数可选值**：

| 值        | 算法                  | 论文中的学术名称        | 原理简述                                       |
| --------- | --------------------- | ----------------------- | ---------------------------------------------- |
| `ppr`     | Personalized PageRank | 个性化 PageRank         | 以目标电影为起点在图上随机游走，按访问频率排序 |
| `content` | 基于内容推荐          | Content-Based Filtering | 根据类型、导演、地区等属性计算相似度           |
| `cf`      | 协同过滤推荐          | Collaborative Filtering | 基于用户-电影交互矩阵计算相似用户/相似物品     |
| `hybrid`  | 混合推荐              | Hybrid Recommendation   | 加权融合 PPR、Content 和 CF 的结果             |

**补充参数约定**：

- `limit` 默认 `10`，最大 `50`
- `algorithm=hybrid` 时允许传入 `weights=w1,w2,w3`（如 `0.5,0.3,0.2`）；非法权重回退默认值
- 个性化推荐在用户偏好为空时，自动降级为 `top` 榜单或基于热门类型的冷启动推荐

**个性化推荐的核心逻辑**（`/api/recommend/personal`）：

1. 从 `user_movie_prefs` 表获取当前用户所有偏好电影
2. 按 `pref_type` 赋予权重：`like` = 0.7，`want_to_watch` = 0.3
3. 将这些电影作为**多个种子节点**输入推荐算法：
    - **PPR 模式**：多起点随机游走，每个种子的跳回概率按权重分配
    - **Content 模式**：取所有种子电影特征向量的加权平均，作为"用户口味画像"
    - **CF 模式**：基于用户偏好矩阵计算邻域相似度并召回候选电影
    - **Hybrid 模式**：融合三种算法的结果（数据不足时自动关闭 CF 分支）
4. 排除用户已标记过的电影（避免推荐已看过的）

**响应示例** (`GET /api/recommend/personal?algorithm=hybrid&limit=5`)：

```json
{
    "user": { "id": 1, "nickname": "张三" },
    "algorithm": "hybrid",
    "based_on": [
        { "mid": "1292052", "title": "肖申克的救赎", "pref_type": "like" },
        { "mid": "1291546", "title": "霸王别姬", "pref_type": "like" }
    ],
    "recommendations": [
        {
            "mid": "1292063",
            "title": "美丽人生",
            "rating": 9.5,
            "genres": ["剧情", "喜剧", "爱情"],
            "cover": "https://img...",
            "score": 0.89,
            "reason": "与您喜欢的《肖申克的救赎》有相似的剧情风格"
        }
    ]
}
```

### 3.8 统计 API (`/api/stats`)

| 方法 | 路径                                | 说明                             |
| ---- | ----------------------------------- | -------------------------------- |
| GET  | `/api/stats/overview`               | 图谱总体统计（节点数、关系数等） |
| GET  | `/api/stats/genre-distribution`     | 电影类型分布                     |
| GET  | `/api/stats/year-distribution`      | 年代分布                         |
| GET  | `/api/stats/top-actors?limit=20`    | 参演最多的演员排行               |
| GET  | `/api/stats/top-directors?limit=20` | 执导最多的导演排行               |
| GET  | `/api/stats/rating-distribution`    | 评分分布                         |

### 3.9 图谱可视化协同设计（前后端联动）

为保证图谱页面可读、可控、可交互，后端接口需与前端可视化约定统一数据契约：

**节点与边映射规范**：

- `node.type`：`Movie` / `Person` / `Genre`，前端按类型映射颜色与大小
- `node.properties`：最少返回 `rating`、`year`、`profession` 等 tooltip 字段
- `edge.type`：`DIRECTED` / `ACTED_IN` / `HAS_GENRE`，前端按关系类型映射线型
- `meta.truncated`：`true` 时前端显示“结果已截断”提示并允许继续展开

**前端建议交互（ECharts / D3.js）**：

- 首屏默认展示 1 跳子图，中心节点固定在画布中心
- 支持“点击节点二次展开”，每次增量加载 1 跳并走同一限流参数
- 支持按关系类型过滤（仅导演、仅演员、仅类型）和按评分区间过滤
- 支持图-表联动：选中节点时右侧展示电影或影人详情卡片

**推荐可视化扩展（可选）**：

- 推荐结果页支持“推荐理由图谱化”，展示 `seed_movie -> person/genre -> recommended_movie`
- 对每条推荐返回 `explain_paths`（最多 3 条）用于可解释展示

---

## 4. 推荐算法设计

### 4.1 算法一：Personalized PageRank (PPR)

**原理**：

标准 PageRank 是 Google 搜索引擎的核心算法，用于衡量网页的"重要性"。Personalized PageRank（个性化 PageRank）是其变体，核心思想是：

以目标电影为"起始节点"，在整个图谱上进行**随机游走（Random Walk）**：

- 每一步，以概率 alpha（通常取 0.85）沿着关系边走向相邻节点
- 以概率 1-alpha（即 0.15）**跳回起始节点**
- 经过大量迭代后，每个节点被访问的概率趋于稳定
- 被访问概率最高的 Movie 节点即为推荐结果

**单电影推荐 vs 个性化推荐**：

- **单电影**：起始节点为 1 个电影，跳回时 100% 概率回到该电影
- **个性化推荐**：起始节点为用户偏好的 N 部电影，跳回时按偏好权重分配概率（如"喜欢"的电影占 70%，"想看"的占 30%），最终推荐结果融合了用户的整体口味

**为什么适合我们的图谱**：

- 如果一部电影和目标电影**共享相同的导演、演员或类型**，随机游走者更容易到达它
- PPR 天然能发现**多跳隐性关联**：例如"和目标电影导演的其他作品风格类似的电影"

**备选 Python 实现**（不依赖 GDS 插件）：

```python
def personalized_pagerank(graph, source_ids, source_weights, alpha=0.85, max_iter=100):
    """
    graph: {node_id: [neighbor_ids]}
    source_ids: 种子节点列表（单电影推荐时为1个，个性化推荐时为多个）
    source_weights: 每个种子的跳回权重
    """
    scores = {node: 0.0 for node in graph}
    # 初始概率分配给种子节点
    for sid, w in zip(source_ids, source_weights):
        scores[sid] = w

    for _ in range(max_iter):
        new_scores = {}
        for node in graph:
            # 跳回种子节点的概率（按权重分配）
            teleport = 0.0
            if node in source_ids:
                idx = source_ids.index(node)
                teleport = source_weights[idx]
            new_scores[node] = (1 - alpha) * teleport
            # 来自邻居的传播
            for neighbor in graph[node]:
                out_degree = len(graph[neighbor])
                if out_degree > 0:
                    new_scores[node] += alpha * scores[neighbor] / out_degree
        scores = new_scores

    return sorted(scores.items(), key=lambda x: -x[1])
```

### 4.2 算法二：基于内容推荐 (Content-Based)

**原理**：

将每部电影表示为一个**特征向量**，通过计算两部电影特征向量之间的**余弦相似度**来度量相似程度。

**特征维度设计**：

| 特征           | 编码方式                             | 权重 | 理由                       |
| -------------- | ------------------------------------ | ---- | -------------------------- |
| 类型 (genres)  | Multi-Hot 编码（32维，每种类型一位） | 0.35 | 类型是用户兴趣的最直接标签 |
| 导演           | One-Hot 编码 + 相似度匹配            | 0.25 | 导演风格对电影调性影响极大 |
| 地区 (regions) | Multi-Hot 编码                       | 0.10 | 不同地区有不同的电影风格   |
| 评分 (rating)  | 归一化到 [0, 1]                      | 0.15 | 推荐质量相近的作品         |
| 年代 (year)    | 高斯衰减函数                         | 0.10 | 年代越接近越相似           |
| 演员重合度     | Jaccard 系数                         | 0.05 | 共同演员暗示风格相近       |

**个性化推荐时**：取用户所有偏好电影的特征向量，按 `like`/`want_to_watch` 权重加权平均，得到一个**用户口味画像向量（User Profile Vector）**，然后找与该画像最相似的电影。

**余弦相似度计算**：

```
similarity(A, B) = (A . B) / (||A|| x ||B||)
```

### 4.3 算法三：混合推荐 (Hybrid)

**原理**：

单一推荐算法各有局限——PPR 擅长发现**图谱结构上的关联**但可能推荐类型差异较大的电影；Content-Based 擅长推荐**属性相似**的电影但容易导致"信息茧房"；Collaborative Filtering 擅长学习群体偏好但依赖用户行为规模。

混合推荐通过**加权线性融合**三种算法的推荐评分，取长补短：

```
hybrid_score(movie) = w1 x ppr_score(movie) + w2 x content_score(movie) + w3 x cf_score(movie)
```

**默认权重**：`w1 = 0.5`（PPR），`w2 = 0.3`（Content-Based），`w3 = 0.2`（CF）

**可调参数**：前端可以通过 `weights` 参数调整比例，用于对比实验。  
当用户行为数据不足时，自动使用两路融合：`w1 = 0.6`，`w2 = 0.4`，`w3 = 0`。

### 4.4 算法四：协同过滤 (Collaborative Filtering, CF)

**结论（是否适合本项目）**：**适合加入，但应作为增强算法而非首发主算法**。

**适配原因**：

- 项目已有 `user_movie_prefs` 交互表，具备用户-电影矩阵基础
- 电影推荐场景中，用户群体偏好可补足图谱和内容相似度的盲点
- 可直接产出“和你口味相似的用户也喜欢”这类可解释理由

**风险与约束**：

- 冷启动明显：新用户和长尾电影缺少交互时效果差
- 数据稀疏：若活跃用户少，UserCF 召回不稳定
- 偏好噪声：`want_to_watch` 代表意图，不等同于真实喜欢

**实现策略（推荐）**：

- 首版采用 **ItemCF**（物品协同过滤）优先：稳定、离线预计算成本可控
- 可选补充 **UserCF**：用于“相似用户推荐”解释场景
- 评分构造：`like=1.0`，`want_to_watch=0.5`，可按时间衰减
- 相似度指标：余弦相似度或 Jaccard，相似度矩阵离线更新（如每 6 小时）

**启用门槛（建议）**：

- 活跃用户数 `>= 500`
- 人均偏好电影数 `>= 10`
- 近 7 天新增交互 `>= 2000`

未达门槛时，`algorithm=cf` 返回“数据不足”，并建议前端回退到 `hybrid`（不含 CF 分量）。

### 4.5 算法调度与降级策略

- **默认算法**：`hybrid`
- **冷启动用户**（无偏好）：优先 `content + 热门榜`
- **低活跃数据期**：关闭 `cf` 分量，退化为 `ppr+content`
- **高并发保护**：推荐超时优先返回缓存结果或热门兜底列表

---

## 5. 数据库连接设计

### 5.1 双数据源架构

后端同时连接两个数据库，各司其职：

| 数据库    | 用途                                             | 连接方式       |
| --------- | ------------------------------------------------ | -------------- |
| **MySQL** | 全文搜索、关键词模糊匹配、分页查询、用户数据管理 | PyMySQL 连接池 |
| **Neo4j** | 图谱关系查询、图算法执行、推荐计算               | neo4j 官方驱动 |

**设计理由**：

- Neo4j 的全文搜索能力较弱（需要额外配置全文索引），而 MySQL 在 LIKE 查询和全文索引方面非常成熟
- Neo4j 在关系遍历和图算法方面有绝对优势
- 用户数据（注册、登录、偏好）属于典型的关系型数据，适合存在 MySQL 中
- 两者配合使用，互补短板

### 5.2 连接池与生命周期管理

```python
# app/db/neo4j.py
from neo4j import GraphDatabase

class Neo4jConnection:
    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            cls._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASS),
                max_connection_pool_size=50
            )
        return cls._driver

    @classmethod
    def close(cls):
        if cls._driver:
            cls._driver.close()
```

在 FastAPI 的 `lifespan` 事件中管理连接生命周期：

```python
# app/main.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化连接
    Neo4jConnection.get_driver()
    yield
    # 关闭时释放连接
    Neo4jConnection.close()
```

### 5.3 双库一致性策略（新增）

为避免出现“搜索命中但详情缺失”的双库不一致问题，后端需要明确一致性策略：

- **同步链路**：`MySQL(cleaned)` -> `ETL` -> `Neo4j`，每次 ETL 生成批次号 `etl_version`
- **读路径校验**：电影详情接口先查 Neo4j，未命中时回退 MySQL 基础信息并返回 `partial=true`
- **一致性 SLA**：常规 ETL 延迟目标 `< 24h`；手动补数任务延迟 `< 1h`
- **巡检任务**：每日比对 `movies.mid` 与 `(:Movie {mid})` 覆盖率，输出缺口清单
- **告警阈值**：缺失率超过 `0.5%` 触发告警并暂停推荐接口的全量刷新

---

## 6. 分阶段实施计划

### 6.1 交付范围分层

为保证进度和可验收性，后端按两层交付：

- **MVP（第1-2周）**：可用系统最小闭环，优先保证查询与图谱展示
- **v1.1（第3周）**：补齐推荐算法与个性化能力，完成性能与效果评估

### 6.2 MVP（第1-2周，约 9~11 人天）

| 子阶段 | 工期 | 目标 | 关键交付 |
| ------ | ---- | ---- | -------- |
| A. 工程基线 | 1~2 天 | 后端可启动、可观测 | FastAPI 骨架、配置管理、`GET /health`、日志中间件 |
| B. 认证与用户体系 | 2~3 天 | 用户与管理员体系闭环 | 用户/管理员登录登出、会话管理、偏好 + 评分 CRUD、审计日志 |
| C. 查询 API | 3 天 | 前端核心页面可用 | movies/persons 搜索与详情接口 |
| D. 图谱与统计 | 2 天 | 图谱页可稳定展示 | graph 1-hop API、统计 API、可视化数据契约与节点/边限流参数 |
| E. 测试联调 | 1~2 天 | 可发布候选版本 | OpenAPI 文档、核心接口测试、前后端联调 |

**MVP 验收门槛**：

- 认证、查询、图谱、统计接口全部可访问，错误码规范化
- Graph API 在限制参数下不超时，且返回 `meta.truncated` 状态
- 覆盖最少 20 条 API 自动化测试（含鉴权失败和参数边界）
- 上线前完成一次双库一致性巡检

### 6.3 v1.1（第3周，约 5~7 人天）

| 子阶段 | 工期 | 目标 | 关键交付 |
| ------ | ---- | ---- | -------- |
| F. 推荐算法实现 | 3~4 天 | 推荐功能可用 | PPR、Content、CF、Hybrid、推荐服务层 |
| G. 个性化与缓存 | 1~2 天 | 个性化推荐稳定 | `recommend/personal`、CF 相似度缓存、冷启动降级 |
| H. 评估与压测 | 1 天 | 可量化验收 | 离线指标脚本、性能压测报告、参数调优记录 |

**v1.1 验收门槛**：

- `movie`/`personal`/`person` 推荐接口可用，支持算法切换
- 推荐接口性能满足第 10 节 P95 指标
- 产出推荐质量基线（Precision@10、Recall@10、NDCG@10）
- 评估报告包含 CF 启用门槛是否达标及开关策略

### 6.4 里程碑（与总计划对齐）

- **M1（第1周末）**：完成工程基线 + 用户认证
- **M2（第2周末）**：完成查询/图谱/统计 MVP，前后端可联调
- **M3（第3周末）**：完成推荐 v1.1 与性能/质量验收

---

## 7. 配置与环境变量

```env
# .env 文件
# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_mysql_user
DB_PASS=your_mysql_password
DB_NAME=douban
DB_POOL_SIZE=20

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=your_neo4j_user
NEO4J_PASS=your_neo4j_password
NEO4J_MAX_CONNECTION_POOL_SIZE=50

# FastAPI
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
APP_ENV=dev

# JWT
JWT_SECRET=your-secret-key-change-in-production
JWT_ACCESS_EXPIRE_MINUTES=30
JWT_REFRESH_EXPIRE_DAYS=7
AUTH_TOKEN_TRANSPORT=cookie

# Cache
CACHE_TTL_SECONDS=300
```

---

## 8. 依赖管理

核心依赖（`pyproject.toml`）的调整建议：

| 依赖                        | 版本      | 用途                 | 备注                                                             |
| --------------------------- | --------- | -------------------- | ---------------------------------------------------------------- |
| `fastapi[standard]`         | >=0.112.0 | Web 框架             | 已有                                                             |
| `pydantic`                  | >=2.7.0   | 数据校验             | 已有                                                             |
| `pydantic-settings`         | >=2.2.0   | 环境变量配置管理     | 已有                                                             |
| `neo4j`                     | >=5.17.0  | Neo4j 驱动           | 已有                                                             |
| `pymysql`                   | >=1.1.0   | MySQL 连接           | 应保留                                                           |
| `python-dotenv`             | >=1.0.0   | .env 文件加载        | 已有                                                             |
| `numpy`                     | >=1.26.0  | 推荐算法数值计算     | 已有                                                             |
| `scikit-learn`              | >=1.4.0   | 余弦相似度等度量函数 | 推荐模块新增                                                     |
| `scipy`                     | >=1.12.0  | 稀疏矩阵计算         | 协同过滤（ItemCF/UserCF）建议新增                                |
| `python-jose[cryptography]` | >=3.3.0   | JWT Token 签发与验证 | 认证模块新增                                                     |
| `passlib[bcrypt]`           | >=1.7.0   | 密码哈希（bcrypt）   | 认证模块新增                                                     |
| `cachetools`                | >=5.3.0   | 本地缓存 TTL         | 可选（不接 Redis 时使用）                                        |
| ~~`hanlp`~~                 | -         | -                    | 建议从 `db-backend` 依赖移除，仅保留在数据处理/离线实验环境中    |
| ~~`jieba`~~                 | -         | -                    | 同上                                                             |
| `pandas`                    | >=2.2.0   | 离线特征处理         | 建议不在在线请求链路中使用；可留在离线任务依赖中                 |

---

## 9. 论文对应关系

后端开发的各模块与毕业论文章节的对应关系：

| 后端模块           | 论文章节                           | 重点阐述内容                                                 |
| ------------------ | ---------------------------------- | ------------------------------------------------------------ |
| 项目结构与分层设计 | 系统设计 -- 总体架构               | 三层架构（路由层->服务层->数据层）的设计理由，关注点分离原则 |
| 用户认证系统       | 系统设计 -- 用户模块               | JWT 无状态认证、bcrypt 密码安全、会话撤销机制                |
| 用户行为系统       | 系统设计 -- 用户模块               | 喜欢/想看、评分、搜索历史等行为数据模型                      |
| 管理员系统         | 系统设计 -- 管理模块               | RBAC 角色、管理员登录登出、用户管理与操作审计                |
| 电影/影人查询 API  | 系统实现 -- 数据查询模块           | MySQL + Neo4j 双数据源策略，各自负责的查询类型               |
| 图谱探索 API       | 系统实现 -- 知识图谱应用           | Cypher 图模式匹配、多跳关系查询、最短路径算法                |
| PPR 推荐算法       | 推荐算法研究 -- 基于图结构的推荐   | 随机游走模型、衰减因子分析、时间复杂度                       |
| Content-Based 推荐 | 推荐算法研究 -- 基于内容的推荐     | 特征工程、向量化表示、余弦相似度                             |
| 协同过滤推荐       | 推荐算法研究 -- 基于行为协同过滤   | 用户-电影交互矩阵、ItemCF/UserCF、相似度计算                 |
| 个性化推荐         | 推荐算法研究 -- 基于用户画像的推荐 | 多种子 PPR、用户口味画像向量、偏好类型权重设计               |
| 混合推荐           | 推荐算法研究 -- 混合推荐策略       | PPR + Content + CF 融合、权重参数调优、对比实验              |
| 统计 API           | 系统验证 -- 数据分析               | 数据分布可视化，验证图谱的完整性                             |

---

## 10. 性能目标

统一使用 `P50 / P95` 口径验收，避免“全接口 <500ms”这类不现实目标。

| 接口类型 | P50 目标 | P95 目标 | 超时阈值 | 备注 |
| -------- | -------- | -------- | -------- | ---- |
| 用户登录/注册 | <120ms | <300ms | 1s | 含 bcrypt 校验 |
| 管理员登录/用户管理 | <150ms | <400ms | 1s | 含 RBAC 校验与审计落库 |
| 电影/影人搜索 | <150ms | <400ms | 1s | MySQL 索引 + 分页 |
| 电影/影人详情 | <120ms | <350ms | 1s | Neo4j 点查 |
| 图谱探索（1跳） | <300ms | <800ms | 1.5s | 带 `node_limit/edge_limit` |
| 图谱探索（2跳） | <800ms | <1800ms | 3s | 默认关闭，仅受控启用 |
| 推荐（movie/person） | <700ms | <2000ms | 3s | PPR/Content/CF 召回后重排，允许缓存 |
| 个性化推荐（personal） | <1000ms | <3000ms | 4s | 偏好画像 + 多种子 |

性能压测建议：

- 并发基线：`50 RPS`（查询）+ `10 RPS`（推荐）持续 5 分钟
- 稳定性目标：错误率 `< 0.5%`，无大规模超时
- 热门接口命中缓存后，P95 至少下降 `30%`

---

## 11. 工程保障与风险控制（新增）

上线前建议补齐以下工程项，避免后期返工：

- **数据库迁移**：MySQL 使用 Alembic 管理 DDL，禁止手工改表漂移
- **错误码规范**：统一 `code/message/request_id` 响应格式
- **可观测性**：结构化日志 + 慢查询日志 + 基础指标（QPS/RT/错误率）
- **限流与降级**：图谱与推荐接口增加限流；超时时返回降级结果
- **契约测试**：前后端基于 OpenAPI 做接口契约校验

---

## 12. 推荐效果评估（新增）

推荐模块除了延迟，还需要质量验收：

- **离线指标**：`Precision@10`、`Recall@10`、`NDCG@10`、覆盖率、多样性
- **切分方式**：按用户或时间切分训练/验证集，避免数据泄漏
- **在线指标（可选）**：点击率（CTR）、收藏率、停留时长
- **版本对比**：固定评估集，对比 `ppr/content/cf/hybrid` 四种算法并记录权重配置
