# 知识图谱与推荐系统技术文档

## 推荐算法融合方案 (Phase 5 - Graph-Native)

本系统将实现完全基于知识图谱 (Graph-Native) 的 PPR + Content + CF + Hybrid 四种算法架构。核心目标是全盘摒弃脱离图属性的传统 ML 矩阵计算，将所有数据挖掘逻辑下沉到 Neo4j 拓扑网络中，打造纯正的“基于知识图谱的综合推荐系统”。

---

### 1. PPR (Personalized PageRank) 算法详解与实施

**核心原理**:
基于知识图谱拓扑结构进行随机游走。从用户偏好的节点（种子节点）出发，沿着边（演员、导演、类型）随机跳转，并以固定概率（如 0.15）跳回种子节点。多次迭代后，各节点的访问概率趋于稳定，概率越高的节点（电影）推荐优先级越高。它可以深层挖掘“相似导演拍摄的相似类型电影”这种隐性结构关联。

**准备工作**:

1. 确保 Neo4j 图数据库已启动并存储了高质量的 Movie, Person (Actor/Director), Genre 节点及它们之间的关系连边。
2. （可选但推荐）安装 Neo4j 的 GDS (Graph Data Science) 官方插件，这会让图算法在千级节点时的计算速度达到毫秒级。如果不安装 GDS，也可以用 Python 的 NetworkX 或基于 `apoc` 过程在内存中近似实现。

**代码实现步骤**:

1. 接收前端传来的 1 个或多个目标 `movie_ids` 作为种子节点。
2. 在后端通过 Python Driver 执行 Cypher 查询。

    ```cypher
    // 1. 投射独立网络图
    CALL gds.graph.project(
      'ppr_graph',
      ['Movie', 'Person', 'Genre'],
      ['ACTED_IN', 'DIRECTED', 'HAS_GENRE']
    )

    // 2. 游走计算
    CALL gds.pageRank.stream('ppr_graph', {
      sourceNodes: $seed_nodes,
      dampingFactor: 0.85
    })
    YIELD nodeId, score
    RETURN gds.util.asNode(nodeId).name AS name, score
    ORDER BY score DESC LIMIT 50

    // 3. 释放内存
    CALL gds.graph.drop('ppr_graph', false)
    ```

3. 过滤掉用户已经看过的电影，过滤掉非 Movie 节点。
4. 返回归一化得分给 Hybrid 统筹中心。

---

### 2. 基于图内容的推荐 (Graph-Content-Based) 详解与实施

**核心原理**:
替代传统基于长文本的 TF-IDF 运算。直接通过 Neo4j 图谱中的**共享实体路径**来衡量内容相似度。即：寻找与目标电影共享最多导演(Director)、核心演员(Actor)、编剧(Writer)和流派(Genre)的其他电影。

**突出优势**:
天然具备**极强的推荐可解释性**，这正是知识图谱的灵魂所在。我们可以提取共享路径作为 `reason` 返回给前端渲染。

**代码实现步骤**:

1. 基于用户近期高分的种子电影，利用 Cypher 查找与之存在强属性连通的图元。
2. 典型的查询模式：
    ```cypher
    MATCH (source:Movie {douban_id: $seed_id})-[:DIRECTED_BY|HAS_GENRE|ACTED_IN]->(shared_node)<-[:DIRECTED_BY|HAS_GENRE|ACTED_IN]-(target:Movie)
    WHERE NOT target.douban_id IN $watched_ids
    WITH target, count(shared_node) AS shared_count, collect(shared_node.name) AS shared_reasons
    RETURN target.douban_id AS movie_id, shared_count, shared_reasons
    ORDER BY shared_count DESC
    LIMIT 50
    ```
3. 后端 Python 拿到 `shared_reasons` 即可封装诸如：“因为都属于 科幻 流派且有 克里斯托弗·诺兰 参与”的自然语言理由。

---

### 3. 基于图拓扑的协同过滤 (Graph-Collaborative-Filtering)

**核心原理**:
告别 `surprise` 里的 SVD 矩阵分解。利用大语言模型（LLM）生成的具有强偏好逻辑的仿真用户打分数据，直接将 `User` 节点和附带了属性的 `[RATED {rating: score}]` 关系连边编织到 Neo4j 中。基于拓扑连接计算 UserCF 或 ItemCF。

**准备工作**:

1. 编写独立 Python 脚本调用大模型 API（如 Kimi），通过构造设定（例如：科幻迷、文艺青年等），生成 1 万条逻辑自洽的评分记录。
2. 存入 MySQL (`MovieRating` 表) 的同时，执行 Cypher **落入 Neo4j**。

**代码实现步骤**:

1. **拓扑查询 (UserCF 例)**：查找同样喜欢种子电影的相似用户，并抓取他们给出好评的其他电影。
    ```cypher
    // 找给目标电影打出高分的相似用户
    MATCH (u1:User {id: $target_user})-[:RATED {rating: 5}]->(m:Movie)<-[:RATED {rating: 5}]-(u2:User)
    // 找这些相似用户打过高分的其他电影
    WITH u2, count(m) AS similarity
    ORDER BY similarity DESC LIMIT 10
    MATCH (u2)-[r:RATED]->(rec:Movie)
    WHERE r.rating >= 4 AND NOT (u1)-[:RATED]->(rec)
    RETURN rec.douban_id AS movie_id, sum(r.rating * similarity) AS cf_score
    ORDER BY cf_score DESC LIMIT 50
    ```
2. **“活”的推荐池**：随着真实用户数据录入系统，Neo4j 中的 RATED 边会实时增加，Graph-CF 的查询拓扑结构瞬间自适应，彻底避免了传统机器学习“重新跑批训练模型”的开销。

---

### 4. 纯图谱混合调度器 (Graph-Hybrid Manager) 的最终实现

**核心原理**:
在 FastAPI 业务层作为一个调度与归一化聚合网关。收集这三股皆由 Neo4j 计算完成的召回流，结合设定的领域权重，吐出 Top N 综合排行。

**实施框架**:

1. 并发调度：使用 `asyncio.gather` 为这 3 路算法发送对 Neo4j 的不同 Cypher 请求。
2. 内存归一聚合（归总到统一数值区间 [0, 1]）：由于这三条路的得分基准截然不同（PPR 是极小的概率值，Graph-Content 是共享实体个数，CF 是叠加分数），因此必须先各自 Min-Max 归一化。
3. 加权计分：
    ```python
    # 代码示意
    final_score = (
        norm_ppr_score * 0.3 +
        norm_content_score * 0.3 +
        norm_cf_score * 0.4
    )
    ```
4. 综合结果的响应负载：
    ```json
    {
        "movie_id": "xxx",
        "final_score": 0.89,
        "reasons": ["与《星际穿越》共享导演", "124位品味相投的用户也喜欢"]
    }
    ```
