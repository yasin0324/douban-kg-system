# 豆瓣电影知识图谱项目开发计划书

> 2026-03-10 备注：文中推荐算法、CFKG、离线评估与相关脚本内容已归档，不再对应当前仓库实现。

## 1. 项目概述

### 1.1 项目名称

基于豆瓣电影的知识图谱构建与应用

### 1.2 项目目标

在两个月（8周）内完成系统开发，包括：

1. 数据采集与预处理：爬取豆瓣电影数据，确保数据质量和完整性
2. 知识抽取与表示：从采集数据中抽取实体（电影、导演、演员、类型）和关系，形成知识三元组
3. 知识图谱构建：使用Neo4j构建并存储知识图谱，确保查询高效
4. 系统集成与可视化：使用FastAPI+Vue3前后端分离架构，实现知识图谱电影应用
5. 用户行为与内容浏览：实现登录、评分、偏好管理以及图谱化内容浏览

### 1.3 技术栈

#### 后端技术栈

- **数据采集**：Python + Scrapy 或 Requests+BeautifulSoup
- **数据清洗**：Pandas
- **NLP处理**：HanLP（命名实体识别）、jieba（分词）
- **图数据库**：Neo4j + Cypher
- **Web框架**：FastAPI（高性能异步API框架）
- **推荐算法**：
    - 基于图结构：Personalized PageRank、图卷积网络（GCN）、LightGCN
    - 基于内容：TF-IDF、余弦相似度、向量嵌入（Embedding）
    - 混合推荐：多策略加权融合

#### 前端技术栈

- **框架**：Vue3 + Composition API
- **状态管理**：Pinia
- **路由**：Vue Router 4
- **UI组件库**：Element Plus 或 Ant Design Vue
- **HTTP客户端**：Axios
- **图谱可视化**：ECharts 或 D3.js
- **构建工具**：Vite

#### 开发工具

- **版本控制**：Git
- **API测试**：Postman / Apifox
- **IDE**：PyCharm（后端）+ WebStorm / VS Code（前端）

---

## 2. 时间线总览

| 阶段 | 时间       | 主要目标 | 交付物                 |
| ---- | ---------- | -------- | ---------------------- | ------------------------------------------------------------ |
|      | **阶段一** | 第1-2周  | 环境搭建 & 数据采集    | 1000+电影数据，爬虫系统                                      |
|      | **阶段二** | 第3-4周  | 数据处理 & 知识抽取    | 清洗数据，实体关系三元组                                     |
|      | **阶段三** | 第5-6周  | 知识图谱构建 & API开发 | Neo4j图谱，7000+节点，15000+关系，FastAPI基础接口            |
|      | **阶段四** | 第7周    | 前后端主链路打通       | Vue3界面、图谱可视化、前后端接口联调、系统可演示（不含推荐） |
|      | **阶段五** | 第8周    | 推荐算法增强与验证     | PPR/Content/CF/Hybrid 可用，用户画像驱动推荐链路与评估报告   |

### 关键里程碑

- **第2周末**：成功采集1000+部电影的完整数据
- **第4周末**：完成数据质量评分 ≥90%，知识抽取准确率 ≥95%
- **第6周末**：知识图谱加载完成，FastAPI基础接口可用
- **第7周末**：完成非推荐主链路打通（前后端+图谱可视化+数据连通）
- **第8周末**：推荐算法功能完成并通过评估，完整系统演示

---

## 3. 详细周计划

### 第1周：环境搭建与数据爬虫开发

#### 3.1 任务清单

- [ ] 后端开发环境搭建（Python 3.8+、Neo4j、Git、FastAPI）
- [ ] 前端开发环境搭建（Node.js、Vue3、Vite、Element Plus）
- [ ] Scrapy框架安装与配置
- [ ] 豆瓣电影页面结构分析
- [ ] 编写电影列表页爬虫
- [ ] 编写电影详情页爬虫
- [ ] 实现User-Agent轮换与请求延迟
- [ ] 基础数据存储（JSON格式）

#### 3.2 交付物

- 开发环境配置文档（`docs/env_setup.md`）
- Scrapy爬虫项目结构
- 电影列表爬虫（`spiders/movie_list.py`）
- 电影详情爬虫（`spiders/movie_detail.py`）
- 配置文件（`settings.py`，包含DOWNLOAD_DELAY=2）

#### 3.3 成功标准

**功能标准：**

- 爬虫能够成功访问豆瓣电影页面
- 能够提取电影标题、评分、导演、演员、类型、上映时间等基本信息
- 能够处理分页，支持批量爬取

**可观察标准：**

- 成功爬取并保存至少100部电影数据到JSON文件
- 无明显的反爬封锁（IP未被封禁）
- 爬取速度控制在合理范围（~5秒/页）

**通过/失败标准：**

- ✅ 通过：JSON文件包含100+条电影记录，字段完整率≥90%
- ❌ 失败：爬取失败率≥20% 或 字段缺失率≥30%

#### 3.4 测试验证

**测试方法：**

```python
# 验证数据完整性
import json

with open('movies_week1.json', 'r', encoding='utf-8') as f:
    movies = json.load(f)

required_fields = ['title', 'rating', 'directors', 'actors', 'genres']
completeness = sum(1 for m in movies if all(f in m for f in required_fields))
assert completeness >= 90, f"数据完整率: {completeness/len(movies)*100:.2f}%"
```

**预期结果：**

- 通过验证脚本，数据完整率≥90%
- 爬虫日志显示成功爬取100+部电影
- 控制台无关键错误（ERROR级别）

---

### 第2周：大规模数据采集与优化

