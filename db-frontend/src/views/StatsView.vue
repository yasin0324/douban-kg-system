<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from "vue";
import { useRouter } from "vue-router";
import * as echarts from "echarts";
import { statsApi } from "@/api/stats";
import { useThemeStore } from "@/stores/theme";

const router = useRouter();
const themeStore = useThemeStore();

const loading = ref(true);
const overview = ref(null);

const genreChartRef = ref(null);
const yearChartRef = ref(null);
const ratingChartRef = ref(null);
const genreYearChartRef = ref(null);
const ratingYearChartRef = ref(null);

let chartInstances = [];
// 保存原始数据用于主题切换后重绘
let cachedData = {};

// 主题色
const getChartTheme = () => {
    const isDark = themeStore.isDark;
    return {
        textColor: isDark ? "#a0a0b0" : "#6e6e73",
        titleColor: isDark ? "#e8e8e8" : "#1d1d1f",
        bgColor: "transparent",
        splitLineColor: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
        axisLineColor: isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)",
    };
};

const accentColors = [
    "#00b51d",
    "#2563eb",
    "#f59e0b",
    "#ef4444",
    "#8b5cf6",
    "#06b6d4",
    "#ec4899",
    "#10b981",
    "#f97316",
    "#6366f1",
];

// 加载所有数据
onMounted(async () => {
    loading.value = true;
    try {
        const [
            overviewRes,
            genreRes,
            yearRes,
            ratingRes,
            genreYearRes,
            ratingYearRes,
        ] = await Promise.all([
            statsApi.getOverview(),
            statsApi.getGenreDistribution(),
            statsApi.getYearDistribution(),
            statsApi.getRatingDistribution(),
            statsApi.getGenreYearTrends(),
            statsApi.getRatingYearTrends(),
        ]);

        overview.value = overviewRes.data;
        // 缓存原始数据
        cachedData = {
            genre: genreRes.data,
            year: yearRes.data,
            rating: ratingRes.data,
            genreYear: genreYearRes.data,
            ratingYear: ratingYearRes.data,
        };

        await nextTick();

        initGenreChart(cachedData.genre);
        initYearChart(cachedData.year);
        initRatingChart(cachedData.rating);
        initGenreYearChart(cachedData.genreYear);
        initRatingYearChart(cachedData.ratingYear);
    } catch (err) {
        console.error("统计数据加载失败:", err);
    } finally {
        loading.value = false;
    }

    window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
    chartInstances.forEach((c) => c.dispose());
    chartInstances = [];
    window.removeEventListener("resize", handleResize);
});

// 监听主题切换，重新渲染所有图表
watch(
    () => themeStore.isDark,
    async () => {
        if (!cachedData.genre) return;
        // 销毁旧实例
        chartInstances.forEach((c) => c.dispose());
        chartInstances = [];
        await nextTick();
        initGenreChart(cachedData.genre);
        initYearChart(cachedData.year);
        initRatingChart(cachedData.rating);
        initGenreYearChart(cachedData.genreYear);
        initRatingYearChart(cachedData.ratingYear);
    },
);

const handleResize = () => {
    chartInstances.forEach((c) => c.resize());
};

const createChart = (domRef) => {
    if (!domRef) return null;
    const chart = echarts.init(domRef);
    chartInstances.push(chart);
    return chart;
};

// 格式化数字
const formatNum = (num) => {
    if (!num) return "0";
    if (num >= 10000) return (num / 10000).toFixed(1) + "万";
    return num.toLocaleString();
};

// ========== 1. 类型分布饼图 ==========
const initGenreChart = (data) => {
    const chart = createChart(genreChartRef.value);
    if (!chart) return;
    const t = getChartTheme();

    // 取 Top 15，其余合并
    const sorted = [...data].sort((a, b) => b.count - a.count);
    const top = sorted.slice(0, 15);
    const otherCount = sorted.slice(15).reduce((s, d) => s + d.count, 0);
    if (otherCount > 0) top.push({ genre: "其他", count: otherCount });

    chart.setOption({
        title: {
            text: "🏷️ 类型分布",
            left: "center",
            textStyle: { color: t.titleColor, fontSize: 16, fontWeight: 600 },
        },
        tooltip: {
            trigger: "item",
            formatter: "{b}: {c} ({d}%)",
        },
        legend: {
            type: "scroll",
            orient: "vertical",
            right: 10,
            top: 50,
            bottom: 20,
            textStyle: { color: t.textColor, fontSize: 12 },
        },
        color: accentColors,
        series: [
            {
                type: "pie",
                radius: ["35%", "65%"],
                center: ["40%", "55%"],
                avoidLabelOverlap: true,
                itemStyle: {
                    borderRadius: 6,
                    borderColor:
                        t.bgColor === "transparent" ? undefined : t.bgColor,
                    borderWidth: 2,
                },
                label: { show: false },
                emphasis: {
                    label: { show: true, fontSize: 14, fontWeight: "bold" },
                },
                data: top.map((d) => ({
                    name: d.genre,
                    value: d.count,
                })),
            },
        ],
    });
};

