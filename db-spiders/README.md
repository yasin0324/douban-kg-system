# db-spiders 项目文档

## 简介

Douban KG System 的数据采集子系统，基于 Playwright 实现，能够突破豆瓣反爬机制。

## 目录结构

```
db-spiders/
├── crawl_movie.py          # 🚀 核心爬虫 (入口)
├── rebuild_pid.py          # 🔄 ETL工具 (人物ID提取)
│
├── db_spiders/             # 公共库
│   ├── database.py         # 数据库连接
│   ├── util.py             # 工具函数
│   └── validator.py        # 数据验证
│
├── scripts/                # 维护脚本
│   └── check_db.py         # 数据库检查
│
├── sql/                    # SQL补丁
├── config/                 # 配置文件
├── logs/                   # 运行日志
└── docs/                   # 说明文档
```

## 快速开始

### 1. 采集电影数据

使用 `crawl_movie.py` (原 playwright_crawler_concurrent.py)

```bash
# 推荐：无头模式 + 2个并发
python crawl_movie.py --headless --workers 2

# 测试模式
python crawl_movie.py --test --visible
```

### 2. 提取人物ID

采集完成后，运行 ETL 工具提取人物信息：

```bash
python rebuild_pid.py
```

### 3. 检查进度

```bash
python scripts/check_db.py
```
