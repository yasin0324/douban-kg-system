# 知识图谱与推荐系统技术文档

**版本**: v2.1  
**最后更新**: 2026-03-09  
**适用范围**: 当前已落地的推荐系统实现（`db-backend/app/services/recommend_service.py` + `db-frontend/src/views/HomeView.vue` + `db-frontend/src/views/RecommendView.vue`）

---

## 1. 当前推荐系统总览

当前系统采用“用户画像驱动 + 知识图谱计算 + 可解释前端展示”的推荐架构，核心不再是“前端手工指定 1-5 部种子电影”，而是：

1. 后端从用户的全部行为中构建画像。
2. 将画像映射为图谱中的电影上下文、类型偏好、导演偏好、演员偏好、地区语言偏好与弱负反馈约束。
3. 线上主链路默认走 `CFKG`，并以 `CF / Content` 召回和知识图谱嵌入重排为核心。
4. 研究/对照层同时保留 `ItemCF / TF-IDF / CF / Content / PPR / Hybrid / CFKG` 七种算法。
5. 前端首页与推荐页不展示“依据哪些电影”，只展示画像标签、推荐结果和解释入口。
6. 解释抽屉中允许回指少量“代表兴趣电影”，并配合证据小图展示图谱解释路径或基线解释信号。

这套方案仍然严格属于“基于豆瓣电影知识图谱的电影推荐系统”，因为：

- 画像不是脱离图谱单独算分，而是被投影到 `Movie / Person / Genre` 图结构上参与召回与重排。
- `Content` 和 `PPR` 直接在图谱实体关系上运行。
- `CF` 依赖 Neo4j 中的 `User -[RATED]-> Movie` 评分图做邻域传播。
- `Hybrid` 融合的也是三条图原生分支。
- `CFKG` 在此基础上进一步把用户行为与知识图谱嵌入到同一条主推荐链路中。

---

## 2. 用户画像构建

### 2.1 行为来源

当前画像同时纳入三类行为：

- 评分 `user_movie_ratings`
- 喜欢 `user_movie_prefs.pref_type = like`
- 想看 `user_movie_prefs.pref_type = want_to_watch`

多种行为对同一电影采用**叠加计算**，不会互相覆盖。

### 2.2 评分语义

系统当前采用 5 分制的如下解释：

| 行为 | 语义 | 画像作用 |
| ---- | ---- | -------- |
| `4.0 - 5.0` | 强正反馈 | 高权重正向兴趣 |
| `3.5` | 弱正反馈 | 低于高分、但仍纳入正向兴趣 |
| `3.0` 及以下 | 弱负反馈 | 同时参与画像构建与排序降权 |

### 2.3 行为优先级

正向强度按如下顺序理解：

`强正评分 > 喜欢 > 弱正评分 > 想看`

其中：

- `喜欢` 代表明确正向偏好，权重高于 `3.5` 评分。
- `想看` 同时承担“弱正反馈 + 轻探索信号”的双重作用。
- 低分/差评是**弱负反馈**，会降权但不做强惩罚。

### 2.4 过滤规则

当前线上推荐对已交互电影的处理规则为：

- 已评分电影：排除
- 已喜欢电影：排除
- 仅想看电影：**不排除**，允许再次被推荐

这样做的原因是：

- 评分和喜欢通常代表“已经消费过或强确认过”；
- 想看更多是一种兴趣声明，重复出现仍然合理。

### 2.5 画像输出结构

后端在 `build_user_recommendation_profile()` 中生成以下核心字段：

- `movie_feedback`
- `positive_movie_ids`
- `negative_movie_ids`
- `context_movie_ids`
- `graph_context_movie_ids`
- `representative_movie_ids`
- `hard_exclude_movie_ids`
- `summary`

再结合 Neo4j 中的电影实体特征构造：

- `positive_features`
- `negative_features`
- `exploration_features`
- `positive_years`
- `positive_ratings`
- `content_type_counter`
- `feature_labels`
- `profile_highlights`

其中 `profile_highlights` 会直接返回给前端，用于首页/推荐页展示“画像标签”。

---

## 3. 当前线上链路与研究对照算法

### 3.1 CFKG: 当前线上默认主链路

