# 知识图谱与推荐系统技术文档

## 推荐算法融合方案 (Phase 5)

本系统将实现 PPR + Content + CF + Hybrid 四种算法的融合，构建“基于知识图谱的综合推荐系统”。核心目标是利用图结构发现隐性关系、利用文本发现内容相似性，同时借助大模型数据增强构建协同过滤矩阵，最终通过加权融合提供稳定且具有惊喜感的推荐结果。

---

### 1. PPR (Personalized PageRank) 算法详解与实施

**核心原理**: 
基于知识图谱拓扑结构进行随机游走。从用户偏好的节点（种子节点）出发，沿着边（演员、导演、类型）随机跳转，并以固定概率（如 0.15）跳回种子节点。多次迭代后，各节点的访问概率趋于稳定，概率越高的节点（电影）推荐优先级越高。它可以深层挖掘“相似导演拍摄的相似类型电影”这种隐性结构关联。

**准备工作**:
1. 确保 Neo4j 图数据库已启动并存储了高质量的 Movie, Person (Actor/Director), Genre 节点及它们之间的关系连边。
2. （可选但推荐）安装 Neo4j 的 GDS (Graph Data Science) 官方插件，这会让图算法在千级节点时的计算速度达到毫秒级。如果不安装 GDS，也可以用 Python 的 NetworkX 在内存中实现。

**代码实现步骤**:
1. 接收前端传来的 1 个或多个目标 `movie_ids` 作为种子节点。
2. 如果使用 GDS，在后端组装 Cypher 语句：
   ```cypher
   CALL gds.pageRank.stream({
     nodeProjection: ['Movie', 'Person', 'Genre'],
     relationshipProjection: ['ACTED_IN', 'DIRECTED', 'HAS_GENRE'],
     sourceNodes: $seed_nodes,
     dampingFactor: 0.85
   })
   YIELD nodeId, score
   RETURN gds.util.asNode(nodeId).name AS name, score
   ORDER BY score DESC LIMIT 50
   ```
3. 过滤掉用户已经看过的电影，过滤掉非 Movie 节点。
4. 返回归一化得分给 Hybrid 统筹中心。

---

### 2. 基于内容的推荐 (Content-Based) 详解与实施

**核心原理**: 
通过计算电影之间属性的数学相似度来进行推荐。对于分类标签（类型、国家），可以使用 One-hot 编码；对于最核心的**剧情简介 (storyline)**，则需要使用 NLP 技术将其转化为数学向量（词袋模型或 TF-IDF）。

**准备工作**:
1. 在后端的 Python 环境中安装第三方依赖库：
   `uv add pandas scikit-learn jieba`
2. 确保在 MySQL（或 Neo4j 补充属性中）含有大量完整的 `storyline` 和 `genres` 字段。

**代码实现步骤**:
1. **数据拉取与预处理**：使用 Pandas 一次性拉取 MySQL 中的几千部电影基础数据。
   ```python
   import pandas as pd
   df = pd.read_sql("SELECT douban_id, genres, storyline FROM movies", conn)
   ```
2. **NLP 分词处理**：使用 `jieba` 将中文字符串分词，并过滤掉无用停用词（如“的”、“了”）。
   ```python
   import jieba
   df['content_words'] = df['storyline'].fillna('').apply(lambda x: " ".join(jieba.lcut(x)))
   df['combined_features'] = df['genres'] + " " + df['content_words']
   ```
3. **TF-IDF 与相似度矩阵生成**：
   ```python
   from sklearn.feature_extraction.text import TfidfVectorizer
   from sklearn.metrics.pairwise import cosine_similarity
   
   tfidf = TfidfVectorizer()
   tfidf_matrix = tfidf.fit_transform(df['combined_features'])
   # 这一步计算出 [电影数量 x 电影数量] 的相似度大矩阵
   cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)
   ```
4. **实时推荐与工程优化**：计算矩阵很耗时。最好的做法是写个离线脚本（如每日跑一次），将 `cosine_sim` 或者相似度 top-100 直接写入 Redis 缓存或本地 `.npy` 文件。线上 API 请求时，只需几毫秒的查表操作。

