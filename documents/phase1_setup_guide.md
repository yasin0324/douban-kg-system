# 第一阶段：环境搭建与数据爬虫开发详细指南

> 本文档提供完整的环境搭建和数据爬虫开发操作步骤
> 目标：2 周内完成环境搭建，采集 1000+部豆瓣电影数据

---

## 目录

-   [一、项目整体架构](#一项目整体架构)
-   [二、开发环境准备](#二开发环境准备)
-   [三、Python 环境与 uv 配置](#三python环境与uv配置)
-   [四、配置项目依赖](#四配置项目依赖)
-   [五、Neo4j 本地安装](#五neo4j本地安装)
-   [六、前端环境配置](#六前端环境配置)
-   [七、Scrapy 爬虫开发](#七scrapy爬虫开发)
-   [八、数据采集与验证](#八数据采集与验证)
-   [九、常见问题排查](#九常见问题排查)
-   [十、后续任务清单](#十后续任务清单)

---

---

## 一、项目整体架构

### 1.1 项目目录结构

```
douban-kg-system/
├── pyproject.toml              # 根项目配置（workspace管理）
├── .python-version             # Python版本锁定
├── .gitignore                   # Git忽略文件
├── README.md
├── documents/                   # 文档目录
│   ├── phase1_setup_guide.md   # 本文档
│   ├── development_plan.md
│   └── design.md
├── db-spiders/                  # 爬虫模块
│   ├── pyproject.toml         # 爬虫依赖配置
│   ├── .python-version
│   ├── README.md
│   ├── main.py
│   ├── scrapy.cfg
│   ├── items.py               # 数据模型定义
│   ├── middlewares.py         # 中间件（反爬）
│   ├── pipelines.py           # 数据处理管道
│   ├── settings.py            # Scrapy配置
│   └── spiders/               # 爬虫目录
│       ├── __init__.py
│       ├── douban_chart.py   # 电影排行榜爬虫
│       └── douban_detail.py  # 电影详情爬虫
├── db-backend/                  # 后端模块
│   ├── pyproject.toml         # 后端依赖配置
│   └── main.py                # FastAPI入口
├── db-frontend/                 # 前端模块
│   ├── package.json           # 前端依赖
│   └── src/
├── data/                        # 数据目录
│   ├── raw/                    # 原始爬取数据
│   └── processed/              # 清洗后数据
└── scripts/                     # 脚本工具
    └── validate_data.py       # 数据验证脚本
```

---

## 二、开发环境准备

### 2.1 必装软件清单

#### Windows 系统准备

1. **Python 3.11+**

    - 下载地址：https://www.python.org/downloads/
    - 选择 Python 3.11.x 或 3.12.x
    - 安装时勾选 "Add Python to PATH"

2. **Git**

    - 下载地址：https://git-scm.com/download/win
    - 安装后运行：`git --version` 确认

3. **Node.js 18+**

    - 下载地址：https://nodejs.org/
    - 选择 LTS 版本（推荐 18.x 或 20.x）
    - 安装后运行：`node --version` 和 `npm --version` 确认

4. **Neo4j Desktop**（用于 Neo4j 本地管理）

    - 下载地址：https://neo4j.com/download/
    - 选择 Neo4j Desktop 版本

5. **Visual Studio Code**（推荐编辑器）
    - 下载地址：https://code.visualstudio.com/
    - 推荐插件：
        - Python
        - Pylance
        - Vue Language Features (Volar)
        - GitLens

### 2.2 环境检查命令

在项目根目录打开 PowerShell 或 CMD，依次运行以下命令验证环境：

```bash
# 检查 Python 版本
python --version
# 期望输出：Python 3.11.x 或 3.12.x

# 检查 Git 版本
git --version
# 期望输出：git version 2.x.x

# 检查 Node.js 版本
node --version
# 期望输出：v18.x.x 或 v20.x.x

# 检查 npm 版本
npm --version
# 期望输出：10.x.x
```

---

## 三、Python 环境与 uv 配置

### 3.1 安装 uv（Python 包管理工具）

uv 是一个极快的 Python 包管理工具，替代 pip、pip-tools、virtualenv 等工具。

#### Windows (PowerShell)

```powershell
# 方法1：使用 PowerShell 安装
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 方法2：如果上面不行，使用 pip 安装
pip install uv
```

#### 验证安装

```bash
uv --version
# 期望输出：uv 0.x.x
```

### 3.2 创建 Python 虚拟环境

在项目根目录执行：

```bash
# 初始化 uv 项目（如果还没有）
uv init

# 同步依赖，创建虚拟环境
uv sync
```

### 3.3 锁定 Python 版本

在项目根目录创建 `.python-version` 文件：

```bash
3.11
```

---

## 四、配置项目依赖

### 4.1 配置根项目 pyproject.toml

在项目根目录 `pyproject.toml` 中添加以下内容：

```toml
[project]
name = "douban-kg-system"
version = "0.1.0"
description = "Douban movie knowledge graph system"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

# uv workspace 配置
[tool.uv]
package = false

[tool.uv.workspace]
members = ["db-spiders", "db-backend"]

# 开发依赖
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.3.0",
    "mypy>=1.8.0",
    "pre-commit>=3.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# Ruff 配置
[tool.ruff]
line-length = 88 # 保持与 Black 一致的行宽

[tool.ruff.lint]
# 启用 Pyflakes (F), Pycodestyle (E, W), Isort (I), Naming (N)
select = ["E", "F", "I", "N", "W"]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"

# MyPy 配置
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
```

### 4.2 配置 db-spiders/pyproject.toml

在 `db-spiders/pyproject.toml` 中添加以下内容：

```toml
[project]
name = "db-spiders"
version = "0.1.0"
description = "Douban movie spider module using Scrapy"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "scrapy>=2.11.0",
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.1.0",
    "fake-useragent>=1.4.0",
    "pandas>=2.2.0",
    "numpy>=1.26.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-scrapy>=0.0.1",
    "scrapy-splash>=0.9.0",
]

[project.scripts]
scrapy = "scrapy.cmdline:execute"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 4.3 配置 db-backend/pyproject.toml

在 `db-backend/pyproject.toml` 中添加以下内容：

```toml
[project]
name = "db-backend"
version = "0.1.0"
description = "FastAPI backend for douban knowledge graph"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "neo4j>=5.14.0",
    "python-dotenv>=1.0.0",
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "jieba>=0.42.1",
    "hanlp>=2.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",
    "black>=23.12.0",
    "ruff>=0.1.9",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 4.4 同步所有依赖

在项目根目录执行：

```bash
# 同步所有项目依赖
uv sync

# 验证安装
uv run python --version
uv run scrapy --version
```

---

## 五、Neo4j 本地安装

### 5.1 安装 Neo4j Desktop

1. 下载并安装 Neo4j Desktop
2. 创建一个新项目，命名为 "douban-kg"
3. 创建数据库实例：

    - 点击 "Add Database"
    - 命名：douban-kg
    - 版本：选择 5.x（推荐 5.15.x）
    - 密码：设置一个密码（例如：douban123）
    - 点击 "Create"

4. 启动数据库：
    - 点击 "Start" 按钮启动数据库
    - 等待状态变为 "Active"

### 5.2 测试 Neo4j 连接

在 Neo4j Desktop 中：

1. 点击 "Open" 打开 Neo4j Browser
2. 输入密码（设置的密码）
3. 测试查询：

```cypher
// 查看数据库信息
CALL dbms.components() YIELD name, versions, edition
RETURN name, versions, edition;

// 查看节点数量
MATCH (n) RETURN count(n) AS node_count;
```

### 5.3 配置 Neo4j 连接信息

创建 `db-backend/.env` 文件：

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=douban123
```

---

## 六、前端环境配置

### 6.1 初始化前端项目

在 `db-frontend` 目录下执行：

```bash
cd db-frontend

# 如果目录为空，初始化 Vue3 项目
npm create vue@latest .

# 或者使用 Vite 直接创建
npm init vite@latest . -- --template vue
```

按照提示选择：

-   TypeScript? No
-   JSX? No
-   Vue Router? Yes
-   Pinia? Yes
-   Vitest? No
-   Playwright? No
-   ESLint? Yes

### 6.2 安装依赖

```bash
cd db-frontend

# 安装依赖
npm install

# 安装额外需要的依赖
npm install axios element-plus echarts vue-echarts @element-plus/icons-vue
```

### 6.3 配置前端

修改 `db-frontend/vite.config.js`：

```javascript
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
    plugins: [vue()],
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
});
```

### 6.4 测试前端启动

```bash
cd db-frontend
npm run dev
```

访问 http://localhost:5173，应该能看到 Vue 默认欢迎页面。

---

## 七、Scrapy 爬虫开发

### 7.1 创建 Scrapy 项目结构

#### 创建目录

```bash
# 确保在项目根目录
cd db-spiders

# 创建必要的目录
mkdir -p spiders data/raw data/processed
```

#### 创建 Scrapy 配置文件

**创建 `db-spiders/scrapy.cfg`：**

```ini
[settings]
default = db_spiders.settings

[deploy]
project = db_spiders
```

**创建 `db-spiders/__init__.py`：**

```python
# 空文件
```

### 7.2 定义数据模型

**创建 `db-spiders/items.py`：**

```python
"""定义豆瓣电影数据项模型"""
import scrapy


class DoubanMovieItem(scrapy.Item):
    """电影数据项"""

    # 基础信息
    movie_id = scrapy.Field()          # 电影ID
    title = scrapy.Field()             # 电影标题
    original_title = scrapy.Field()    # 原标题
    year = scrapy.Field()              # 上映年份

    # 评分信息
    rating = scrapy.Field()            # 评分
    rating_count = scrapy.Field()     # 评分人数

    # 电影详情
    directors = scrapy.Field()         # 导演列表
    writers = scrapy.Field()           # 编剧列表
    actors = scrapy.Field()            # 演员列表
    genres = scrapy.Field()            # 类型列表

    # 其他信息
    languages = scrapy.Field()         # 语言
    countries = scrapy.Field()         # 制片国家
    release_date = scrapy.Field()      # 上映日期
    duration = scrapy.Field()          # 时长
    summary = scrapy.Field()           # 简介

    # 元数据
    url = scrapy.Field()               # 详情页URL
    image_url = scrapy.Field()         # 封面图片URL
    crawled_at = scrapy.Field()        # 爬取时间
```

### 7.3 配置 Scrapy 设置

**创建 `db-spiders/settings.py`：**

```python
"""Scrapy 爬虫配置"""

import os

# 项目名称
BOT_NAME = "db_spiders"

SPIDER_MODULES = ["db_spiders.spiders"]
NEWSPIDER_MODULE = "db_spiders.spiders"

# 遵守 robots.txt 规则（设置为 False，因为豆瓣没有限制）
ROBOTSTXT_OBEY = False

# 下载延迟（重要：防止被反爬）
DOWNLOAD_DELAY = 2

# 并发设置
CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8

# 下载超时
DOWNLOAD_TIMEOUT = 30

# User-Agent 配置
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# 中间件配置
DOWNLOADER_MIDDLEWARES = {
    # 关闭默认 User-Agent 中间件
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    # 启用自定义 User-Agent 轮换中间件
    "db_spiders.middlewares.RandomUserAgentMiddleware": 400,
}

# 数据管道
ITEM_PIPELINES = {
    # JSON 存储管道
    "db_spiders.pipelines.JsonWriterPipeline": 300,
}

# 日志配置
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

# 重试设置
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# 数据存储目录
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")

# 启用 cookies
COOKIES_ENABLED = True

# 禁用 Telnet Console（Windows 可能不支持）
TELNETCONSOLE_ENABLED = False
```

### 7.4 创建反爬中间件

**创建 `db-spiders/middlewares.py`：**

```python
"""Scrapy 中间件"""
from fake_useragent import UserAgent
import random
import time


class RandomUserAgentMiddleware:
    """随机 User-Agent 中间件

    使用 fake-useragent 库轮换 User-Agent，模拟真实浏览器访问
    """

    def __init__(self):
        self.ua = UserAgent()
        # 备用 User-Agent 列表
        self.fallback_ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]

    def process_request(self, request, spider):
        """处理每个请求，设置随机 User-Agent"""
        try:
            request.headers["User-Agent"] = self.ua.random
        except:
            # 如果 fake-useragent 失败，使用备用列表
            request.headers["User-Agent"] = random.choice(self.fallback_ua_list)


class RateLimitMiddleware:
    """请求限速中间件

    确保请求间隔满足 DOWNLOAD_DELAY 设置
    """

    def __init__(self):
        self.last_request_time = 0

    def process_request(self, request, spider):
        """处理请求，添加延迟"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        # 如果距离上次请求时间小于设定的延迟，则等待
        download_delay = spider.settings.get("DOWNLOAD_DELAY", 2)
        if time_since_last_request < download_delay:
            sleep_time = download_delay - time_since_last_request
            time.sleep(sleep_time)

        self.last_request_time = time.time()
```

### 7.5 创建数据管道

**创建 `db-spiders/pipelines.py`：**

```python
"""Scrapy 数据管道"""
import json
import os
from datetime import datetime
from urllib.parse import urlparse


class JsonWriterPipeline:
    """JSON 文件存储管道

    将爬取的数据保存为 JSON 格式文件
    """

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.file = None
        self.items = []
        self.filename = None

    @classmethod
    def from_crawler(cls, crawler):
        """从 Scrapy 配置中获取数据目录"""
        data_dir = crawler.settings.get("DATA_DIR", "data/raw")
        return cls(data_dir)

    def open_spider(self, spider):
        """爬虫启动时调用"""
        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)

        # 生成文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = os.path.join(self.data_dir, f"movies_{spider.name}_{timestamp}.json")

        # 打开文件
        self.file = open(self.filename, "w", encoding="utf-8")
        spider.logger.info(f"数据将保存到: {self.filename}")

    def close_spider(self, spider):
        """爬虫结束时调用"""
        # 写入 JSON
        json.dump(self.items, self.file, ensure_ascii=False, indent=2)
        self.file.close()

        spider.logger.info(f"已保存 {len(self.items)} 条数据到 {self.filename}")
        spider.logger.info(f"数据文件路径: {os.path.abspath(self.filename)}")

    def process_item(self, item, spider):
        """处理每个数据项"""
        # 将 Item 转换为字典
        item_dict = dict(item)

        # 添加爬取时间戳
        if "crawled_at" not in item_dict:
            item_dict["crawled_at"] = datetime.now().isoformat()

        self.items.append(item_dict)
        return item


class DataValidationPipeline:
    """数据验证管道

    验证数据的完整性和正确性
    """

    def process_item(self, item, spider):
        """验证数据项"""
        # 必填字段检查
        required_fields = ["movie_id", "title"]
        for field in required_fields:
            if field not in item or not item[field]:
                spider.logger.warning(f"缺少必填字段 {field}: {item}")

        # 评分范围检查
        if "rating" in item and item["rating"]:
            try:
                rating = float(item["rating"])
                if not (0 <= rating <= 10):
                    spider.logger.warning(f"评分超出范围 {rating}: {item.get('title')}")
            except ValueError:
                spider.logger.warning(f"评分格式错误: {item.get('rating')}")

        return item
```

### 7.6 创建豆瓣排行榜爬虫

**创建 `db-spiders/spiders/__init__.py`：**

```python
# 爬虫包初始化
```

**创建 `db-spiders/spiders/douban_chart.py`：**

```python
"""豆瓣电影排行榜爬虫"""
import scrapy
from db_spiders.items import DoubanMovieItem


class DoubanChartSpider(scrapy.Spider):
    """豆瓣电影排行榜爬虫

    爬取豆瓣电影排行榜页面：
    - 一周热门口碑榜: https://movie.douban.com/chart
    - 热门电影榜单: https://movie.douban.com/chart
    """

    name = "douban_chart"
    allowed_domains = ["douban.com", "movie.douban.com"]

    # 起始URL（豆瓣电影排行榜）
    start_urls = [
        "https://movie.douban.com/chart",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 3,  # 排行榜页面延迟可以稍长
    }

    def parse(self, response):
        """解析排行榜页面，提取电影列表"""

        # 豆瓣排行榜页面结构分析
        # 电影信息在 <tr> 标签中，class="item"
        movie_items = response.css('tr.item')

        self.logger.info(f"找到 {len(movie_items)} 部电影")

        for item in movie_items:
            # 提取电影链接
            movie_url = item.css('a.nbg::attr(href)').get()
            if not movie_url:
                continue

            # 提取电影ID（从URL中提取，例如：https://movie.douban.com/subject/1292052/）
            movie_id = movie_url.split("/")[-2]

            # 提取电影标题
            title = item.css('div.pl2 a::text').get()
            if title:
                title = title.strip()

            # 提取评分
            rating = item.css('span.rating_nums::text').get()
            if rating:
                rating = rating.strip()

            # 提取评分人数
            rating_count = item.css('span.rating_nums + span::text').get()
            if rating_count:
                rating_count = rating_count.strip().replace("人评价", "")

            # 提取电影信息（导演、演员、类型等）
            info = item.css('div.pl::text').get()
            directors = []
            actors = []
            genres = []
            year = ""

            if info:
                info = info.strip()
                # 信息格式示例："导演: 张艺谋 / 主演: 章子怡 / 周润发 / 类型: 剧情片 / 动作片 / 地区: 中国大陆 / 年份: 2024"
                self._parse_movie_info(info, directors, actors, genres, year)

            # 提取封面图片
            image_url = item.css('a.nbg img::attr(src)').get()

            # 创建数据项
            movie_item = DoubanMovieItem()
            movie_item["movie_id"] = movie_id
            movie_item["title"] = title
            movie_item["rating"] = rating
            movie_item["rating_count"] = rating_count
            movie_item["directors"] = directors
            movie_item["actors"] = actors
            movie_item["genres"] = genres
            movie_item["year"] = year
            movie_item["url"] = movie_url
            movie_item["image_url"] = image_url

            # 输出日志
            self.logger.info(f"发现电影: {title} (ID: {movie_id}, 评分: {rating})")

            # 请求详情页获取更完整的信息
            yield scrapy.Request(
                url=movie_url,
                callback=self.parse_movie_detail,
                meta={"item": movie_item}
            )

    def parse_movie_detail(self, response):
        """解析电影详情页，补充详细信息"""

        # 获取基础数据项
        movie_item = response.meta["item"]

        # 提取原标题
        original_title = response.css('span[property="v:itemreviewed"]::text').get()
        if original_title:
            movie_item["original_title"] = original_title.strip()

        # 提取详细信息（从 #info 区域）
        info_div = response.css('#info')

        # 导演列表
        directors = info_div.css('a[rel="v:directedBy"]::text').getall()
        if directors:
            movie_item["directors"] = [d.strip() for d in directors]

        # 编剧列表
        writers = info_div.css('span::text').re_all(r'编剧[:：]\s*(.+?)\s*/')
        if not writers:
            writers = info_div.css('a[rel="v:writer"]::text').getall()
        movie_item["writers"] = writers

        # 主演列表
        actors = info_div.css('a[rel="v:starring"]::text').getall()
        if actors:
            movie_item["actors"] = [a.strip() for a in actors]

        # 类型列表
        genres = info_div.css('span[property="v:genre"]::text').getall()
        if genres:
            movie_item["genres"] = [g.strip() for g in genres]

        # 上映日期
        release_date = response.css('span[property="v:initialReleaseDate"]::text').get()
        if release_date:
            movie_item["release_date"] = release_date.strip()

        # 年份
        year = response.css('span.year::text').get()
        if year:
            year = year.strip("()").strip()
            movie_item["year"] = year

        # 时长
        duration = response.css('span[property="v:runtime"]::text').get()
        if duration:
            movie_item["duration"] = duration.strip()

        # 语言
        languages = info_div.css('::text').re_all(r'语言[:：]\s*(.+?)\s*/')
        movie_item["languages"] = languages

        # 制片国家
        countries = info_div.css('::text').re_all(r'制片国家/地区[:：]\s*(.+?)\s*/')
        movie_item["countries"] = countries

        # 简介
        summary = response.css('span[property="v:summary"]::text').get()
        if summary:
            movie_item["summary"] = summary.strip()
        else:
            # 尝试其他选择器
            summary = response.css('div#link-report div.all::text').get()
            if summary:
                movie_item["summary"] = summary.strip()

        # 返回完整的数据项
        yield movie_item

    def _parse_movie_info(self, info, directors, actors, genres, year):
        """辅助方法：解析电影信息字符串"""
        # 简单的字符串解析，可以根据实际情况调整
        info = info.replace("导演:", "导演:")
        info = info.replace("主演:", "主演:")
        info = info.replace("类型:", "类型:")

        parts = info.split("/")

        for part in parts:
            part = part.strip()
            if "导演:" in part:
                dir_part = part.replace("导演:", "").strip()
                if dir_part:
                    directors = dir_part.split("/")
            elif "主演:" in part:
                actor_part = part.replace("主演:", "").strip()
                if actor_part:
                    actors = actor_part.split("/")
            elif "类型:" in part:
                genre_part = part.replace("类型:", "").strip()
                if genre_part:
                    genres = genre_part.split("/")
            elif "年份:" in part:
                year = part.replace("年份:", "").strip()
```

### 7.7 创建豆瓣详情页爬虫（按标签爬取）

**创建 `db-spiders/spiders/douban_detail.py`：**

```python
"""豆瓣电影详情页爬虫（按标签爬取）"""
import scrapy
from db_spiders.items import DoubanMovieItem


class DoubanDetailSpider(scrapy.Spider):
    """豆瓣电影详情页爬虫

    按标签分类爬取电影：
    - 标签列表：剧情、喜剧、动作、爱情、科幻、悬疑、恐怖、动画等
    - 每个标签爬取多页
    """

    name = "douban_detail"
    allowed_domains = ["douban.com", "movie.douban.com"]

    # 标签列表（按优先级排序）
    tags = ["剧情", "喜剧", "动作", "爱情", "科幻", "悬疑", "恐怖", "动画"]

    # 每个标签爬取的页数
    pages_per_tag = 5

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS": 8,
    }

    def start_requests(self):
        """生成起始请求"""
        for tag in self.tags:
            for page in range(self.pages_per_tag):
                # 构造标签页URL
                # 格式：https://movie.douban.com/tag/#/?sort=S&range=0,10&tags=剧情&start=20
                start = page * 20
                url = f"https://movie.douban.com/tag/#/?sort=S&range=0,10&tags={tag}&start={start}"

                self.logger.info(f"爬取标签: {tag}, 页码: {page + 1}")

                yield scrapy.Request(
                    url=url,
                    callback=self.parse_tag_page,
                    meta={"tag": tag, "page": page + 1}
                )

    def parse_tag_page(self, response):
        """解析标签页面，提取电影列表"""

        # 豆瓣标签页需要使用 JavaScript 渲染，普通爬虫无法直接获取
        # 这里使用豆瓣的标签搜索接口
        # 格式：https://movie.douban.com/j/new_search_subjects?sort=U&range=0,10&tags=剧情&start=0

        tag = response.meta["tag"]
        page = response.meta["page"]
        start = (page - 1) * 20

        # 使用 JSON 接口
        api_url = f"https://movie.douban.com/j/new_search_subjects?sort=U&range=0,10&tags={tag}&start={start}"

        self.logger.info(f"请求标签API: {tag}, 页码: {page}")

        yield scrapy.Request(
            url=api_url,
            callback=self.parse_tag_api,
            meta={"tag": tag, "page": page}
        )

    def parse_tag_api(self, response):
        """解析标签API返回的JSON数据"""

        import json

        try:
            data = json.loads(response.text)
            movies = data.get("data", [])

            self.logger.info(f"标签 {response.meta['tag']} 第 {response.meta['page']} 页找到 {len(movies)} 部电影")

            for movie in movies:
                movie_id = movie.get("id")
                title = movie.get("title")
                url = movie.get("url")
                rate = movie.get("rate")
                cover = movie.get("cover")

                if not url:
                    continue

                # 创建基础数据项
                movie_item = DoubanMovieItem()
                movie_item["movie_id"] = str(movie_id)
                movie_item["title"] = title
                movie_item["rating"] = rate
                movie_item["url"] = url
                movie_item["image_url"] = cover

                # 请求详情页
                yield scrapy.Request(
                    url=url,
                    callback=self.parse_movie_detail,
                    meta={"item": movie_item}
                )

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {e}")

    def parse_movie_detail(self, response):
        """解析电影详情页"""

        movie_item = response.meta["item"]

        # 这里复用 douban_chart.py 中的 parse_movie_detail 逻辑
        # 为简化，这里只提取基础信息

        # 提取导演
        directors = response.css('a[rel="v:directedBy"]::text').getall()
        if directors:
            movie_item["directors"] = [d.strip() for d in directors]

        # 提取主演
        actors = response.css('a[rel="v:starring"]::text').getall()
        if actors:
            movie_item["actors"] = [a.strip() for a in actors]

        # 提取类型
        genres = response.css('span[property="v:genre"]::text').getall()
        if genres:
            movie_item["genres"] = [g.strip() for g in genres]

        # 提取年份
        year = response.css('span.year::text').get()
        if year:
            movie_item["year"] = year.strip("()").strip()

        # 提取评分人数
        rating_count = response.css('a.rating_people span::text').get()
        if rating_count:
            movie_item["rating_count"] = rating_count.strip()

        # 提取简介
        summary = response.css('span[property="v:summary"]::text').get()
        if summary:
            movie_item["summary"] = summary.strip()

        yield movie_item
```

### 7.8 创建运行入口

**创建 `db-spiders/main.py`：**

```python
"""爬虫运行入口"""
import sys
from scrapy.cmdline import execute


def main():
    """运行爬虫的主函数"""

    # 可以在这里添加命令行参数处理
    spider_name = sys.argv[1] if len(sys.argv) > 1 else "douban_chart"

    # 运行爬虫
    execute(["scrapy", "crawl", spider_name])


if __name__ == "__main__":
    main()
```

---

## 八、数据采集与验证

### 8.1 运行爬虫

#### 运行豆瓣排行榜爬虫

```bash
# 方法1：使用 uv run
uv run scrapy crawl douban_chart

# 方法2：使用 main.py
uv run python db-spiders/main.py douban_chart

# 方法3：激活环境后直接运行
uv shell
scrapy crawl douban_chart
```

#### 运行标签爬虫（采集更多数据）

```bash
# 爬取按标签分类的电影
uv run scrapy crawl douban_detail
```

### 8.2 查看爬虫日志

爬虫运行时会输出日志，关键信息：

```
2025-01-16 23:00:00 [db_spiders.spiders.douban_chart] INFO: 找到 20 部电影
2025-01-16 23:00:05 [db_spiders.spiders.douban_chart] INFO: 发现电影: 肖申克的救赎 (ID: 1292052, 评分: 9.7)
2025-01-16 23:00:07 [db_spiders.pipelines] INFO: 数据将保存到: data/raw/movies_douban_chart_20250116_230000.json
2025-01-16 23:05:00 [db_spiders.pipelines] INFO: 已保存 20 条数据到 data/raw/movies_douban_chart_20250116_230000.json
```

### 8.3 创建数据验证脚本

**创建 `scripts/validate_data.py`：**

```python
"""数据验证脚本"""
import json
import os
import sys
from pathlib import Path


def validate_movie_data(json_file):
    """验证电影数据质量

    Args:
        json_file: JSON 文件路径

    Returns:
        bool: 验证是否通过
    """
    # 读取数据
    with open(json_file, "r", encoding="utf-8") as f:
        movies = json.load(f)

    print("=" * 60)
    print(f"数据文件: {json_file}")
    print("=" * 60)

    # 基础统计
    print(f"\n【基础统计】")
    print(f"总电影数: {len(movies)}")

    if not movies:
        print("❌ 数据为空！")
        return False

    # 必填字段检查
    print(f"\n【必填字段检查】")
    required_fields = ["movie_id", "title"]

    field_completeness = {}
    for field in required_fields:
        count = sum(1 for m in movies if field in m and m[field])
        completeness = (count / len(movies)) * 100
        field_completeness[field] = completeness
        status = "✅" if completeness == 100 else "⚠️"
        print(f"{status} {field}: {count}/{len(movies)} ({completeness:.1f}%)")

    # 评分统计
    print(f"\n【评分统计】")
    ratings = [float(m.get("rating", 0)) for m in movies if m.get("rating")]
    if ratings:
        print(f"平均评分: {sum(ratings) / len(ratings):.2f}")
        print(f"最高评分: {max(ratings)}")
        print(f"最低评分: {min(ratings)}")

        # 评分分布
        high_rating = sum(1 for r in ratings if r >= 8.0)
        mid_rating = sum(1 for r in ratings if 6.0 <= r < 8.0)
        low_rating = sum(1 for r in ratings if r < 6.0)

        print(f"高分电影 (≥8.0): {high_rating} ({high_rating/len(ratings)*100:.1f}%)")
        print(f"中等电影 (6.0-7.9): {mid_rating} ({mid_rating/len(ratings)*100:.1f}%)")
        print(f"低分电影 (<6.0): {low_rating} ({low_rating/len(ratings)*100:.1f}%)")
    else:
        print("⚠️ 没有评分数据")

    # 字段完整性检查
    print(f"\n【字段完整性检查】")
    all_fields = [
        "title", "rating", "directors", "actors",
        "genres", "year", "summary"
    ]

    completeness_stats = {}
    for field in all_fields:
        count = sum(1 for m in movies if field in m and m[field])
        completeness = (count / len(movies)) * 100
        completeness_stats[field] = completeness
        status = "✅" if completeness >= 90 else "⚠️" if completeness >= 70 else "❌"
        print(f"{status} {field}: {count}/{len(movies)} ({completeness:.1f}%)")

    # 去重检查
    print(f"\n【去重检查】")
    movie_ids = [m.get("movie_id") for m in movies if m.get("movie_id")]
    unique_ids = len(set(movie_ids))
    duplicate_count = len(movie_ids) - unique_ids

    if duplicate_count == 0:
        print(f"✅ 无重复数据")
    else:
        print(f"⚠️ 发现 {duplicate_count} 条重复数据")

    # 异常值检查
    print(f"\n【异常值检查】")

    # 评分范围检查
    invalid_ratings = [m for m in movies if m.get("rating") and not (0 <= float(m["rating"]) <= 10)]
    if invalid_ratings:
        print(f"⚠️ 发现 {len(invalid_ratings)} 个异常评分")
    else:
        print(f"✅ 评分范围正常")

    # 年份检查
    years = [int(m["year"]) for m in movies if m.get("year") and m["year"].isdigit()]
    if years:
        print(f"年份范围: {min(years)} - {max(years)}")

        # 异常年份检查（假设合理的电影年份在 1900-2030 之间）
        invalid_years = [y for y in years if y < 1900 or y > 2030]
        if invalid_years:
            print(f"⚠️ 发现 {len(invalid_years)} 个异常年份")
        else:
            print(f"✅ 年份范围正常")

    # 数据质量评分
    print(f"\n【数据质量评分】")

    # 计算综合得分
    avg_completeness = sum(completeness_stats.values()) / len(completeness_stats)

    # 评分权重
    weights = {
        "completeness": 0.4,      # 字段完整性
        "uniqueness": 0.3,       # 唯一性
        "validity": 0.3,         # 有效性
    }

    # 计算各项得分
    completeness_score = avg_completeness
    uniqueness_score = (unique_ids / len(movie_ids)) * 100 if movie_ids else 0
    validity_score = 100 - (len(invalid_ratings) / len(movies)) * 100 if movies else 0

    # 加权总分
    total_score = (
        completeness_score * weights["completeness"] +
        uniqueness_score * weights["uniqueness"] +
        validity_score * weights["validity"]
    )

    print(f"字段完整性: {completeness_score:.1f}/100")
    print(f"数据唯一性: {uniqueness_score:.1f}/100")
    print(f"数据有效性: {validity_score:.1f}/100")
    print(f"综合得分: {total_score:.1f}/100")

    # 成功标准判断
    print(f"\n【成功标准判断】")
    print(f"目标数据量: ≥1000")
    print(f"当前数据量: {len(movies)}")
    print(f"目标完整率: ≥90%")
    print(f"当前完整率: {avg_completeness:.1f}%")

    success = (
        len(movies) >= 1000 and
        avg_completeness >= 90 and
        duplicate_count == 0
    )

    if success:
        print(f"\n✅ 数据验证通过！")
    else:
        print(f"\n❌ 数据验证未通过，请继续采集数据")
        if len(movies) < 1000:
            print(f"  - 还需要采集 {1000 - len(movies)} 部电影")
        if avg_completeness < 90:
            print(f"  - 数据完整率不足 {90 - avg_completeness:.1f}%")

    print("=" * 60)

    return success


def main():
    """主函数"""

    # 数据目录
    data_dir = Path(__file__).parent.parent / "data" / "raw"

    # 查找所有 JSON 文件
    json_files = list(data_dir.glob("*.json"))

    if not json_files:
        print(f"❌ 在 {data_dir} 目录下未找到 JSON 文件")
        sys.exit(1)

    print(f"找到 {len(json_files)} 个数据文件:\n")

    # 列出所有文件
    for i, file in enumerate(json_files, 1):
        file_size = file.stat().st_size / 1024  # KB
        print(f"{i}. {file.name} ({file_size:.1f} KB)")

    # 验证每个文件
    all_success = True
    for file in json_files:
        success = validate_movie_data(file)
        if not success:
            all_success = False
        print()

    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
```

### 8.4 运行数据验证

```bash
# 验证数据质量
uv run python scripts/validate_data.py
```

### 8.5 达到 1000 部数据的策略

如果爬取的数据量不足 1000 部，可以：

#### 策略 1：增加标签页的页数

修改 `db-spiders/spiders/douban_detail.py`：

```python
# 修改这行
pages_per_tag = 10  # 从5改为10
```

#### 策略 2：添加更多标签

修改 `db-spiders/spiders/douban_detail.py`：

```python
# 修改这行，添加更多标签
tags = [
    "剧情", "喜剧", "动作", "爱情", "科幻",
    "悬疑", "恐怖", "动画", "纪录片", "传记",
    "历史", "战争", "犯罪", "奇幻", "冒险"
]
```

#### 策略 3：多次运行爬虫

```bash
# 多次运行爬虫，采集不同时间的数据
uv run scrapy crawl douban_detail
uv run scrapy crawl douban_chart
```

---

## 九、常见问题排查

### 9.1 uv 相关问题

#### 问题：uv 命令找不到

**症状：**

```
uv: command not found
```

**解决方案：**

```bash
# Windows PowerShell - 重新安装
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip 安装
pip install uv
```

#### 问题：uv sync 失败

**症状：**

```
error: Failed to resolve dependencies
```

**解决方案：**

```bash
# 清理缓存
uv cache clean

# 重新同步
uv sync --reinstall
```

### 9.2 Scrapy 相关问题

#### 问题：爬虫被豆瓣反爬（403 Forbidden）

**症状：**

```
2025-01-16 23:00:00 [scrapy.downloadermiddlewares.redirect] DEBUG: Redirecting (403)
```

**解决方案：**

1. **增加延迟**：修改 `settings.py`

```python
DOWNLOAD_DELAY = 5  # 增加到5秒
```

2. **检查 User-Agent**：确保中间件正常工作

3. **添加 Cookies**：在 `settings.py` 中添加

```python
COOKIES_ENABLED = True
```

4. **使用代理**（如果需要）：

```python
# 在 request 中设置代理
yield scrapy.Request(url=url, meta={'proxy': 'http://your-proxy:port'})
```

#### 问题：fake-useragent 报错

**症状：**

```
fake_useragent.errors.FakeUserAgentError
```

**解决方案：**

修改 `middlewares.py`，增强容错能力：

```python
def process_request(self, request, spider):
    try:
        request.headers["User-Agent"] = self.ua.random
    except Exception as e:
        # 使用备用列表
        request.headers["User-Agent"] = random.choice(self.fallback_ua_list)
```

#### 问题：JSON 解析错误

**症状：**

```
json.JSONDecodeError: Expecting value: line 1 column 1
```

**解决方案：**

检查豆瓣 API 返回的数据格式是否正确，可能需要更新选择器。

---

### 9.3 Neo4j 相关问题

#### 问题：Neo4j 无法连接

**症状：**

```
neo4j.exceptions.ServiceUnavailable: Unable to connect to bolt://localhost:7687
```

**解决方案：**

1. **检查 Neo4j 是否启动**

    - 打开 Neo4j Desktop
    - 确保数据库状态为 "Active"

2. **检查端口**

    - 默认端口：7687 (Bolt), 7474 (HTTP), 7473 (HTTPS)
    - 确保端口没有被占用

3. **测试连接**
    - 打开 Neo4j Browser
    - 输入密码，确认可以连接

#### 问题：内存不足

**症状：**

```
Java heap space error
```

**解决方案：**

在 Neo4j Desktop 中：

1. 停止数据库
2. 点击 "Settings"
3. 找到 "dbms.memory.heap.initial_size" 和 "dbms.memory.heap.max_size"
4. 增加内存分配（例如：512m）

---

### 9.4 前端相关问题

#### 问题：npm install 失败

**症状：**

```
npm ERR! code ENOENT
```

**解决方案：**

```bash
# 清理 npm 缓存
npm cache clean --force

# 删除 node_modules 和 package-lock.json
rm -rf node_modules package-lock.json

# 重新安装
npm install
```

#### 问题：Vite 启动失败

**症状：**

```
Error: Cannot find module 'vite'
```

**解决方案：**

```bash
# 确保在 db-frontend 目录下
cd db-frontend

# 重新安装依赖
npm install

# 启动开发服务器
npm run dev
```

---

## 十、后续任务清单

### 10.1 第一周任务（本周完成）

-   [x] 创建项目目录结构
-   [x] 配置 pyproject.toml（根项目、db-spiders、db-backend）
-   [x] 安装 uv 并配置虚拟环境
-   [x] 安装 Scrapy 及相关依赖
-   [x] 创建 Scrapy 爬虫项目结构
-   [ ] 实现豆瓣排行榜爬虫（douban_chart）
-   [ ] 实现豆瓣标签爬虫（douban_detail）
-   [ ] 配置反爬中间件（User-Agent 轮换）
-   [ ] 实现数据存储管道（JSON）
-   [ ] 运行爬虫，采集初始数据
-   [ ] 验证数据质量（运行 validate_data.py）
-   [ ] 调整采集策略，确保达到 1000 部数据
-   [ ] 编写环境搭建文档

### 10.2 第二周任务（下周完成）

-   [ ] 优化爬虫性能（并发控制、请求延迟）
-   [ ] 实现断点续爬功能
-   [ ] 扩展数据采集范围（演员、导演详细信息）
-   [ ] 实现数据去重机制
-   [ ] 添加错误处理与重试逻辑
-   [ ] 数据验证与清洗（基础版本）
-   [ ] 确保最终数据量达到 1000+部
-   [ ] 数据完整率达到 90%以上
-   [ ] 编写数据采集报告

### 10.3 第三周任务（数据处理阶段）

-   [ ] 数据质量分析（缺失值、异常值、重复值）
-   [ ] 实现数据清洗 Pipeline（使用 Pandas）
-   [ ] 缺失值处理策略（删除、填充、标记）
-   [ ] 数据格式标准化（日期、评分、类型）
-   [ ] 异常值检测与处理
-   [ ] 数据质量评分系统
-   [ ] 清洗后数据验证

### 10.4 第四周任务（知识抽取阶段）

-   [ ] 设计知识图谱 Schema（节点类型、关系类型、属性）
-   [ ] 实现实体抽取（电影、导演、演员、类型）
-   [ ] 实现关系抽取（出演、导演、类型归属）
-   [ ] 实现属性抽取（评分、上映日期等）
-   [ ] 构建知识三元组（实体-关系-实体/属性）
-   [ ] 实体消歧（同名演员/导演区分）
-   [ ] 生成 Neo4j 导入文件

---

## 附录：常用命令速查

### uv 命令

```bash
# 安装 uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 初始化项目
uv init

# 同步依赖
uv sync

# 添加依赖
uv add <package-name> --package db-spiders

# 添加开发依赖
uv add <package-name> --dev

# 运行命令
uv run <command>

# 激活虚拟环境
uv shell

# 查看已安装的包
uv pip list
```

### Scrapy 命令

```bash
# 运行爬虫
scrapy crawl <spider_name>

# 列出所有爬虫
scrapy list

# 检查爬虫代码
scrapy check

# 测试 URL 解析
scrapy parse <url>

# 导出为 JSON
scrapy crawl <spider_name> -o output.json

# 导出为 CSV
scrapy crawl <spider_name> -o output.csv

# 导出为 XML
scrapy crawl <spider_name> -o output.xml
```

### Neo4j 命令

```bash
# 在 Neo4j Browser 中执行

# 查看所有节点
MATCH (n) RETURN n

# 统计节点数量
MATCH (n) RETURN count(n)

# 删除所有数据（危险操作！）
MATCH (n) DETACH DELETE n

# 创建索引
CREATE INDEX movie_title_idx FOR (m:Movie) ON (m.title)
```

### Git 命令

```bash
# 查看状态
git status

# 添加所有更改
git add .

# 提交更改
git commit -m "描述你的更改"

# 推送到远程仓库
git push

# 拉取最新代码
git pull

# 查看提交历史
git log

# 查看分支
git branch

# 创建新分支
git branch <branch-name>

# 切换分支
git checkout <branch-name>
```

---

## 文档总结

本文档提供了完整的第一阶段环境搭建和数据爬虫开发操作指南，包括：

1. ✅ 项目整体架构设计
2. ✅ 开发环境准备（Python、Git、Node.js、Neo4j）
3. ✅ uv 包管理工具配置
4. ✅ pyproject.toml 标准化配置
5. ✅ Neo4j 本地安装与配置
6. ✅ 前端 Vue3 环境配置（使用 npm）
7. ✅ Scrapy 爬虫完整开发流程
8. ✅ 反爬策略实现（User-Agent 轮换、请求延迟）
9. ✅ 数据采集与质量验证
10. ✅ 常见问题排查指南

**关键成功指标：**

-   📊 数据量：≥1000 部电影
-   📈 字段完整率：≥90%
-   ✨ 无重复数据
-   🎯 数据质量评分：≥90

**预计完成时间：** 2 周（第 1-2 周）

**下一步：** 按照本文档逐步执行，遇到问题参考"常见问题排查"章节。
