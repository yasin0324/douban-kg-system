# 豆瓣电影知识图谱 Schema 设计

**版本**: v2.0
**修订日期**: 2026-05-01
**依据**: `data_processing/etl_to_neo4j.py`、`data_processing/reports/data_quality_report.md`

本文档描述当前 ETL 实际导入 Neo4j 的节点、关系、属性和规模口径。旧版“10,000 部电影小型图谱预估”已废弃。

## 1. 节点定义

### 1.1 Movie

对应 MySQL `movies` 表。

| 属性 | 说明 |
|---|---|
| `mid` | 豆瓣条目 ID，唯一标识 |
| `title` | 电影名称 |
| `content_type` | 内容形式，来自 `movies.type` |
| `rating` | 豆瓣评分 |
| `votes` | 评分人数，来自 `douban_votes` |
| `release_date` | 上映日期 |
| `cover` | 封面 URL |
| `year` | 年份 |
| `regions` | 制片地区原始字段 |
| `languages` | 语言原始字段 |
| `runtime` | 片长 |
| `storyline` | 剧情简介 |
| `alias` | 别名 |
| `url` | 豆瓣详情页 URL |

### 1.2 Person

对应 MySQL `person` 表，导演和演员统一建模为 `Person`，通过关系区分职责。

| 属性 | 说明 |
|---|---|
| `pid` | 豆瓣影人 ID，唯一标识 |
| `name` | 姓名 |
| `sex` | 性别 |
| `name_en` | 英文名 |
| `name_zh` | 中文名 |
| `birth` | 出生日期 |
| `death` | 去世日期 |
| `birthplace` | 出生地 |
| `profession` | 职业 |
| `biography` | 简介 |

### 1.3 结构化维度节点

| Label | 主键 | 来源 |
|---|---|---|
| `Genre` | `name` | `movies.genres` |
| `Region` | `name` | `movies.regions` |
| `Language` | `name` | `movies.languages` |
| `ContentType` | `name` | `movies.type` |
| `YearBucket` | `name` | `movies.year` 派生 |

`YearBucket` 规则为 `before_1990`、`1990s`、`2000s`、`2010s`、`2020s_plus`。

## 2. 关系定义

| 关系 | 起点 | 终点 | 说明 |
|---|---|---|---|
| `DIRECTED` | `Person` | `Movie` | 影人执导电影 |
| `ACTED_IN` | `Person` | `Movie` | 影人参演电影，包含 `order` 属性 |
| `HAS_GENRE` | `Movie` | `Genre` | 电影所属类型 |
| `IN_REGION` | `Movie` | `Region` | 电影制片地区 |
| `IN_LANGUAGE` | `Movie` | `Language` | 电影语言 |
| `HAS_CONTENT_TYPE` | `Movie` | `ContentType` | 内容形式 |
| `IN_YEAR_BUCKET` | `Movie` | `YearBucket` | 年代分桶 |

## 3. 约束与索引

ETL 创建以下唯一约束和索引：

```cypher
CREATE CONSTRAINT movie_mid IF NOT EXISTS FOR (m:Movie) REQUIRE m.mid IS UNIQUE;
CREATE CONSTRAINT person_pid IF NOT EXISTS FOR (p:Person) REQUIRE p.pid IS UNIQUE;
CREATE CONSTRAINT genre_name IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE;
CREATE CONSTRAINT region_name IF NOT EXISTS FOR (r:Region) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT language_name IF NOT EXISTS FOR (l:Language) REQUIRE l.name IS UNIQUE;
CREATE CONSTRAINT content_type_name IF NOT EXISTS FOR (c:ContentType) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT year_bucket_name IF NOT EXISTS FOR (y:YearBucket) REQUIRE y.name IS UNIQUE;
CREATE INDEX movie_title IF NOT EXISTS FOR (m:Movie) ON (m.title);
CREATE INDEX movie_rating IF NOT EXISTS FOR (m:Movie) ON (m.rating);
CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name);
```

## 4. 数据规模口径

来自 `data_processing/reports/data_quality_report.md`：

| 指标 | 数值 |
|---|---:|
| Movies 表记录数 | 192,032 |
| Persons 表记录数 | 236,882 |
| 不重复影人 ID 数 | 236,886 |
| 电影类型数 | 32 |
| `ACTED_IN` 预估关系数 | 1,333,995 |
| `DIRECTED` 预估关系数 | 217,108 |
| `HAS_GENRE` 预估关系数 | 339,601 |
| 核心关系预估总数 | 1,890,704 |

地区、语言、内容形式和年代桶关系由 ETL 从电影元数据派生，数量与电影记录规模线性相关。论文中若需要精确写出这些扩展关系数量，应以实际 Neo4j 查询结果为准。