// ========== 2. 年代分布折线图 ==========
const initYearChart = (data) => {
    const chart = createChart(yearChartRef.value);
    if (!chart) return;
    const t = getChartTheme();

    // 过滤无效年份，聚合到 10 年区间
    const validData = data.filter(
        (d) => d.year && d.year >= 1900 && d.year <= 2030,
    );

    chart.setOption({
        title: {
            text: "📅 年代分布",
            left: "center",
            textStyle: { color: t.titleColor, fontSize: 16, fontWeight: 600 },
        },
        tooltip: {
            trigger: "axis",
            formatter: "{b}年: {c} 部",
        },
        grid: { left: 60, right: 20, top: 50, bottom: 40 },
        xAxis: {
            type: "category",
            data: validData.map((d) => d.year),
            axisLabel: {
                color: t.textColor,
                rotate: 45,
                interval: Math.floor(validData.length / 15),
            },
            axisLine: { lineStyle: { color: t.axisLineColor } },
        },
        yAxis: {
            type: "value",
            name: "电影数",
            nameTextStyle: { color: t.textColor },
            axisLabel: { color: t.textColor },
            splitLine: { lineStyle: { color: t.splitLineColor } },
        },
        series: [
            {
                type: "line",
                data: validData.map((d) => d.count),
                smooth: true,
                symbol: "none",
                lineStyle: { width: 2, color: "#2563eb" },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: "rgba(37, 99, 235, 0.3)" },
                        { offset: 1, color: "rgba(37, 99, 235, 0.02)" },
                    ]),
                },
            },
        ],
    });
};

// ========== 3. 评分分布柱状图 ==========
const initRatingChart = (data) => {
    const chart = createChart(ratingChartRef.value);
    if (!chart) return;
    const t = getChartTheme();

    const sorted = [...data].sort((a, b) => a.rating - b.rating);

    chart.setOption({
        title: {
            text: "⭐ 评分分布",
            left: "center",
            textStyle: { color: t.titleColor, fontSize: 16, fontWeight: 600 },
        },
        tooltip: {
            trigger: "axis",
            formatter: "{b} 分: {c} 部",
        },
        grid: { left: 60, right: 20, top: 50, bottom: 40 },
        xAxis: {
            type: "category",
            data: sorted.map((d) => d.rating + " 分"),
            axisLabel: { color: t.textColor },
            axisLine: { lineStyle: { color: t.axisLineColor } },
        },
        yAxis: {
            type: "value",
            name: "电影数",
            nameTextStyle: { color: t.textColor },
            axisLabel: { color: t.textColor },
            splitLine: { lineStyle: { color: t.splitLineColor } },
        },
        series: [
            {
                type: "bar",
                data: sorted.map((d) => d.count),
                itemStyle: {
                    borderRadius: [4, 4, 0, 0],
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: "#f59e0b" },
                        { offset: 1, color: "#f97316" },
                    ]),
                },
                barMaxWidth: 40,
            },
        ],
    });
};

// ========== 8. 流派年代演变 (堆叠面积图) ==========
const initGenreYearChart = (data) => {
    const chart = createChart(genreYearChartRef.value);
    if (!chart) return;
    const t = getChartTheme();

    const genres = data.genres;
    const trends = data.trends;

    // Prepare years
    const yearSet = new Set(trends.map((d) => d.year));
    const years = Array.from(yearSet).sort();

    const series = genres.map((genre) => {
        const yearMap = new Map();
        trends
            .filter((d) => d.genre === genre)
            .forEach((d) => yearMap.set(d.year, d.count));
        return {
            name: genre,
            type: "line",
            stack: "Total",
            areaStyle: {},
            emphasis: { focus: "series" },
            data: years.map((y) => yearMap.get(y) || 0),
        };
    });

    chart.setOption({
        title: {
            text: "📈 主要流派年代演变",
            left: "center",
            textStyle: { color: t.titleColor, fontSize: 16, fontWeight: 600 },
        },
        tooltip: { trigger: "axis" },
        legend: {
            data: genres,
            bottom: 0,
            textStyle: { color: t.textColor },
        },
        grid: { left: 50, right: 30, top: 50, bottom: 60 },
        xAxis: {
            type: "category",
            boundaryGap: false,
            data: years,
            axisLabel: { color: t.textColor },
        },
        yAxis: {
            type: "value",
            axisLabel: { color: t.textColor },
            splitLine: { lineStyle: { color: t.splitLineColor } },
        },
        color: accentColors,
        series: series,
    });
};