#### 3.5 任务清单

- [ ] 优化爬虫性能（并发控制、请求延迟）
- [ ] 实现断点续爬功能
- [ ] 扩展数据采集范围（演员、导演详细信息）
- [ ] 实现数据去重机制
- [ ] 添加错误处理与重试逻辑
- [ ] 数据验证与清洗（基础版本）
- [ ] 大规模数据爬取（目标：1000+电影）

#### 3.6 交付物

- 优化后的爬虫配置（`settings.py`）
- 断点续爬中间件（`middlewares.py`）
- 数据去重Pipeline（`pipelines.py`）
- 数据验证脚本（`validate_data.py`）
- 1000+条电影数据集（`movies_week2.json`）

#### 3.7 成功标准

**功能标准：**

- 支持断点续爬，中断后可从上次停止位置继续
- 能够处理网络异常和反爬机制
- 自动去重，无重复数据

**可观察标准：**

- 成功采集1000+部电影的完整数据
- 数据去重率≥5%（说明去重机制生效）
- 爬取稳定运行，无频繁崩溃

**通过/失败标准：**

- ✅ 通过：数据集≥1000条，去重有效，数据完整率≥90%
- ❌ 失败：数据集<800条 或 数据完整率<85%

#### 3.8 测试验证

**测试方法：**

```python
# 验证数据规模和质量
import json

with open('movies_week2.json', 'r', encoding='utf-8') as f:
    movies = json.load(f)

# 规模验证
assert len(movies) >= 1000, f"数据量: {len(movies)}"

# 去重验证（通过ID检查）
movie_ids = [m['id'] for m in movies]
assert len(set(movie_ids)) == len(movie_ids), "存在重复数据"

# 字段完整性验证
required_fields = ['title', 'rating', 'directors', 'actors', 'genres', 'release_date']
avg_completeness = sum(1 for m in movies
                       for f in required_fields if f in m and m[f]) / (len(movies) * len(required_fields))
assert avg_completeness >= 0.90, f"字段完整率: {avg_completeness*100:.2f}%"
```

**预期结果：**

- 所有断言通过
- 数据质量报告显示各项指标达标
- 爬虫日志显示运行稳定，错误率<5%

---

### 第3周：数据清洗与标准化

#### 3.9 任务清单

- [ ] 数据质量分析（缺失值、异常值、重复值）
- [ ] 实现数据清洗Pipeline（使用Pandas）
- [ ] 缺失值处理策略（删除、填充、标记）
- [ ] 数据格式标准化（日期、评分、类型）
- [ ] 异常值检测与处理
- [ ] 数据质量评分系统
- [ ] 清洗后数据验证

#### 3.10 交付物

- 数据质量分析报告（`docs/data_quality_report.md`）
- 数据清洗Pipeline（`data_processing/clean_pipeline.py`）
- 数据标准化规则文档（`docs/data_standards.md`）
- 清洗后数据集（`data/processed/movies_cleaned.csv`）
- 数据质量评分脚本（`data_processing/quality_score.py`）

#### 3.11 成功标准

**功能标准：**

- 自动检测并处理数据质量问题
- 数据格式统一，符合存储要求
- 生成可读的数据质量报告

**可观察标准：**

- 数据质量评分 ≥90
- 关键字段缺失率 <5%
- 无明显的数据异常（如评分不在0-10范围内）

**通过/失败标准：**

- ✅ 通过：质量评分≥90，数据可用于后续处理
- ❌ 失败：质量评分<80 或 关键字段缺失率>10%

#### 3.12 测试验证

**测试方法：**

```python
import pandas as pd

df = pd.read_csv('data/processed/movies_cleaned.csv')

# 1. 缺失值检查
missing_rate = df.isnull().sum() / len(df)
assert missing_rate.max() < 0.05, f"最高缺失率: {missing_rate.max()*100:.2f}%"

# 2. 评分范围检查
assert df['rating'].between(0, 10).all(), "存在超出范围的评分"

# 3. 日期格式检查
assert pd.to_datetime(df['release_date'], errors='coerce').notna().all(), "日期格式错误"

# 4. 类型标准化检查
genre_set = {'剧情', '喜剧', '动作', '爱情', '科幻', '悬疑', '恐怖', '动画'}
valid_genres = df['genres'].apply(lambda x: set(x.split(','))).apply(
    lambda g: all(item in genre_set for item in g)
)
assert valid_genres.all(), "存在未知电影类型"
```

**预期结果：**

- 所有断言通过
- 数据质量报告显示各项指标合格
- 清洗日志记录所有处理操作

---

### 第4周：知识抽取与表示

#### 3.13 任务清单

- [ ] 设计知识图谱Schema（节点类型、关系类型、属性）
- [ ] 实现实体抽取（电影、导演、演员、类型）
- [ ] 实现关系抽取（出演、导演、类型归属）
- [ ] 实现属性抽取（评分、上映日期等）
- [ ] 构建知识三元组（实体-关系-实体/属性）
- [ ] 实体消歧（同名演员/导演区分）
- [ ] 生成Neo4j导入文件

#### 3.14 交付物

- 知识图谱Schema设计文档（`docs/schema_design.md`）
- 实体抽取模块（`data_processing/entity_extractor.py`）
- 关系抽取模块（`data_processing/relation_extractor.py`）
- 实体消歧模块（`data_processing/entity_disambiguation.py`）
- 知识三元组数据集（`data/processed/triples.csv`）
- Neo4j导入脚本（`graph_db/import_to_neo4j.py`）

#### 3.15 成功标准

**功能标准：**

