# db-backend — 豆瓣电影知识图谱后端

基于 **FastAPI** 的后端服务，提供电影/影人查询、知识图谱探索、用户认证与偏好管理等 API。

## 技术栈

- **Python 3.11+** / FastAPI / Pydantic
- **MySQL 8.x** — 电影、影人、用户数据存储
- **Neo4j 5.x**（Docker） — 知识图谱（电影-影人-类型关系）
- **JWT** — 用户认证（access + refresh token）

---

## 环境准备

### 前置依赖

| 工具         | 用途          | 安装方式                                                              |
| ------------ | ------------- | --------------------------------------------------------------------- |
| Python 3.11+ | 运行后端      | [python.org](https://www.python.org/)                                 |
| uv           | Python 包管理 | `curl -LsSf https://astral.sh/uv/install.sh \| sh`                    |
| Docker       | 运行 Neo4j    | [docker.com](https://www.docker.com/)                                 |
| MySQL 8.x    | 关系型数据库  | [mysql.com](https://dev.mysql.com/downloads/) 或 `brew install mysql` |

### 1. 启动 MySQL

**macOS 原生安装：**

```bash
# 如果通过 DMG 安装
sudo /usr/local/mysql/support-files/mysql.server start

# 如果通过 Homebrew 安装
brew services start mysql
```

**确认 MySQL 运行中：**

```bash
# 原生安装
/usr/local/mysql/bin/mysql -u root -p -e "SELECT 1"

# Homebrew
mysql -u root -p -e "SELECT 1"
```

### 2. 启动 Neo4j（Docker）

**首次创建容器：**

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -v neo4j_data:/data \
  -v neo4j_logs:/logs \
  -e NEO4J_AUTH=neo4j/douban2026 \
  -e NEO4J_server_memory_heap_initial__size=512m \
  -e NEO4J_server_memory_heap_max__size=1g \
  neo4j:5
```

**容器已存在，直接启动：**

```bash
docker start neo4j
```

**确认 Neo4j 运行中：**

```bash
docker ps | grep neo4j
# 或访问浏览器管理界面：http://localhost:7474
```

**停止 Neo4j：**

```bash
docker stop neo4j
```

### 3. 创建 MySQL 数据库与用户（仅首次）

```bash
# 登录 MySQL（根据安装方式选择路径）
/usr/local/mysql/bin/mysql -u root -p
# 或
mysql -u root -p
```

```sql
-- 创建数据库
CREATE DATABASE IF NOT EXISTS douban CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户并授权（密码按需修改）
CREATE USER IF NOT EXISTS 'douban_crawler'@'localhost' IDENTIFIED BY '1224guoyuanxin';
GRANT ALL PRIVILEGES ON douban.* TO 'douban_crawler'@'localhost';
FLUSH PRIVILEGES;
```

---

## 快速启动（日常开发）

> 以下步骤假设数据库已安装并配置过，日常开发只需执行这几步：

```bash
# 1. 启动 MySQL（如未运行）
sudo /usr/local/mysql/support-files/mysql.server start

# 2. 启动 Neo4j（如未运行）
docker start neo4j

# 3. 进入项目目录
cd db-backend

# 4. 启动后端（开发模式，自动重载）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功日志：

```
🚀 正在启动后端服务...
MySQL 连接池已初始化: localhost:3306/douban (pool_size=20)
Neo4j 驱动已初始化: bolt://localhost:7687
✅ 数据库连接已就绪
Uvicorn running on http://0.0.0.0:8000
```

验证：

- 健康检查：http://localhost:8000/health
- API 文档：http://localhost:8000/docs

---

## 全新机器部署指南

在另一台电脑上从零开始部署本项目，按以下步骤操作：

### Step 1：安装基础工具

```bash
# 安装 Homebrew（macOS）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python 3.11+
brew install python@3.11

# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Docker Desktop
# 下载安装：https://www.docker.com/products/docker-desktop/

# 安装 MySQL（二选一）
brew install mysql          # Homebrew 方式
# 或下载 DMG：https://dev.mysql.com/downloads/mysql/
```

### Step 2：克隆项目

```bash
git clone <your-repo-url>
cd douban-kg-system/db-backend
```

### Step 3：安装 Python 依赖

```bash
uv sync
```

### Step 4：启动并配置数据库

```bash
# 启动 MySQL
brew services start mysql  # 或 sudo /usr/local/mysql/support-files/mysql.server start

# 创建 Neo4j 容器
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -v neo4j_data:/data -v neo4j_logs:/logs \
  -e NEO4J_AUTH=neo4j/douban2026 \
  -e NEO4J_server_memory_heap_initial__size=512m \
  -e NEO4J_server_memory_heap_max__size=1g \
  neo4j:5
```

### Step 5：初始化 MySQL

```bash
# 创建数据库和用户（参考上方「创建 MySQL 数据库与用户」）

# 执行迁移脚本
mysql -u root -p douban < migrations/001_create_user_tables.sql
mysql -u root -p douban < migrations/002_create_admin_tables.sql
```

### Step 6：配置环境变量

编辑 `db-backend/.env`，根据实际情况修改：

```env
# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=douban_crawler
DB_PASS=your_mysql_password    # ← 改为实际密码
DB_NAME=douban
DB_POOL_SIZE=20

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=douban2026          # ← 与 docker run 中的密码一致

# JWT
JWT_SECRET=your-secret-key     # ← 生产环境务必修改
JWT_ACCESS_EXPIRE_MINUTES=30
JWT_REFRESH_EXPIRE_DAYS=7

# Cache
CACHE_TTL_SECONDS=300
```

### Step 7：导入数据

将爬虫采集的数据导入 MySQL 和 Neo4j（具体步骤参考 `crawler/` 目录），**或参考下方的「Neo4j 数据迁移」直接拷贝已有数据**。

### Step 8：启动服务

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Neo4j 数据迁移（将已有数据移至新电脑）

如果你在一台电脑上已经拥有了完整的图谱数据，**不需要**在另一台电脑上重新运行耗时的导入脚本。你可以直接打包并迁移数据：

### 在【旧电脑】上导出数据

1. 首先停止 Neo4j 容器：
    ```bash
    docker stop neo4j
    ```
2. 执行导出命令，将数据打包至当前目录下的 `neo4j_dump.dump` 文件：
    ```bash
    docker run --rm --name neo4j_export \
      -v neo4j_data:/data \
      -v $(pwd):/backups \
      neo4j:5 \
      neo4j-admin database dump neo4j --to-path=/backups
    ```
3. 当前目录下会生成一个 `neo4j.dump` 文件（约几百 MB 取决于数据量）。将此文件拷贝到【新电脑】上。
4. 重新启动旧电脑的 Neo4j：`docker start neo4j`。

### 在【新电脑】上导入数据

1. 确保新电脑上**已经停止**了 neo4j 容器：
    ```bash
    docker stop neo4j
    ```
2. 进入刚刚把 `neo4j.dump` 文件拷贝过去的目录。
3. 执行导入命令，将数据恢复到新机器的 volume 中：
    ```bash
    docker run --rm --name neo4j_import \
      -v neo4j_data:/data \
      -v $(pwd):/backups \
      neo4j:5 \
      neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
    ```
4. 启动新电脑的 Neo4j：
    ```bash
    docker start neo4j
    ```
    数据迁移完成！

---

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

## 常见问题

**Q: Neo4j 容器启动失败？**

```bash
# 查看日志
docker logs neo4j
# 常见原因：端口被占用、内存不足
```

**Q: MySQL 连接被拒绝？**

```bash
# 检查 MySQL 是否运行
sudo /usr/local/mysql/support-files/mysql.server status
# 检查用户权限
/usr/local/mysql/bin/mysql -u root -p -e "SHOW GRANTS FOR 'douban_crawler'@'localhost';"
```

**Q: `uv sync` 失败？**

```bash
# 确保 Python 版本 >= 3.11
python3 --version
# 清理缓存重试
uv cache clean && uv sync
```
