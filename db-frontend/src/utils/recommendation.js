export const ALGORITHM_OPTIONS = [
    {
        value: "cfkg",
        label: "CFKG",
        description: "以用户-电影交互和电影知识图谱联合建模的主推荐链路。",
    },
    {
        value: "cf",
        label: "图协同过滤",
        description: "根据相似用户的高分行为推荐电影。",
    },
    {
        value: "content",
        label: "图内容推荐",
        description: "根据导演、演员、类型等图谱内容相似性推荐。",
    },
    {
        value: "ppr",
        label: "PPR",
        description: "通过图谱随机游走发现隐性关联电影。",
    },
];

export const ALGORITHM_LABELS = {
    hybrid: "混合推荐",
    ...Object.fromEntries(ALGORITHM_OPTIONS.map((item) => [item.value, item.label])),
};

export const SOURCE_ALGORITHM_LABELS = {
    cfkg: "CFKG",
    hybrid: "混合推荐",
    cf: "图协同过滤",
    content: "图内容推荐",
    ppr: "PPR",
    profile: "画像匹配",
};

export const SOURCE_ALGORITHM_COLORS = {
    cfkg: "linear-gradient(90deg, #00b51d, #3dd56d)",
    hybrid: "linear-gradient(90deg, #4f46e5, #7c3aed)",
    cf: "linear-gradient(90deg, #0f766e, #14b8a6)",
    content: "linear-gradient(90deg, #ca8a04, #f59e0b)",
    ppr: "linear-gradient(90deg, #2563eb, #60a5fa)",
    profile: "linear-gradient(90deg, #1f2937, #6b7280)",
};

export const GENERATION_MODE_LABELS = {
    profile: "画像推荐",
    cold_start: "冷启动兜底",
};

export const RECOMMENDATION_EMPTY_FEEDBACK = {
    is_liked: false,
    is_want_to_watch: false,
};

export const formatAlgorithmLabel = (algorithm) =>
    ALGORITHM_LABELS[algorithm] || algorithm;

export const formatSourceAlgorithmLabel = (algorithm) =>
    SOURCE_ALGORITHM_LABELS[algorithm] || algorithm;

export const getSourceAlgorithmColor = (algorithm) =>
    SOURCE_ALGORITHM_COLORS[algorithm] ||
    "linear-gradient(90deg, #64748b, #94a3b8)";

export const formatGenerationModeLabel = (generationMode) =>
    GENERATION_MODE_LABELS[generationMode] || "推荐模式";

export const formatScore = (score) =>
    Number.isFinite(Number(score)) ? Number(score).toFixed(3) : "--";