- 准确识别所有类型的实体
- 正确建立实体之间的关系
- 能够处理同名实体消歧

**可观察标准：**

- 提取实体总数：电影≥1000，导演≥500，演员≥5000
- 提取关系总数 ≥15000
- 实体消歧准确率 ≥95%

**通过/失败标准：**

- ✅ 通过：实体关系抽取准确率≥95%，数据可用于图谱构建
- ❌ 失败：准确率<90% 或 关系抽取存在严重错误

#### 3.16 测试验证

**测试方法：**

```python
import pandas as pd

# 1. 实体类型检查
triples = pd.read_csv('data/processed/triples.csv', names=['entity1', 'relation', 'entity2', 'type'])
entity_types = set(triples['type'].unique())
expected_types = {'movie', 'director', 'actor', 'genre'}
assert expected_types.issubset(entity_types), f"缺少实体类型: {expected_types - entity_types}"

# 2. 关系类型检查
relation_types = set(triples['relation'].unique())
expected_relations = {'directed_by', 'starred_by', 'has_genre', 'released_in'}
assert expected_relations.issubset(relation_types), f"缺少关系类型: {expected_relations - relation_types}"

# 3. 实体消歧验证（手动抽查）
test_case = triples[triples['entity1'] == '刘德华']
assert len(test_case) > 0, "刘德华实体不存在"
# 验证不同电影的刘德华是否指向同一实体
liu_roles = triples[triples['entity1'] == '刘德华']['entity2'].tolist()
assert len(set(liu_roles)) > 5, "刘德华出演电影过少"

# 4. 三元组完整性检查
assert triples.isnull().sum().sum() == 0, "三元组存在空值"
```

**预期结果：**

- 所有断言通过
- 实体关系统计报告显示数据规模达标
- 消歧准确率抽样验证≥95%

---

### 第5周：Neo4j环境搭建与基础导入

#### 3.17 任务清单

- [ ] Neo4j安装与配置（Docker或本地安装）
- [ ] Neo4j数据库连接测试
- [ ] 设计Cypher索引策略
- [ ] 实现批量数据导入（使用UNWIND优化）
- [ ] 导入实体节点（电影、导演、演员、类型）
- [ ] 导入关系节点
- [ ] 基础查询测试
- [ ] FastAPI项目初始化

#### 3.18 交付物

- Neo4j安装配置文档（`docs/neo4j_setup.md`）
- 索引创建脚本（`graph_db/create_indexes.cypher`）
- 批量导入脚本（`graph_db/batch_import.py`）
- 基础查询测试脚本（`graph_db/test_queries.cypher`）
- FastAPI项目结构（`api/`目录）
- FastAPI基础配置（`api/config.py`）

#### 3.19 成功标准

**功能标准：**

- Neo4j成功运行并可访问
- 批量导入性能良好（1000条节点/分钟）
- 基础查询响应时间<500ms
- FastAPI服务可启动并响应

**可观察标准：**

- 成功导入1000+电影节点
- 成功导入500+导演节点
- 成功导入5000+演员节点
- 成功导入15000+关系边
- FastAPI接口返回200状态码

**通过/失败标准：**

- ✅ 通过：图谱数据完整导入，基础查询正常，性能达标
- ❌ 失败：导入失败率>5% 或 查询性能>2秒

#### 3.20 测试验证

**测试方法：**

```cypher
// 1. 节点数量验证
MATCH (m:Movie) RETURN count(m) AS movie_count
// 预期: ≥1000

MATCH (d:Director) RETURN count(d) AS director_count
// 预期: ≥500

MATCH (a:Actor) RETURN count(a) AS actor_count
// 预期: ≥5000

// 2. 关系数量验证
MATCH ()-[r]->() RETURN count(r) AS relation_count
// 预期: ≥15000

// 3. 查询性能测试
PROFILE MATCH (m:Movie {title: '肖申克的救赎'})--(p:Person) RETURN p
// 检查: db hits < 10000

// 4. 索引有效性验证
CALL db.indexes() YIELD name, state
// 检查: 所有关键索引状态为 ONLINE
```

**FastAPI测试：**

```python
import requests
response = requests.get("http://localhost:8000/health")
assert response.status_code == 200
assert response.json()['status'] == 'ok'
```

**预期结果：**

- 所有计数查询返回预期结果
- PROFILE查询显示索引生效，db hits合理
- 查询响应时间<500ms
- FastAPI健康检查通过

---

### 第6周：知识图谱优化与基础API开发

#### 3.21 任务清单

- [ ] 图谱性能优化（索引调整、查询优化）
- [ ] 实现复杂查询路径（多跳关系查询）
- [ ] 实现图算法（PageRank、最短路径、社区检测）
- [ ] Neo4j APOC插件集成
- [ ] 构建FastAPI基础接口（电影查询、图谱查询）
- [ ] 实现图谱可视化API（返回图数据结构）
- [ ] 性能压力测试

#### 3.22 交付物

- 性能优化报告（`docs/performance_optimization.md`）
- 高级查询脚本集（`graph_db/advanced_queries.cypher`）
- 图算法实现（`graph_db/graph_algorithms.py`）
- FastAPI基础接口（`api/routes/`）
- FastAPI图数据接口（`api/routes/graph.py`）

#### 3.23 成功标准

**功能标准：**

- 复杂查询响应时间<2秒
- 图算法正确执行
- API接口稳定可用
- 图数据接口返回前端可用格式

**可观察标准：**

- API平均响应时间<200ms
- 图算法返回合理结果
- 前端可获取并展示图数据

**通过/失败标准：**