当前 `/api/recommend/personal` 默认算法已经切换为 `cfkg`，首页与推荐页也固定使用这条链路。

实现上，`CFKG` 采用两阶段策略：

1. 先用 `CF` 召回为主、`Content` 补齐的候选池。
2. 再使用知识图谱嵌入模型做排序，并可接入轻量 reranker。

这使得主链路兼顾：

- 用户行为协同信号
- 知识图谱实体关系
- 嵌入空间中的隐性语义关联

### 3.2 图谱算法分支：CF / Content / PPR / Hybrid

除 `CFKG` 外，系统仍保留四类图谱推荐分支，主要用于实验对照与解释：

- `CF`：基于 Neo4j `User -[RATED]-> Movie` 图做相似用户传播。
- `Content`：基于类型、导演、演员等图谱实体命中召回，再结合画像重排。
- `PPR`：从画像派生的上下文电影出发，在图上做 Personalized PageRank。
- `Hybrid`：融合 `CF / Content / PPR` 三条图原生分支，并保留 `source_algorithms` 与 `score_breakdown`。

其中：

- `Content` 与 `PPR` 直接运行在知识图谱实体关系上。
- `CF` 使用的是图数据库中的评分图，而不是离线黑盒矩阵。
- `Hybrid` 用于说明“多策略融合”相对单一图算法的收益。

### 3.3 传统对照基线：ItemCF / TF-IDF

为满足论文实验对照要求，系统新增两类传统基线：

- `ItemCF`：只基于用户正向行为共现关系做物品协同过滤，不依赖知识图谱结构。
- `TF-IDF`：只基于电影标题、类型、地区、语言、导演、演员、简介等文本/元数据做内容相似度推荐。

这两类基线的定位是：

- 进入后端接口与离线评估，方便论文统一比较。
- 不进入首页/推荐页默认入口，避免影响当前产品主链路表达。
- 解释接口仍返回统一结构，但解释语义分别变为“协同用户信号”和“共享文本特征”。

---

## 4. 冷启动、重刷与多样性策略

### 4.1 冷启动

当前冷启动判定基于画像摘要中的行为数量与正向兴趣电影数量。

当行为不足时：

- `cfkg` 使用统一冷启动兜底
- 单算法尽量保留自身风格的 fallback
  - `cf`: 大众高分行为兜底
  - `content`: 类型特征清晰、评分稳定的电影
  - `ppr`: 图谱连接度较高的电影
  - `itemcf` / `tfidf`: 若历史行为或文本信号不足，则直接返回空结果并标记冷启动，不偷偷切到其他算法

前端会明确展示“当前仍处于冷启动阶段”的提示，不会把兜底结果伪装成成熟个性化推荐。

### 4.2 重新生成推荐

用户要求“重新生成”后的结果与上一批重合度偏低，因此当前实现采用了两层策略：

1. **前端浏览器侧短期记忆**
   - 当前浏览器 / 当前设备
   - 30 分钟有效
   - 每个算法独立维护一份最近展示记录
   - 仅在用户主动点击“重新生成”时，才会传给后端避让

2. **后端受控探索重排**
   - 接收 `exclude_movie_ids`
   - 接收 `reroll_token`
   - 在候选池中做“相关性 + 多样性 + 轻随机扰动”重排

因此首页预览和推荐页都能做到：

- 首次加载保持稳定
- 主动刷新时低重合度
- 不同算法之间相互独立

---

## 5. 当前 API 契约

### 5.1 个性化推荐

`GET /api/recommend/personal`

参数：

- `algorithm`: `cfkg | hybrid | cf | content | ppr | itemcf | tfidf`
- `limit`: `1 - 50`
- `exclude_movie_ids`: 可选，重新生成时尽量避开的电影
- `reroll_token`: 可选，刷新请求的随机标识

响应核心字段：

```json
{
  "algorithm": "cfkg",
  "cold_start": false,
  "generation_mode": "profile",
  "profile_summary": {
    "rating_count": 12,
    "likes": 6,
    "wants": 8,
    "positive_movie_count": 14
  },
  "profile_highlights": [
    { "type": "genre", "label": "科幻" },
    { "type": "director", "label": "克里斯托弗·诺兰" }
  ],
  "items": [
    {
      "movie": {
        "mid": "1292720",
        "title": "阿甘正传",
        "rating": 9.5,
        "year": 1994,
        "cover": "https://...",
        "genres": ["剧情", "爱情"]
      },
      "score": 1.284,
      "reasons": ["命中偏好类型 剧情", "相似用户也明显偏好这部电影"],
      "source_algorithms": ["cf", "content"],
      "negative_signals": [],
      "score_breakdown": {
        "cf": 0.73,
        "content": 0.41
      }
    }
  ]
}
```