---

### 3. 协同过滤 (Collaborative Filtering - CF) 详解与实施

**核心原理**: 
俗话说“物以类聚，人以群分”。系统会观察和你口味相似的其群体，看看他们还喜欢什么你还没看过的电影（UserCF），或者找看某部电影的人还常看哪些热门影片（ItemCF）。
为了解决爬虫无法抓取用户隐私数据的“冷启动”痛点，本系统引入**大语言模型（LLM）**生成海量仿真评分矩阵。

**准备工作**:
1. 准备大模型 API_KEY （如 DeepSeek / Kimi / 阿里云通义）。
2. 在 Python 环境中安装：`uv add requests surprise`。`surprise` 库专门用于推荐系统矩阵分解算法。

**代码实现步骤**:
1. **构建“人设集”并发起 LLM 生成**（离线脚本操作）：
   编写 Prompt：“你是一个【资深科幻片爱好者】，请从这部 500 个热门电影名单中选出 30 部看过的电影打分（1-5分）。必须符合你的科幻标签，且请适当保留少数冷门电影的高分。” 循环此步骤，生成约上万条由大模型“模拟”出来的 (user_id, movie_id, rating) JSON 记录。
2. **入库模拟数据**：将这些大模型返回的数据落表，形成一张结构完美、特征鲜明（有明显的偏好聚类）的评分明细表。
3. **算法训练 (ItemCF)**：
   使用 `Surprise` 库读取这个数据表，因为是基于物品的相似性，ItemCF 非常快且准确。
   ```python
   from surprise import Dataset, Reader, KNNBasic
   
   reader = Reader(rating_scale=(1, 5))
   data = Dataset.load_from_df(df_ratings[['user_id', 'douban_id', 'rating']], reader)
   trainset = data.build_full_trainset()
   
   # 使用余弦相似度构建基于 Item 的协同矩阵
   sim_options = {'name': 'cosine', 'user_based': False}
   algo = KNNBasic(sim_options=sim_options)
   algo.fit(trainset)
   ```
4. **结合真实用户流融合**：当你的前端真的有用户注册进来了，只要他点击了“喜欢”某部电影，将他的记录拼接到 `trainset` 中，该用户立刻能吃到大模型矩阵带来的丰厚历史推荐池。

---

### 4. 混合推荐 (Hybrid) 的最终调度实现

**核心原理**: 
在 FastAPI 的业务逻辑层扮演“调度中枢”（RecommendService）。将上面三个兵种独立产出的结果（不同比例的得分），汇总到一个 DataFrame 中，实施标准加权操作。

**代码实现架构**:
1. **多路并发召回**（提高接口响应速度）：
   使用 Python 的 `asyncio.gather`，同时去调用底层的 PPR查询、Content查表、CF推荐模块。
   如果某个通道崩溃或者超时（比如 Neo4j 短暂卡死），捕获异常，容许降级（缺少一路分数并不影响最终排行）。
2. **归一化大融合**（Pandas 内存操作）：
   ```python
   # 准备三个带打分的 DataFrame 并进行外连接（Outer Join）
   df_hybrid = df_ppr.merge(df_content, on='movie_id', how='outer')
   df_hybrid = df_hybrid.merge(df_cf, on='movie_id', how='outer')
   # 有些电影可能 CF 推了但 PPR 没推，没分数的地方算作 0 分
   df_hybrid.fillna(0, inplace=True)
   
   # 定义加权权重 (可以在配置里灵活动态调优)
   w_ppr, w_content, w_cf = 0.3, 0.3, 0.4
   df_hybrid['final_score'] = (
       df_hybrid['ppr_score'] * w_ppr +
       df_hybrid['content_score'] * w_content +
       df_hybrid['cf_score'] * w_cf
   )
   ```
3. 取出 `final_score` 最高的 Top 10，然后去 MySQL 取出它们的海报、标题，封装成 JSON 返回给 Vue3 前端渲染推荐卡片。