- ✅ 通过：API性能达标，查询功能正常，图数据接口可用
- ❌ 失败：API错误率>5% 或 关键查询超时

#### 3.24 测试验证

**API测试：**

```python
import requests
import time

base_url = "http://localhost:8000/api"

# 1. 基础查询测试
start = time.time()
response = requests.get(f"{base_url}/movie/肖申克的救赎")
latency = time.time() - start
assert latency < 0.5, f"查询延迟: {latency:.2f}s"
assert response.status_code == 200

# 2. 图数据查询测试
start = time.time()
response = requests.get(f"{base_url}/graph/movie/1292052?depth=2")
latency = time.time() - start
assert latency < 1.0, f"图查询延迟: {latency:.2f}s"
assert 'nodes' in response.json() and 'edges' in response.json()

# 3. 压力测试（100请求并发）
import concurrent.futures

def api_call():
    requests.get(f"{base_url}/movie/肖申克的救赎")

start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(api_call) for _ in range(100)]
    concurrent.futures.wait(futures)
duration = time.time() - start
assert duration < 10, f"100请求耗时: {duration:.2f}s"
```

**图算法验证：**

```cypher
// PageRank算法验证
CALL algo.pageRank.stream('Movie', 'DIRECTED_BY')
YIELD nodeId, score
RETURN algo.getNodeById(nodeId).title AS movie, score
ORDER BY score DESC
LIMIT 10
// 检查: 高分电影出现在前列（如《肖申克的救赎》）

// 最短路径验证
MATCH path = shortestPath(
  (m1:Movie {title: '肖申克的救赎'})-[*]-(m2:Movie {title: '教父'})
)
RETURN path
// 检查: 返回合理路径，如导演或演员关联
```

**预期结果：**

- 所有API测试通过
- 响应时间满足要求
- 图算法返回符合预期的结果
- 图数据接口返回格式正确

---

### 第7周：Vue3前端开发与主链路打通（不含推荐）

#### 3.25 任务清单

- [ ] Vue3项目初始化（Vite + Vue Router + Pinia）
- [ ] UI组件库集成（Element Plus）
- [ ] 电影搜索页面开发
- [ ] 电影详情页面开发
- [ ] 图谱可视化组件（ECharts）
- [ ] 前后端接口联调（auth/movies/persons/graph/stats）
- [ ] 系统整体测试（非推荐路径）
- [ ] 文档整理与演示准备

#### 3.26 交付物

- Vue3前端项目（`frontend/`目录）
- 电影搜索页面（`frontend/src/views/Search.vue`）
- 电影详情页面（`frontend/src/views/Detail.vue`）
- 图谱可视化组件（`frontend/src/components/GraphVisualization.vue`）
- API集成配置（`frontend/src/api/`）
- 非推荐主链路联调清单（`docs/integration_checklist.md`）
- 系统用户手册（`docs/user_guide.md`）

#### 3.27 成功标准

**功能标准：**

- 前端页面完整实现，交互流畅
- 非推荐核心 API 全部成功对接
- 图谱可视化正常显示（1 跳稳定加载）
- 系统可完整演示（登录->搜索->详情->图谱）

**可观察标准：**

- 页面加载时间 <2 秒
- 前端无控制台错误
- 图谱交互响应流畅（展开/过滤）
- 响应式设计支持不同屏幕

**通过/失败标准：**

- ✅ 通过：非推荐主链路完整打通，可稳定演示
- ❌ 失败：前后端主链路存在阻塞点或图谱页面不可用

#### 3.28 测试验证

**前端测试：**

```bash
cd frontend
npm install
npm run dev
npm run build
```

**集成测试（非推荐）**：

```python
assert requests.get("http://localhost:8000/health").status_code == 200
assert requests.get(f"{base_url}/api/movies/search?q=肖申克&page=1&size=20").status_code == 200
assert requests.get(f"{base_url}/api/graph/movie/1292052?depth=1&node_limit=150&edge_limit=300").status_code == 200
```

**预期结果：**

- 前端构建成功、非推荐接口全部联通、演示流程顺畅

---

### 第8周：推荐算法增强与系统收口 ✅ 已完成 (2026-03-07)

#### 3.29 任务清单

- [x] 实现 Personalized PageRank 推荐算法，并改为用户画像驱动的图游走
- [x] 实现基于图内容的推荐算法（类型/导演/演员命中 + 画像重排）
- [x] 实现图协同过滤（CF）分支，并纳入正负反馈约束
- [x] 实现混合推荐策略（PPR + Content + CF + 动态门控）
- [x] 实现传统论文基线 `ItemCF / TF-IDF`
- [x] 完成 `CFKG` 默认主链路与知识图谱嵌入推理接入
- [x] 完成推荐 API 接口联调与冷启动/重刷机制
- [x] 完成首页推荐预览、推荐中心、解释抽屉前端页面
- [x] 完成推荐系统测试、离线评估脚本与报告输出

#### 3.30 交付物

- 推荐技术文档（`documents/kg_technical_doc.md`）
- 论文 2.5 节提纲稿（推荐系统设计与实现）
- 离线评估脚本与报告（`db-backend/scripts/evaluate_recommendations.py`、`db-backend/reports/`）
- PPR 实现（`db-backend/app/algorithms/graph_ppr.py`）
- 图内容推荐实现（`db-backend/app/algorithms/graph_content.py`）
- 图协同过滤实现（`db-backend/app/algorithms/graph_cf.py`）
- 混合推荐调度器（`db-backend/app/algorithms/hybrid_manager.py`）
- `ItemCF` 与 `TF-IDF` 基线实现（`db-backend/app/algorithms/item_cf.py`、`db-backend/app/algorithms/tfidf_content.py`）
- 推荐服务与 API（`db-backend/app/services/recommend_service.py`、`db-backend/app/routers/recommend.py`）
- 推荐页与首页预览（`db-frontend/src/views/RecommendView.vue`、`db-frontend/src/views/HomeView.vue`）