### 5.2 推荐解释

`GET /api/recommend/explain`

参数：

- `target_mid`
- `algorithm`

说明：

- 需要登录
- 不再要求前端传种子电影
- 后端会自动根据当前用户画像选取少量 `representative_movies`

响应核心字段：

- `representative_movies`
- `profile_highlights`
- `profile_reasons`
- `negative_signals`
- `nodes`
- `edges`
- `reason_paths`
- `matched_entities`

---

## 6. 前端展示策略

### 6.1 首页

首页推荐区当前已落地为“CFKG 个性化推荐预览”：

- 已登录用户显示真实个性化推荐
- 未登录用户显示登录引导 + 热门样本
- 展示画像标签、行为摘要、冷启动状态
- 不展示“依据哪些电影”

### 6.2 推荐页

推荐页当前已落地为推荐中心：

- 默认链路：`CFKG`
- 状态卡：显示画像摘要、推荐模式、结果数
- 重新生成：按算法独立刷新
- 推荐卡片：支持 `喜欢 / 想看 / 去评分`

说明：

- 后端接口保留多算法参数，便于实验与调试。
- 但前端主页面不再暴露多算法切换，避免把论文对照算法混入默认产品体验。

### 6.3 解释抽屉

解释抽屉采用三层信息组织：

1. 推荐理由
2. 关系可视化小图
3. 算法指标

其中：

- 主界面不展示依据电影
- 抽屉允许展示少量代表兴趣电影
- 弱负反馈只在“算法指标”区域展示，不放在主解释区

---

## 7. 与知识图谱主题的关系

本系统没有从“知识图谱推荐”偏题到“纯行为推荐”，原因如下：

1. 用户画像最终被投影为图谱中的电影、类型、导演、演员、地区、语言等实体偏好。
2. Content 与 PPR 的候选发现完全依赖 Neo4j 图结构。
3. CF 使用的是 Neo4j 中的用户-电影评分图，而非脱离图谱的离线黑盒模型。
4. 解释模块返回的是电影、影人、类型等图节点和关系边，能直接展示证据链。

因此，当前架构相较于“前端显式手选种子电影”的版本，更贴近“知识图谱 + 用户画像”的综合推荐表达。

---

## 8. 当前实现与离线评估的说明

线上主链路已经完全采用画像驱动。

当前离线评估也已经统一切换为“画像驱动 + 时间切分”协议：

- 历史窗口使用评分、喜欢、想看共同构建画像
- 未来窗口只将 `rating >= 4.0` 与 `like` 视为主相关真值
- 统一比较 `ItemCF / TF-IDF / CF / Content / PPR / Hybrid / CFKG`
- 输出 `Precision@10 / Recall@10 / NDCG@10 / Coverage / User Coverage / Diversity`

评估脚本与报告输出：

- 脚本：`db-backend/scripts/evaluate_recommendations.py`
- JSON 报告：`db-backend/reports/recommendation_eval_latest.json`
- Markdown 报告：`db-backend/reports/recommendation_eval_latest.md`

---

## 9. 结论

截至 2026-03-09，推荐系统已经从“种子电影驱动的实验接口”升级为“用户画像驱动、以 CFKG 为默认主链路、并保留多算法实验对照”的推荐系统。

当前版本的技术特征可以概括为：

- 线上默认链路为 `CFKG`
- 研究对照算法扩展为 `ItemCF / TF-IDF / CF / Content / PPR / Hybrid / CFKG`
- 正负反馈同时参与
- 主页面不暴露种子概念
- 抽屉保留代表兴趣电影与图谱证据链
- 支持冷启动、动态降级与低重合度重刷
- 离线评估协议已经与线上画像逻辑对齐
- 保持与“基于豆瓣电影知识图谱的电影推荐系统”这一课题主题强一致
