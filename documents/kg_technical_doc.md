# 知识图谱与推荐系统技术文档

## 推荐算法融合方案 (Phase 5)

本系统将实现 PPR + Content + CF + Hybrid 四种算法的融合，构建“基于知识图谱的综合推荐系统”。

### 1. 算法组件

1.  **PPR (Personalized PageRank)**
    *   **原理**: 基于知识图谱拓扑结构，从用户偏好的电影节点出发进行随机游走，发现多跳隐性关联（如同导演、同类型）。
    *   **适用场景**: 图谱结构密集、希望发现深层属性关联。
    *   **实现**: Neo4j Cypher / GDS 库。

2.  **内容过滤 (Content-Based)**
    *   **原理**: 基于电影的文本属性（核心是 `storyline` 剧情简介），计算相似度。
    *   **适用场景**: 解决内容高度相关的“同类片”推荐，突破仅图层面的结构限制。
    *   **实现**: `jieba` 分词 + `sklearn` TF-IDF + 建立余弦相似度矩阵。

3.  **协同过滤 (Collaborative Filtering - CF)**
    *   **原理**: 基于“相似用户偏好”的交叉推荐，提供惊喜感（Serendipity）。
    *   **数据来源 (核心亮点)**: 由于缺乏真实用户评分，引入 **大语言模型 (LLM)** 生成带有人设标签的 10 万+ 条逻辑自洽的模拟评分数据，解决系统冷启动。
    *   **实现**: `Pandas` / `Surprise` 库构建 User-Item 矩阵，计算 Item/User 相似度。

4.  **混合推荐 (Hybrid)**
    *   **原理**: 将上述三种召回通道的结果进行加权融合。
    *   **过程**:
        1. 归一化 (Min-Max) 三通道得分。
        2. 以 Pandas DataFrame 实现 Outer Join。
        3. 按动态权重 (如 PPR 30%, Content 30%, CF 40%) 计算最终得分并排序取 Top N。

### 2. 实施路径

*   **STEP 1**: 在 Neo4j 实现基础 PPR 查询 (无需额外依赖)。
*   **STEP 2**: 环境引入 `jieba`, `scikit-learn`，实现基于 `storyline` 的内容特征向量和相似度缓存。
*   **STEP 3**: 编写 Python 脚本调用 LLM API，生成模拟的 CF 评分集，落库 MySQL 并供 CF 模块离线运算。
*   **STEP 4**: 在 FastAPI 的 `recommend_service.py` 收口，拉取各路结果用 Pandas 合并并加权输出。