#### 3.31 成功标准

**功能标准：**

- `ItemCF / TF-IDF / CF / Content / PPR / Hybrid / CFKG` 七种算法可用于实验对照
- 首页与推荐页继续保持 `CFKG` 作为默认主推荐入口
- 推荐 API 支持算法切换
- 首页与推荐页能展示真实个性化结果并支持重新生成
- 推荐结果可在前端页面正常展示
- 推荐解释抽屉可展示画像理由、图谱证据小图和算法指标
- 离线评估脚本可输出 JSON 与 Markdown 报告

**可观察标准：**

- 推荐响应时间 <3 秒（P95）
- 推荐列表相关性 ≥70%
- 推荐结果多样性达标（前10部不重复）
- 不同算法产生可区分的结果

**通过/失败标准：**

- ✅ 通过：核心推荐算法可用、质量达标、系统完整演示通过
- ❌ 失败：核心算法不可用或推荐质量明显不足

#### 3.32 测试验证

**算法/API 测试：**

```python
resp = requests.get(
    f"{base_url}/api/recommend/personal?algorithm=cfkg&limit=10",
    headers={"Authorization": f"Bearer {token}"},
)
assert resp.status_code == 200
assert resp.json()["algorithm"] == "cfkg"
assert "items" in resp.json()
```

**预期结果：**

- 推荐算法测试通过，前后端推荐链路可用，系统收口完成

---

## 4. 成功标准汇总

### 4.1 项目级成功标准

**功能性：**

- ✅ 成功采集1000+部电影的完整数据
- ✅ 知识图谱包含至少7000个节点和15000条边
- ✅ 先完成非推荐主链路打通（前后端+图谱可视化+数据连通）
- ✅ 实现核心推荐算法（ItemCF、TF-IDF、PPR、内容、CF、混合、CFKG），统一纳入实验框架
- ✅ 推荐算法支持多种策略选择与自动降级
- ✅ FastAPI后端接口完整可用
- ✅ Vue3前端界面完整可用

**质量指标：**

- ✅ 数据完整率 ≥95%
- ✅ 知识抽取准确率 ≥95%
- ✅ 推荐相关性 ≥70%
- ✅ API平均响应时间 <200ms
- ✅ 查询响应时间 <2秒
- ✅ 推荐响应时间 <3秒

**可观测性：**

- ✅ 系统可完整演示（10-15分钟）
- ✅ 代码覆盖率 ≥70%（核心模块）
- ✅ 文档完整（安装、使用、API文档）
- ✅ 无严重Bug（错误率<1%）
- ✅ 前后端无缝对接

### 4.2 通过/失败标准

**✅ 项目通过：**

- 所有核心功能正常运行
- 关键质量指标达标
- 系统可稳定演示
- 推荐系统支持多种策略（含可选CF）
- 文档齐全
- 前后端完整对接

**❌ 项目失败：**

- 任一核心功能不可用
- 关键质量指标<80%
- 系统无法稳定演示
- 前后端无法对接
- 数据规模严重不足（<50%目标）

---

## 5. 风险管理

### 5.1 技术风险

| 风险 | 影响               | 概率 | 缓解策略 | 应急计划                                                      |
| ---- | ------------------ | ---- | -------- | ------------------------------------------------------------- | --------------------------------------------------------------------- |
|      | **反爬虫机制增强** | 高   | 中       | 1. 使用代理IP池<br>2. 模拟真实浏览器行为<br>3. 限制爬取速度   | 1. 使用官方API（如有）<br>2. 使用第三方数据集<br>3. 减少数据规模要求  |
|      | **Neo4j性能不足**  | 中   | 低       | 1. 优化查询和索引<br>2. 使用UNWIND批量导入<br>3. 考虑云数据库 | 1. 减少数据规模<br>2. 分库分表<br>3. 使用轻量级图数据库               |
|      | **NLP准确率低**    | 中   | 中       | 1. 使用预训练模型<br>2. 构建领域词典<br>3. 人工校验关键数据   | 1. 简化NLP任务<br>2. 增加规则匹配<br>3. 手工标注训练数据              |
|      | **数据质量问题**   | 高   | 高       | 1. 多源数据验证<br>2. 严格数据清洗<br>3. 数据质量监控         | 1. 手工修正关键数据<br>2. 降低数据规模要求<br>3. 使用公开数据集       |
|      | **推荐算法效果差** | 高   | 中       | 1. 研究多种算法<br>2. 参数调优<br>3. 混合策略                 | 1. 使用经典推荐算法<br>2. 降低推荐质量要求<br>3. 重点展示推荐策略选择 |
|      | **前后端对接困难** | 中   | 中       | 1. 明确API接口规范<br>2. 使用Swagger文档<br>3. 前后端并行开发 | 1. 简化接口设计<br>2. 使用Mock数据<br>3. 延后部分功能                 |

### 5.2 时间风险

