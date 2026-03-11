# 豆瓣电影知识图谱 - Schema 设计文档

**版本**: v1.0
**日期**: 2026-02-01

---

## 1. 节点定义 (Nodes)

### 1.1 Movie (电影)

核心实体，对应 MySQL 中的 `movies` 表记录。

- **Label**: `:Movie`
- **Primary Key**: `mid` (对应 `douban_id`)
- **Properties**:
  | 属性名 | 类型 | 说明 | 来源字段 |
  |Str|Str|Str|Str|
  | `mid` | String | 豆瓣ID (唯一标识) | `douban_id` |
  | `title` | String | 电影名称 | `name` |
  | `rating` | Float | 豆瓣评分 | `douban_score` |
  | `release_date` | Date | 上映日期 | `release_date` |
  | `cover` | String | 封面图片URL | `cover` |
  | `url` | String | 豆瓣详情页链接 | (Constructed) |

### 1.2 Person (影人)

代表导演或演员。由于豆瓣中导演和演员常由同一人担任（如姜文），我们使用一个统一的 `Person` 节点，通过关系来区分角色。

- **Label**: `:Person`
- **Primary Key**: `pid` (豆瓣影人ID)
- **Properties**:
  | 属性名 | 类型 | 说明 | 来源字段 |
  |Str|Str|Str|Str|
  | `pid` | String | 影人ID | 解析自 `actor_ids`/`director_ids` |
  | `name` | String | 姓名 | 解析自 `actor_ids`/`director_ids` |
  | `birth` | Date | 出生日期 | (Future Extension) |
  | `death` | Date | 去世日期 | (Future Extension) |
  | `birthplace` | String | 出生地 | (Future Extension) |
  | `biography` | String | 个人简介 | (Future Extension) |

### 1.3 Genre (类型)

电影类型，如“剧情”、“喜剧”。

- **Label**: `:Genre`
- **Primary Key**: `name`
- **Properties**:
  | 属性名 | 类型 | 说明 |
  |Str|Str|Str|
  | `name` | String | 类型名称 (Unique) |

### 1.4 Region / Language / ContentType / YearBucket

为推荐实验补充的结构节点，全部从 `movies` 表现有字段派生，不引入外部数据源。

- **Region**
  - Label: `:Region`
  - Primary Key: `name`
- **Language**
  - Label: `:Language`
  - Primary Key: `name`
- **ContentType**
  - Label: `:ContentType`
  - Primary Key: `name`
- **YearBucket**
  - Label: `:YearBucket`
  - Primary Key: `name`
  - Bucket 规则: `before_1990` / `1990s` / `2000s` / `2010s` / `2020s_plus`

---

## 2. 关系定义 (Relationships)

### 2.1 执导 (`DIRECTED`)

- **Start Node**: `:Person`
- **End Node**: `:Movie`
- **Type**: `:DIRECTED`
- **Properties**: 无

### 2.2 参演 (`ACTED_IN`)

- **Start Node**: `:Person`
- **End Node**: `:Movie`
- **Type**: `:ACTED_IN`
- **Properties**:
    - `role`: String (可选，饰演的角色名，当前爬虫暂未爬取，预留)
    - `order`: Integer (可选，演员表排序)

### 2.3 属于类型 (`HAS_GENRE`)

- **Start Node**: `:Movie`
- **End Node**: `:Genre`
- **Type**: `:HAS_GENRE`

### 2.4 扩展结构关系

- `(:Movie)-[:IN_REGION]->(:Region)`
- `(:Movie)-[:IN_LANGUAGE]->(:Language)`
- `(:Movie)-[:HAS_CONTENT_TYPE]->(:ContentType)`
- `(:Movie)-[:IN_YEAR_BUCKET]->(:YearBucket)`

---

## 3. 索引策略 (Indices & Constraints)

为了保证查询性能和数据完整性，必须创建以下约束：

```cypher
// 唯一性约束 (同时也自动创建索引)
CREATE CONSTRAINT FOR (m:Movie) REQUIRE m.mid IS UNIQUE;
CREATE CONSTRAINT FOR (p:Person) REQUIRE p.pid IS UNIQUE;
CREATE CONSTRAINT FOR (g:Genre) REQUIRE g.name IS UNIQUE;
CREATE CONSTRAINT FOR (r:Region) REQUIRE r.name IS UNIQUE;
CREATE CONSTRAINT FOR (l:Language) REQUIRE l.name IS UNIQUE;
CREATE CONSTRAINT FOR (c:ContentType) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT FOR (y:YearBucket) REQUIRE y.name IS UNIQUE;

// 辅助索引
CREATE INDEX FOR (m:Movie) ON (m.title);
CREATE INDEX FOR (m:Movie) ON (m.rating);
```

## 4. 数据量预估

假设 MySQL 中有 10,000 部电影：

- **Movie 节点**: 10,000 个
- **Person 节点**: 约 30,000 - 50,000 个 (假设平均每部电影关联 5-10 个影人，考虑重叠)
- **Genre 节点**: 约 30 个 (固定集合)
- **Region / Language / ContentType / YearBucket 节点**: 数量较小，通常远少于 Movie/Person
- **Relationships**:
    - `ACTED_IN`: ~60,000 (平均 6 个演员)
    - `DIRECTED`: ~12,000 (平均 1.2 个导演)
    - `HAS_GENRE`: ~25,000 (平均 2.5 个类型)
    - `IN_REGION` / `IN_LANGUAGE` / `HAS_CONTENT_TYPE` / `IN_YEAR_BUCKET`: 按电影元数据规模线性增长
    - **Total Edges**: ~100,000 条

规模属于 **小型图谱**，单机 Neo4j (Docker 1GB RAM) 即可轻松承载。