// ========== 9. 评分年代变化 ==========
const initRatingYearChart = (data) => {
    const chart = createChart(ratingYearChartRef.value);
    if (!chart) return;
    const t = getChartTheme();

    chart.setOption({
        title: {
            text: "⭐ 评分年代演变趋势",
            left: "center",
            textStyle: { color: t.titleColor, fontSize: 16, fontWeight: 600 },
        },
        tooltip: { trigger: "axis", formatter: "{b}年: 平均 {c} 分" },
        grid: { left: 50, right: 30, top: 40, bottom: 40 },
        xAxis: {
            type: "category",
            data: data.map((d) => d.year),
            axisLabel: { color: t.textColor },
        },
        yAxis: {
            type: "value",
            min: "dataMin",
            axisLabel: { color: t.textColor },
            splitLine: { lineStyle: { color: t.splitLineColor } },
        },
        series: [
            {
                data: data.map((d) => d.avg_rating),
                type: "line",
                smooth: true,
                lineStyle: { width: 3, color: "#f59e0b" },
                itemStyle: { color: "#f59e0b" },
            },
        ],
    });
};
</script>

<template>
    <div class="stats-view container" v-loading="loading">
        <h1 class="page-title">📊 统计看板</h1>

        <!-- 概览卡片 -->
        <div class="overview-cards" v-if="overview">
            <div class="overview-card">
                <span class="ov-icon">🎬</span>
                <span class="ov-number">{{
                    formatNum(overview.movie_count)
                }}</span>
                <span class="ov-label">电影</span>
            </div>
            <div class="overview-card">
                <span class="ov-icon">🧑</span>
                <span class="ov-number">{{
                    formatNum(overview.person_count)
                }}</span>
                <span class="ov-label">影人</span>
            </div>
            <div class="overview-card">
                <span class="ov-icon">🏷️</span>
                <span class="ov-number">{{
                    formatNum(overview.genre_count)
                }}</span>
                <span class="ov-label">类型</span>
            </div>
            <div class="overview-card">
                <span class="ov-icon">🔗</span>
                <span class="ov-number">{{
                    formatNum(overview.relationship_count)
                }}</span>
                <span class="ov-label">关系</span>
            </div>
        </div>

        <div class="chart-grid">
            <div class="chart-card">
                <div ref="genreChartRef" class="chart-container"></div>
            </div>
            <div class="chart-card">
                <div ref="yearChartRef" class="chart-container"></div>
            </div>
            <div class="chart-card">
                <div ref="ratingChartRef" class="chart-container"></div>
            </div>
            <div class="chart-card">
                <div ref="ratingYearChartRef" class="chart-container"></div>
            </div>
            <div class="chart-card chart-card-tall full-width">
                <div ref="genreYearChartRef" class="chart-container-tall"></div>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.stats-view {
    padding-top: var(--space-xl);
    padding-bottom: var(--space-2xl);
}

.section-title {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: var(--space-lg);
    color: var(--text-color);
}

.mt-xl {
    margin-top: var(--space-2xl);
}

.full-width {
    grid-column: 1 / -1;
}

.overview-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-xl);
}

.overview-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-xs);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-lg) var(--space-md);
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--color-accent);
        box-shadow: var(--shadow-md);
        transform: translateY(-2px);
    }
}

.ov-icon {
    font-size: 2rem;
}

.ov-number {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--color-accent);
    line-height: 1.2;
}

.ov-label {
    font-size: 0.85rem;
    color: var(--text-muted);
}

.chart-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: var(--space-md);
}

.chart-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--border-color-light);
        box-shadow: var(--shadow-sm);
    }
}

.chart-container {
    width: 100%;
    height: 360px;
}

.chart-container-tall {
    width: 100%;
    height: 520px;
}

@media (max-width: 768px) {
    .overview-cards {
        grid-template-columns: repeat(2, 1fr);
    }

    .chart-grid {
        grid-template-columns: 1fr;
    }

    .chart-container {
        height: 300px;
    }

    .chart-container-tall {
        height: 420px;
    }
}
</style>