| 风险 | 影响             | 概率 | 缓解策略 | 应急计划                                                     |
| ---- | ---------------- | ---- | -------- | ------------------------------------------------------------ | ----------------------------------------------------- |
|      | **学习曲线陡峭** | 高   | 中       | 1. 提前学习关键技术<br>2. 使用成熟方案<br>3. 寻求导师帮助    | 1. 延长学习时间<br>2. 简化技术栈<br>3. 延后非核心功能 |
|      | **任务估算偏差** | 中   | 中       | 1. 增加20%缓冲时间<br>2. 每周进度审查<br>3. 动态调整计划     | 1. 削减次要功能<br>2. 降低数据规模<br>3. 寻求外部帮助 |
|      | **不可预见问题** | 中   | 低       | 1. 保留20%缓冲时间<br>2. 优先完成核心功能<br>3. 快速迭代开发 | 1. 延长开发周期<br>2. 缩减功能范围<br>3. 寻求额外资源 |

### 5.3 资源风险

| 风险 | 影响             | 概率 | 缓解策略 | 应急计划                                                            |
| ---- | ---------------- | ---- | -------- | ------------------------------------------------------------------- | ----------------------------------------------------------- |
|      | **硬件资源不足** | 中   | 低       | 1. 提前规划硬件需求<br>2. 使用云服务（按需）<br>3. 优化数据加载策略 | 1. 分批处理数据<br>2. 使用轻量级方案<br>3. 寻求学校资源支持 |
|      | **网络问题**     | 低   | 中       | 1. 爬虫增加重试机制<br>2. 使用缓存避免重复请求<br>3. 多时段爬取     | 1. 调整爬取时间<br>2. 使用代理网络<br>3. 延长爬取周期       |

### 5.4 风险监控机制

**每周风险检查：**

- 进度是否按计划？
- 技术难点是否有进展？
- 资源是否充足？
- 是否有新风险出现？

**风险响应流程：**

1. 识别风险 → 2. 评估影响 → 3. 启动缓解策略 → 4. 监控效果 → 5. 必要时启动应急计划

---

## 6. 资源需求

### 6.1 硬件需求

| 组件 | 最低配置 | 推荐配置               | 用途                   |
| ---- | -------- | ---------------------- | ---------------------- | --------------------------------------------- |
|      | **CPU**  | Intel i5 / AMD Ryzen 5 | Intel i7 / AMD Ryzen 7 | 数据处理、Neo4j运行                           |
|      | **内存** | 8GB                    | 16GB                   | Neo4j图数据库、Python数据处理、前端构建       |
|      | **存储** | 30GB SSD               | 50GB SSD               | Neo4j数据、Python环境、爬取数据、Node_modules |
|      | **网络** | 宽带连接               | 宽带连接               | 爬虫数据采集、npm包下载                       |

### 6.2 软件需求

#### 后端软件

| 软件 | 版本        | 用途    |
| ---- | ----------- | ------- | ---------------- |
|      | **Python**  | 3.8+    | 主要开发语言     |
|      | **Neo4j**   | 4.4+    | 图数据库         |
|      | **Scrapy**  | 2.5+    | 网络爬虫框架     |
|      | **Pandas**  | 1.3+    | 数据处理         |
|      | **HanLP**   | 2.0+    | 中文NLP          |
|      | **jieba**   | 0.42+   | 中文分词         |
|      | **FastAPI** | 0.68+   | Web API框架      |
|      | **uvicorn** | 0.15+   | ASGI服务器       |
|      | **py2neo**  | 2021.2+ | Neo4j Python驱动 |

#### 前端软件

| 软件 | 版本             | 用途 |
| ---- | ---------------- | ---- | ------------------ |
|      | **Node.js**      | 16+  | JavaScript运行环境 |
|      | **npm**          | 8+   | 包管理器           |
|      | **Vue3**         | 3.3+ | 前端框架           |
|      | **Vite**         | 4.0+ | 构建工具           |
|      | **Pinia**        | 2.1+ | 状态管理           |
|      | **Vue Router**   | 4.2+ | 路由管理           |
|      | **Element Plus** | 2.3+ | UI组件库           |
|      | **Axios**        | 1.4+ | HTTP客户端         |
|      | **ECharts**      | 5.4+ | 图表可视化         |

#### 开发工具

| 软件 | 版本                       | 用途  |
| ---- | -------------------------- | ----- | ------------ |
|      | **Git**                    | 2.30+ | 版本控制     |
|      | **PyCharm**                | 2022+ | Python IDE   |
|      | **WebStorm** / **VS Code** | 最新  | 前端IDE      |
|      | **Postman** / **Apifox**   | 最新  | API测试      |
|      | **Neo4j Browser**          | 内置  | 图数据库管理 |

### 6.3 数据需求

| 数据类型 | 目标规模     | 数据源  |
| -------- | ------------ | ------- | -------- |
|          | **电影数据** | 1000+部 | 豆瓣电影 |
|          | **导演数据** | 500+人  | 豆瓣电影 |
|          | **演员数据** | 5000+人 | 豆瓣电影 |

### 6.4 预算估算

| 项目 | 费用（人民币） | 说明   |
| ---- | -------------- | ------ | --------------------------- |
|      | **硬件**       | 0      | 使用现有设备                |
|      | **软件**       | 0      | 全部使用开源软件            |
|      | **云服务**     | 0-2100 | 可选，按需使用阿里云/腾讯云 |
|      | **数据**       | 0      | 豆瓣数据免费                |
|      | **总计**       | 0-2100 | 推荐使用本地部署，成本最低  |

---

## 7. 每日工作量估算

### 7.1 工作量分配

