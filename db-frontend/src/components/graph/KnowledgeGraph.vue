<script setup>
import { ref, watch, onMounted, onBeforeUnmount, computed } from "vue";
import * as echarts from "echarts";
import { useThemeStore } from "@/stores/theme";

const themeStore = useThemeStore();

const props = defineProps({
    nodes: { type: Array, default: () => [] },
    edges: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    highlightId: { type: String, default: "" },
    /** 隐藏的节点类型 */
    hiddenTypes: { type: Array, default: () => [] },
    /** 布局模式：force(力引导) / linear(线性路径) */
    layout: { type: String, default: "force" },
});

const emit = defineEmits(["node-click", "node-hover"]);

const chartRef = ref(null);
let chartInstance = null;
let resizeObserver = null;

// -- 节点类型颜色 --
const TYPE_COLORS = {
    Movie: "#409EFF",
    Person: "#67C23A",
    Genre: "#E6A23C",
    Unknown: "#909399",
};

// -- 关系类型中文标签 --
const REL_LABELS = {
    DIRECTED: "导演",
    ACTED_IN: "出演",
    HAS_GENRE: "类型",
};

// -- 计算连接数 --
const connectionCount = computed(() => {
    const count = {};
    props.edges.forEach((e) => {
        count[e.source] = (count[e.source] || 0) + 1;
        count[e.target] = (count[e.target] || 0) + 1;
    });
    return count;
});

