export const ALGORITHM_OPTIONS = [
    {
        value: "cfkg",
        label: "CFKG 主链路",
        type: "KG",
        description: "协同过滤召回后结合知识图谱重排与解释的主推荐链路。",
    },
    {
        value: "kg_path",
        label: "KG 路径推荐",
        type: "KG",
        description: "在知识图谱中通过多跳路径发现关联电影。",
    },
    {
        value: "kg_embed",
        label: "KG 嵌入推荐",
        type: "KG",
        description: "基于 TransE 嵌入的语义相似性推荐。",
    },
    {
        value: "content",
        label: "基于内容推荐",
        type: "基线",
        description: "根据电影类型、地区、年代等元数据特征推荐。",
    },
    {
        value: "item_cf",
        label: "协同过滤推荐",
        type: "基线",
        description: "根据评分行为相似性推荐电影。",
    },
];

export const ALGORITHM_LABELS = {
    ...Object.fromEntries(ALGORITHM_OPTIONS.map((item) => [item.value, item.label])),
};

export const SOURCE_ALGORITHM_LABELS = {
    cfkg: "CFKG 主链路",
    kg_path: "KG 路径",
    kg_embed: "KG 嵌入",
    content: "内容推荐",
    item_cf: "协同过滤",
};

export const formatAlgorithmLabel = (algorithm) =>
    ALGORITHM_LABELS[algorithm] || algorithm;

export const formatSourceAlgorithmLabel = (algorithm) =>
    SOURCE_ALGORITHM_LABELS[algorithm] || algorithm;

export const formatScore = (score) =>
    Number.isFinite(Number(score)) ? Number(score).toFixed(3) : "--";