| 周次 | 核心工作 | 辅助工作 | 总工时  | 日均工时 |
| ---- | -------- | -------- | ------- | -------- | ---------------- |
|      | 第1周    | 35h      | 10h     | 45h      | 6.4h             |
|      | 第2周    | 35h      | 10h     | 45h      | 6.4h             |
|      | 第3周    | 35h      | 10h     | 45h      | 6.4h             |
|      | 第4周    | 35h      | 10h     | 45h      | 6.4h             |
|      | 第5周    | 35h      | 10h     | 45h      | 6.4h             |
|      | 第6周    | 35h      | 10h     | 45h      | 6.4h             |
|      | 第7周    | 37h      | 10h     | 47h      | 6.7h             |
|      | 第8周    | 36h      | 10h     | 46h      | 6.6h             |
|      | **总计** | **283h** | **80h** | **363h** | **平均 6.5h/天** |

**备注：**

- 核心工作：主要开发任务（编码、测试、调试）
- 辅助工作：文档编写、学习研究、问题排查
- 第7周增加工作量用于前后端联调与图谱可视化打通
- 第8周重点完成推荐算法增强与系统收口
- 预留62小时（15%）作为缓冲时间

### 7.2 工作时间建议

**工作日（周一至周五）：**

- 核心时段：上午 9:00 - 12:00（3小时）
- 休息时段：12:00 - 14:00（午餐、休息）
- 核心时段：下午 14:00 - 17:30（3.5小时）
- 辅助时段：晚上 19:00 - 21:00（2小时，可选）
- **日总计**：6.5-8.5小时

**周末（周六、周日）：**

- 建议：每天工作3-5小时，或休息一天
- 周末主要：学习新技术、文档整理、下周规划

### 7.3 学习时间分配

| 技术 | 学习时间           | 学习阶段 |
| ---- | ------------------ | -------- | ------------- |
|      | **Scrapy爬虫**     | 8h       | 第1周         |
|      | **Neo4j & Cypher** | 12h      | 第5周         |
|      | **HanLP/NLP**      | 8h       | 第4周         |
|      | **FastAPI**        | 8h       | 第5-6周       |
|      | **Vue3 + Vite**    | 12h      | 第1周 + 第7周 |
|      | **推荐算法**       | 15h      | 第8周         |
|      | **Element Plus**   | 5h       | 第7周         |
|      | **ECharts**        | 5h       | 第7周         |
|      | **总计**           | **73h**  | 分散在各周    |

### 7.4 健康与效率建议

**番茄工作法：**

- 工作专注 25分钟 → 休息 5分钟
- 每完成4个番茄钟 → 休息 15-30分钟
- 每日番茄钟目标：8-12个

**每周休息：**

- 建议：每周至少休息1天（建议周日）
- 休息日：完全不工作或仅做轻量级任务（如文档整理）

**效率提升：**

- 每天早上制定当日任务清单
- 优先完成高优先级、高难度任务
- 及时记录遇到的问题和解决方案
- 定期与导师沟通进度和问题

---

## 8. 附录

### 8.1 关键技术参考资料

**网络爬虫：**

- Scrapy官方文档：https://docs.scrapy.org/
- 豆瓣反爬策略研究：相关技术博客

**图数据库：**

- Neo4j官方文档：https://neo4j.com/docs/
- Cypher查询语言指南：https://neo4j.com/docs/cypher-manual/

**自然语言处理：**

- HanLP文档：https://hanlp.hankcs.com/
- jieba分词：https://github.com/fxsjy/jieba

**FastAPI：**

- FastAPI官方文档：https://fastapi.tiangolo.com/
- Pydantic文档：https://docs.pydantic.dev/

**Vue3：**

- Vue3官方文档：https://cn.vuejs.org/
- Vite文档：https://cn.vitejs.dev/
- Pinia文档：https://pinia.vuejs.org/zh/
- Element Plus文档：https://element-plus.org/zh-CN/

**推荐算法：**

- 《推荐系统实践》项亮 著
- 《推荐系统手册》项亮 等著
- Graph-based推荐算法论文：
    - "Item-Based Collaborative Filtering Recommendation Algorithms"
    - "Personalized PageRank" - Page et al.
    - "LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation"

**ECharts：**

- ECharts官方文档：https://echarts.apache.org/zh/

### 8.2 项目目录结构建议

