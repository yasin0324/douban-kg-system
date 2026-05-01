# db-spiders

Douban KG System 的数据采集子系统，当前核心实现为 Playwright 电影与影人采集脚本。旧版 Scrapy 规划不再代表当前实现。

## 目录结构

```text
db-spiders/
├── crawl_movie.py              # 电影详情采集入口
├── crawl_person.py             # 影人详情采集入口
├── discover_movies.py          # 电影条目发现
├── rebuild_pid.py              # 从电影演职员字段提取影人 ID
├── recrawl_incomplete_movies.py
├── recrawl_incomplete_persons.py
├── proxy_manager.py            # 代理池管理
├── db_spiders/
│   ├── database.py             # MySQL 连接
│   ├── util.py                 # 工具函数
│   └── validator.py            # 字段校验
├── scripts/                    # 监控和维护脚本
└── sql/                        # MySQL 补丁 SQL
```

## 快速开始

采集电影数据：

```bash
python crawl_movie.py --headless --workers 2
python crawl_movie.py --test --visible
```

从电影字段提取影人 ID：

```bash
python rebuild_pid.py
```

采集影人数据：

```bash
python crawl_person.py --direct --direct-workers 2
```

检查进度：

```bash
python scripts/check_db.py
```

## 论文取材边界

可写 Playwright、任务锁、断点恢复、失败标记、代理/直连模式和缺失字段补采。不要写当前系统仍以 Scrapy 为核心框架，也不要写已实现评论全文采集、HanLP 实体抽取或生产级采集吞吐指标。