// -- 构建 ECharts option --
const buildOption = () => {
    const hidden = new Set(props.hiddenTypes);

    // 过滤节点
    const visibleNodes = props.nodes.filter((n) => !hidden.has(n.type));
    const visibleIds = new Set(visibleNodes.map((n) => n.id));

    // 过滤边
    const visibleEdges = props.edges.filter(
        (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
    );

    // 连接数
    const conn = {};
    visibleEdges.forEach((e) => {
        conn[e.source] = (conn[e.source] || 0) + 1;
        conn[e.target] = (conn[e.target] || 0) + 1;
    });

    const echartsNodes = visibleNodes.map((n) => {
        const isCenter = n.id === props.highlightId;
        const rating = n.properties?.rating;
        const connections = conn[n.id] || 1;

        // 节点大小：中心节点最大，电影按评分，其他按连接数
        let size = 20;
        if (isCenter) {
            size = 55;
        } else if (n.type === "Movie" && rating) {
            size = 12 + rating * 2.5;
        } else {
            size = 12 + Math.min(connections, 20) * 1.5;
        }

        const color = TYPE_COLORS[n.type] || TYPE_COLORS.Unknown;

        return {
            id: n.id,
            name: n.label,
            symbolSize: size,
            category: n.type,
            itemStyle: {
                color: color,
                borderColor: isCenter
                    ? themeStore.isDark
                        ? "#fff"
                        : "#333"
                    : themeStore.isDark
                      ? "rgba(255,255,255,0.2)"
                      : "rgba(0,0,0,0.15)",
                borderWidth: isCenter ? 3 : 1,
                shadowBlur: isCenter ? 20 : 0,
                shadowColor: isCenter ? color : "transparent",
            },
            label: {
                show: isCenter || size > 25,
                fontSize: isCenter ? 14 : 11,
                color: themeStore.isDark ? "#e8e8e8" : "#1d1d1f",
                fontWeight: isCenter ? "bold" : "normal",
            },
            // 附加数据用于 tooltip 和 click
            _raw: n,
        };
    });

    // 合并同一对节点之间的多条边（如同时导演+出演），避免标签重叠
    const edgeMap = new Map();
    visibleEdges.forEach((e) => {
        const key = [e.source, e.target].sort().join("|");
        if (edgeMap.has(key)) {
            const existing = edgeMap.get(key);
            const newLabel = REL_LABELS[e.type] || e.type;
            if (!existing._labels.includes(newLabel)) {
                existing._labels.push(newLabel);
            }
        } else {
            edgeMap.set(key, {
                source: e.source,
                target: e.target,
                _labels: [REL_LABELS[e.type] || e.type],
                _relType: e.type,
            });
        }
    });

    const echartsEdges = Array.from(edgeMap.values()).map((e) => ({
        source: e.source,
        target: e.target,
        lineStyle: {
            color: themeStore.isDark
                ? "rgba(255,255,255,0.12)"
                : "rgba(0,0,0,0.15)",
            width: 1.5,
            curveness: 0.1,
        },
        label: {
            show: edgeMap.size <= 40,
            formatter: e._labels.join("/"),
            fontSize: 10,
            color: themeStore.isDark
                ? "rgba(255,255,255,0.4)"
                : "rgba(0,0,0,0.45)",
        },
        _relType: e._relType,
    }));

    // 类目（用于图例）
    const categories = ["Movie", "Person", "Genre"].map((t) => ({
        name: t === "Movie" ? "电影" : t === "Person" ? "影人" : "类型",
        itemStyle: { color: TYPE_COLORS[t] },
    }));

    // 将 category 映射为索引
    const categoryMap = { Movie: 0, Person: 1, Genre: 2 };
    echartsNodes.forEach((n) => {
        n.category = categoryMap[n._raw.type] ?? 0;
    });

    const isLinear = props.layout === "linear";

    return {
        backgroundColor: "transparent",
        tooltip: {
            trigger: "item",
            backgroundColor: themeStore.isDark
                ? "rgba(22,33,62,0.95)"
                : "rgba(255,255,255,0.95)",
            borderColor: themeStore.isDark
                ? "rgba(255,255,255,0.15)"
                : "rgba(0,0,0,0.12)",
            textStyle: {
                color: themeStore.isDark ? "#e8e8e8" : "#1d1d1f",
                fontSize: 13,
            },
            formatter: (params) => {
                if (params.dataType === "node") {
                    const raw = params.data._raw;
                    let html = `<strong style="font-size:14px">${raw.label}</strong>`;
                    const typeLabel =
                        raw.type === "Movie"
                            ? "🎬 电影"
                            : raw.type === "Person"
                              ? "🧑 影人"
                              : "🏷️ 类型";
                    const subColor = themeStore.isDark ? "#a0a0b0" : "#6e6e73";
                    html += `<br/><span style="color:${subColor}">${typeLabel}</span>`;
                    if (raw.properties?.rating) {
                        html += `<br/>⭐ 评分: ${raw.properties.rating}`;
                    }
                    if (raw.properties?.year) {
                        html += `<br/>📅 ${raw.properties.year}`;
                    }
                    if (raw.properties?.profession) {
                        html += `<br/>💼 ${raw.properties.profession}`;
                    }
                    return html;
                } else if (params.dataType === "edge") {
                    const label =
                        REL_LABELS[params.data._relType] ||
                        params.data._relType;
                    return `关系: ${label}`;
                }
                return "";
            },
        },
        legend: {
            show: false,
            data: categories.map((c) => c.name),
        },
        animationDuration: 800,
        animationEasingUpdate: "quinticInOut",
        series: [
            {
                type: "graph",
                layout: isLinear ? "none" : "force",
                data: echartsNodes,
                links: echartsEdges,
                categories: categories,
                roam: true,
                draggable: true,
                force: isLinear
                    ? undefined
                    : {
                          repulsion: echartsNodes.length > 80 ? 200 : 350,
                          gravity: 0.08,
                          edgeLength: echartsNodes.length > 80 ? 80 : 120,
                          friction: 0.6,
                          layoutAnimation: true,
                      },
                emphasis: {
                    focus: "adjacency",
                    itemStyle: {
                        borderWidth: 3,
                        borderColor: "#fff",
                        shadowBlur: 15,
                    },
                    lineStyle: {
                        width: 3,
                        color: themeStore.isDark
                            ? "rgba(255,255,255,0.5)"
                            : "rgba(0,0,0,0.4)",
                    },
                },
                label: {
                    position: "bottom",
                    distance: 5,
                },
                edgeLabel: {
                    position: "middle",
                },
            },
        ],
    };
};

// -- 线性布局：为路径节点计算 x/y 坐标 --
const applyLinearPositions = (option) => {
    const nodes = option.series[0].data;
    if (nodes.length === 0) return;
    const width = chartRef.value?.clientWidth || 800;
    const height = chartRef.value?.clientHeight || 500;
    const padding = 120;
    const usableWidth = width - padding * 2;
    const step = nodes.length > 1 ? usableWidth / (nodes.length - 1) : 0;

    nodes.forEach((n, i) => {
        n.x = padding + i * step;
        n.y = height / 2 + (i % 2 === 0 ? 0 : -40); // 轻微锯齿以避免重叠
        n.fixed = true;
    });
};

// -- 初始化/更新图表 --
const updateChart = () => {
    if (!chartRef.value) return;

    if (!chartInstance) {
        chartInstance = echarts.init(chartRef.value, null, {
            renderer: "canvas",
        });

        chartInstance.on("click", (params) => {
            if (params.dataType === "node" && params.data._raw) {
                emit("node-click", params.data._raw);
            }
        });

        chartInstance.on("mouseover", (params) => {
            if (params.dataType === "node" && params.data._raw) {
                emit("node-hover", params.data._raw);
            }
        });
    }

    const option = buildOption();

    if (props.layout === "linear") {
        applyLinearPositions(option);
    }

    chartInstance.setOption(option, true);
};

// -- Watch --
watch(
    () => [
        props.nodes,
        props.edges,
        props.hiddenTypes,
        props.highlightId,
        themeStore.isDark,
    ],
    updateChart,
    { deep: true },
);

// -- ResizeObserver --
onMounted(() => {
    updateChart();
    if (chartRef.value) {
        resizeObserver = new ResizeObserver(() => {
            chartInstance?.resize();
        });
        resizeObserver.observe(chartRef.value);
    }
});

onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    chartInstance?.dispose();
    chartInstance = null;
});
</script>

<template>
    <div class="knowledge-graph-wrap">
        <div
            ref="chartRef"
            class="knowledge-graph-canvas"
            v-loading="loading"
            element-loading-text="加载图谱中..."
            :element-loading-background="
                themeStore.isDark
                    ? 'rgba(15,15,26,0.8)'
                    : 'rgba(255,255,255,0.8)'
            "
        ></div>

        <!-- 空状态 -->
        <div v-if="!loading && nodes.length === 0" class="graph-empty">
            <div class="empty-icon">🕸️</div>
            <p>暂无图谱数据</p>
        </div>
    </div>
</template>

<style scoped lang="scss">
.knowledge-graph-wrap {
    position: relative;
    width: 100%;
    height: 100%;
    min-height: 400px;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    overflow: hidden;
}

.knowledge-graph-canvas {
    width: 100%;
    height: 100%;
    min-height: 400px;
}

.graph-empty {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    color: var(--text-muted);

    .empty-icon {
        font-size: 3rem;
        margin-bottom: var(--space-md);
    }

    p {
        font-size: 1rem;
    }
}
</style>