```
graduation_project/
├── design.md                      # 开题报告书
├── development_plan.md            # 开发计划书（本文件）
├── README.md                      # 项目说明文档
├── requirements.txt               # Python依赖
├── .gitignore                     # Git忽略文件
├── docs/                          # 文档目录
│   ├── env_setup.md              # 环境搭建文档
│   ├── api.md                     # API文档
│   ├── schema_design.md           # 知识图谱Schema设计
│   ├── data_standards.md          # 数据标准
│   ├── user_guide.md              # 用户指南
│   ├── recommendation_research.md # 推荐算法研究文档
│   ├── neo4j_setup.md            # Neo4j配置文档
│   ├── performance_optimization.md # 性能优化报告
│   └── demo.md                    # 系统演示指南
├── data/                          # 数据目录
│   ├── raw/                       # 原始数据
│   ├── processed/                 # 清洗后数据
│   └── backups/                   # 数据备份
├── spiders/                       # 爬虫模块
│   ├── spiders/                   # Scrapy爬虫
│   ├── pipelines.py               # 数据管道
│   └── settings.py                # 爬虫配置
├── data_processing/               # 数据处理模块
│   ├── clean_pipeline.py          # 清洗管道
│   ├── entity_extractor.py        # 实体抽取
│   ├── relation_extractor.py      # 关系抽取
│   ├── entity_disambiguation.py   # 实体消歧
│   └── quality_score.py           # 质量评分
├── graph_db/                      # 图数据库模块
│   ├── create_indexes.cypher      # 索引创建
│   ├── batch_import.py            # 批量导入
│   ├── advanced_queries.cypher    # 高级查询
│   └── graph_algorithms.py        # 图算法实现
├── db-backend/                    # FastAPI后端模块
│   ├── app/
│   │   ├── main.py               # FastAPI应用入口
│   │   ├── routers/
│   │   │   └── recommend.py      # 推荐相关接口
│   │   ├── services/
│   │   │   └── recommend_service.py # 画像构建、推荐调度、解释接口
│   │   └── algorithms/
│   │       ├── graph_ppr.py      # Personalized PageRank
│   │       ├── graph_content.py  # 图内容推荐
│   │       ├── graph_cf.py       # 图协同过滤
│   │       └── hybrid_manager.py # 混合推荐调度器
│   └── tests/
│       └── test_recommendation_system.py
├── db-frontend/                   # Vue3前端项目
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.js                # Vue入口
│   │   ├── App.vue                # 根组件
│   │   ├── router/                # 路由配置
│   │   │   └── index.js
│   │   ├── stores/                # Pinia状态管理
│   │   │   └── auth.js
│   │   ├── api/                   # API调用
│   │   │   ├── movies.js
│   │   │   ├── graph.js
│   │   │   └── recommend.js
│   │   ├── views/                 # 页面组件
│   │   │   ├── HomeView.vue       # 首页推荐预览
│   │   │   ├── RecommendView.vue  # 推荐中心
│   │   │   ├── MovieDetailView.vue
│   │   │   └── GraphView.vue
│   │   ├── components/
│   │   │   ├── graph/KnowledgeGraph.vue
│   │   │   └── recommend/RecommendationCard.vue
│   │   └── composables/
│   │       ├── useRecommendations.js
│   │       └── useRecommendationHistory.js
│   └── public/                    # 静态资源
├── tests/                         # 测试模块
│   ├── test_data_processing.py    # 数据处理测试
│   ├── test_graph_db.py           # 图数据库测试
│   └── test_api.py                # API测试
├── utils/                         # 工具模块
│   ├── logger.py                  # 日志工具
│   ├── config.py                  # 配置管理
│   └── helpers.py                 # 辅助函数
└── scripts/                       # 脚本工具
    ├── start_backend.sh           # 启动后端
    ├── start_frontend.sh          # 启动前端
    └── demo.sh                    # 演示脚本
```

### 8.3 成功检查清单

**项目完成前检查：**

- [ ] 所有核心功能已实现并测试通过
- [ ] 数据规模达到目标（1000+电影、7000+节点、15000+关系）
- [ ] 所有质量指标达标（数据完整率≥95%、知识抽取准确率≥95%等）
- [ ] 非推荐主链路已完整打通并可演示
- [ ] 核心推荐算法可用（PPR、内容、CF、混合），统一由用户画像驱动
- [ ] 系统可稳定运行（无严重Bug、错误率<1%）
- [ ] API文档完整且准确
- [ ] 代码覆盖率≥70%（核心模块）
- [ ] 系统可完整演示（10-15分钟）
- [ ] 用户指南和API文档齐全
- [ ] Git版本提交规范，commit信息清晰
- [ ] 所有测试用例通过

**答辩准备检查：**

- [ ] 准备系统演示（录制视频或现场演示）
- [ ] 准备技术PPT（15-20分钟）
- [ ] 准备技术问题回答（常见问题清单）
- [ ] 准备代码展示（关键代码片段）
- [ ] 准备推荐算法对比分析报告
- [ ] 准备性能测试报告

---

## 9. 总结

本开发计划书为豆瓣电影知识图谱项目提供了详细的8周开发路线图，涵盖从数据采集、知识抽取、图谱构建到前后端打通与推荐增强的全过程。计划强调：

1. **可执行性**：每周任务明确，交付物具体，成功标准可量化
2. **风险管理**：识别主要风险并提供缓解策略和应急计划
3. **质量保证**：每个阶段都有测试验证方案和证据要求
4. **资源合理**：工作量估算现实，硬件软件需求明确
5. **前后端分离**：FastAPI + Vue3架构，现代化技术栈
6. **分阶段推荐**：先打通主链路，再完成推荐增强（四算法统一画像驱动）

**关键成功因素：**

- 严格按计划执行，每周进度审查
- 优先完成核心功能（MVP），再进行优化
- 遇到问题及时沟通，避免积累
- 充分利用缓冲时间，确保项目按时完成
- 第7周优先保证前后端与图谱可视化主链路稳定
- 第8周重点推进推荐算法研究与效果验证

**预期成果：**
一个功能完整的电影知识图谱推荐系统，包括数据采集、知识图谱构建、前后端主链路打通、核心推荐算法（PPR/内容/CF/混合）、用户画像驱动的个性化推荐、Vue3前端界面，为毕业设计答辩提供强有力的技术支撑。

---

**文档版本**: v2.2
**创建日期**: 2026-01-13
**最后更新**: 2026-03-07
**更新内容**:

1. 调整实施顺序为“先打通非推荐主链路，再完成推荐增强”，并同步CF可选策略口径
2. **[2026-03-05 标注]** 明确推荐系统融合方案（Phase 5），确定采用 PPR + Content + CF + Hybrid 四路融合算法。其中 CF（协同过滤）数据将采用大语言模型（LLM）基于用户画像标签生成模拟评分数据集，解决冷启动问题，相关技术细节请参考 `kg_technical_doc.md`。
3. **[2026-03-07 标注]** 推荐系统已切换为“用户画像驱动 + 知识图谱计算 + 可解释前端展示”架构；首页推荐预览、推荐中心、解释抽屉与四算法主链路均已落地。
