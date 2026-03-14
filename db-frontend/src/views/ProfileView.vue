<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { usersApi } from "@/api/users";
import { moviesApi } from "@/api/movies";
import { ElMessage, ElMessageBox } from "element-plus";
import { proxyImage } from "@/utils/image";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import * as echarts from "echarts";
import "echarts-wordcloud";

const router = useRouter();
const authStore = useAuthStore();
const themeStore = useThemeStore();

// ==================== 偏好/评分列表 ====================
const activeTab = ref("like");
const loading = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 12;
const movieCache = ref({});

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIwIiBoZWlnaHQ9IjE4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTIwIiBoZWlnaHQ9IjE4MCIgZmlsbD0iIzFhMWEyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjMwIiBmaWxsPSIjNDA0MDYwIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

const fetchData = async () => {
    loading.value = true;
    items.value = [];
    try {
        let res;
        if (activeTab.value === "rating") {
            res = await usersApi.getRatings({ page: page.value, size: pageSize });
        } else {
            res = await usersApi.getPreferences({ pref_type: activeTab.value, page: page.value, size: pageSize });
        }
        items.value = res.data.items || [];
        total.value = res.data.total || 0;
        await fetchMovieInfoBatch(items.value);
    } catch (err) {
        console.error("加载数据失败:", err);
    } finally {
        loading.value = false;
    }
};

const fetchMovieInfoBatch = async (list) => {
    const mids = list.map((item) => item.mid).filter((mid) => !movieCache.value[mid]);
    const promises = mids.map((mid) =>
        moviesApi.getDetail(mid)
            .then((res) => { movieCache.value[mid] = res.data; })
            .catch(() => { movieCache.value[mid] = { mid, title: mid, cover: null }; }),
    );
    await Promise.allSettled(promises);
};

const getMovie = (mid) => movieCache.value[mid] || { mid, title: mid };

const refreshProfileSections = async () => {
    await Promise.all([fetchProfileAnalysis(), fetchProfileGraph()]);
};

const handleRemovePref = async (item) => {
    try {
        await ElMessageBox.confirm("确定要取消该标记吗？", "提示", { type: "warning" });
        await usersApi.removePreference(item.mid);
        ElMessage.success("已取消");
        await Promise.all([fetchData(), refreshProfileSections()]);
    } catch (err) {
        if (err !== "cancel") console.error(err);
    }
};

const handleRemoveRating = async (item) => {
    try {
        await ElMessageBox.confirm("确定要删除该评分吗？", "提示", { type: "warning" });
        await usersApi.removeRating(item.mid);
        ElMessage.success("已删除");
        await Promise.all([fetchData(), refreshProfileSections()]);
    } catch (err) {
        if (err !== "cancel") console.error(err);
    }
};

const handlePageChange = (p) => { page.value = p; fetchData(); };

const formatDate = (dateStr) => {
    if (!dateStr) return "";
    return new Date(dateStr).toLocaleDateString("zh-CN");
};

watch(activeTab, () => { page.value = 1; fetchData(); });

// ==================== 用户画像分析 ====================
const profileLoading = ref(false);
const profileData = ref(null);
const isColdStart = ref(false);

const radarChartRef = ref(null);
const wordCloudRef = ref(null);

let radarChart = null;
let wordCloudChart = null;
let profileResizeObserver = null;

const fetchProfileAnalysis = async () => {
    profileLoading.value = true;
    try {
        const res = await usersApi.getProfileAnalysis();
        profileData.value = res.data;
        const s = res.data.summary || {};
        isColdStart.value = s.cold_start ?? (s.effective_signal_count ?? 0) < 3;
        if (!isColdStart.value) {
            nextTick(() => renderCharts());
        }
    } catch (err) {
        console.error("加载画像数据失败:", err);
    } finally {
        profileLoading.value = false;
    }
};

const renderCharts = () => {
    renderRadarChart();
    renderWordCloud();
    setupResizeObserver();
};

const chartTextColor = () => themeStore.isDark ? "#ccc" : "#333";
const chartAxisColor = () => themeStore.isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.1)";

const renderRadarChart = () => {
    if (!radarChartRef.value || !profileData.value?.genre_distribution?.length) return;
    if (!radarChart) radarChart = echarts.init(radarChartRef.value);

    const top8 = profileData.value.genre_distribution.slice(0, 8);
    const maxVal = Math.max(...top8.map((g) => g.count), 1);

    radarChart.setOption({
        backgroundColor: "transparent",
        tooltip: {},
        radar: {
            indicator: top8.map((g) => ({ name: g.genre, max: maxVal })),
            shape: "polygon",
            splitArea: { areaStyle: { color: "transparent" } },
            axisLine: { lineStyle: { color: chartAxisColor() } },
            splitLine: { lineStyle: { color: chartAxisColor() } },
            axisName: { color: chartTextColor(), fontSize: 12 },
        },
        series: [{
            type: "radar",
            data: [{
                value: top8.map((g) => g.count),
                name: "观影类型",
                areaStyle: { opacity: 0.25 },
                lineStyle: { width: 2 },
            }],
        }],
    });
};

const TAG_COLORS = {
    genre: "#e6a23c",
    director: "#409eff",
    actor: "#67c23a",
};

const renderWordCloud = () => {
    if (!wordCloudRef.value || !profileData.value?.tag_cloud?.length) return;
    if (!wordCloudChart) wordCloudChart = echarts.init(wordCloudRef.value);

    const data = profileData.value.tag_cloud.map((item) => ({
        name: item.text,
        value: item.weight,
        textStyle: {
            color: TAG_COLORS[item.type] || "#909399",
        },
    }));

    wordCloudChart.setOption({
        backgroundColor: "transparent",
        tooltip: {
            show: true,
            formatter: (params) => `${params.name}: ${params.value}`,
        },
        series: [{
            type: "wordCloud",
            shape: "circle",
            left: "center",
            top: "center",
            width: "90%",
            height: "90%",
            sizeRange: [14, 52],
            rotationRange: [-30, 30],
            rotationStep: 15,
            gridSize: 10,
            drawOutOfBound: false,
            layoutAnimation: true,
            textStyle: {
                fontFamily: "system-ui, -apple-system, sans-serif",
                fontWeight: "bold",
            },
            emphasis: {
                textStyle: {
                    shadowBlur: 8,
                    shadowColor: "rgba(0,0,0,0.3)",
                },
            },
            data,
        }],
    });
};

const resizeAllCharts = () => {
    radarChart?.resize();
    wordCloudChart?.resize();
};

const setupResizeObserver = () => {
    if (profileResizeObserver) profileResizeObserver.disconnect();
    profileResizeObserver = new ResizeObserver(() => resizeAllCharts());
    if (radarChartRef.value) profileResizeObserver.observe(radarChartRef.value);
    if (wordCloudRef.value) profileResizeObserver.observe(wordCloudRef.value);
};

watch(() => themeStore.isDark, () => {
    nextTick(() => renderCharts());
});

// ==================== 用户画像图谱 ====================
const profileGraphNodes = ref([]);
const profileGraphEdges = ref([]);
const profileGraphMeta = ref(null);
const profileGraphLoading = ref(false);
const profileMovieLimit = ref(30);
const profileHoveredNode = ref(null);
const profileHiddenTypes = ref([]);
const profileTypeFilters = ref({ Movie: true, Person: true, Genre: true });

const profileTypeCounts = computed(() => {
    const counts = { Movie: 0, Person: 0, Genre: 0 };
    profileGraphNodes.value.forEach((n) => {
        if (counts[n.type] !== undefined) counts[n.type]++;
    });
    return counts;
});

const toggleProfileType = (type) => {
    profileTypeFilters.value[type] = !profileTypeFilters.value[type];
    profileHiddenTypes.value = Object.entries(profileTypeFilters.value)
        .filter(([, v]) => !v)
        .map(([k]) => k);
};

const fetchProfileGraph = async () => {
    profileGraphLoading.value = true;
    try {
        const res = await usersApi.getProfileGraph({ movieLimit: profileMovieLimit.value });
        profileGraphNodes.value = res.data.nodes || [];
        profileGraphEdges.value = res.data.edges || [];
        profileGraphMeta.value = res.data.meta || null;
    } catch (err) {
        console.error("加载画像图谱失败:", err);
        profileGraphNodes.value = [];
        profileGraphEdges.value = [];
    } finally {
        profileGraphLoading.value = false;
    }
};

const handleProfileGraphNodeClick = (node) => {
    if (node.type === "User" || node.type === "Genre") return;
    const idParts = node.id.split("_");
    const rawId = idParts.slice(1).join("_");
    if (node.type === "Movie") router.push(`/movies/${rawId}`);
    else if (node.type === "Person") router.push(`/persons/${rawId}`);
};

onMounted(() => {
    fetchData();
    fetchProfileAnalysis();
    fetchProfileGraph();
});

onBeforeUnmount(() => {
    profileResizeObserver?.disconnect();
    radarChart?.dispose();
    wordCloudChart?.dispose();
    radarChart = null;
    wordCloudChart = null;
});
</script>

<template>
    <div class="profile-view container">
        <!-- 用户信息卡片 -->
        <div class="user-card" v-if="authStore.user">
            <div class="user-avatar-large">
                <el-avatar :size="72">{{ authStore.user.username?.[0]?.toUpperCase() || "U" }}</el-avatar>
            </div>
            <div class="user-info">
                <h1 class="user-name">{{ authStore.user.nickname || authStore.user.username }}</h1>
                <p class="user-detail" v-if="authStore.user.nickname">@{{ authStore.user.username }}</p>
                <p class="user-detail" v-if="authStore.user.email">{{ authStore.user.email }}</p>
                <p class="user-detail" v-if="authStore.user.created_at">{{ formatDate(authStore.user.created_at) }} 注册</p>
            </div>
        </div>

        <!-- ==================== 偏好/评分列表 ==================== -->
        <div class="tabs-section">
            <el-tabs v-model="activeTab" class="profile-tabs">
                <el-tab-pane label="❤️ 喜欢" name="like" />
                <el-tab-pane label="📌 想看" name="want_to_watch" />
                <el-tab-pane label="⭐ 评分" name="rating" />
            </el-tabs>
        </div>

        <div class="items-list" v-loading="loading">
            <div v-if="items.length === 0 && !loading" class="empty-state">
                <p>暂无数据</p>
            </div>

            <div v-else class="item-grid">
                <div v-for="item in items" :key="item.id" class="item-card">
                    <div class="item-poster" @click="router.push(`/movies/${item.mid}`)">
                        <img :src="proxyImage(getMovie(item.mid).cover) || defaultCover"
                            :alt="getMovie(item.mid).title"
                            @error="(e) => (e.target.src = defaultCover)" />
                    </div>
                    <div class="item-info">
                        <h3 class="item-title" @click="router.push(`/movies/${item.mid}`)">
                            {{ getMovie(item.mid).title || item.mid }}
                        </h3>
                        <p class="item-meta">
                            <span v-if="getMovie(item.mid).rating" class="item-rating">
                                {{ getMovie(item.mid).rating?.toFixed(1) }}
                            </span>
                            <span v-if="getMovie(item.mid).year">{{ getMovie(item.mid).year }}</span>
                        </p>
                        <p v-if="activeTab === 'rating'" class="item-my-rating">
                            我的评分：<strong>{{ item.rating }}</strong>
                        </p>
                        <p class="item-date">
                            {{ formatDate(activeTab === "rating" ? item.rated_at : item.created_at) }}
                        </p>
                        <el-button size="small" type="danger" plain
                            @click="activeTab === 'rating' ? handleRemoveRating(item) : handleRemovePref(item)">
                            {{ activeTab === "rating" ? "删除评分" : "取消标记" }}
                        </el-button>
                    </div>
                </div>
            </div>

            <div class="pagination-wrap" v-if="total > pageSize">
                <el-pagination :current-page="page" :page-size="pageSize" :total="total"
                    layout="prev, pager, next" @current-change="handlePageChange" />
            </div>
        </div>

        <!-- ==================== 用户画像分析（移到列表下方） ==================== -->
        <div class="portrait-section" v-loading="profileLoading">
            <h2 class="section-title">观影画像</h2>

            <!-- 冷启动提示 -->
            <div class="cold-start-hint" v-if="isColdStart && !profileLoading">
                <div class="cold-start-icon">📊</div>
                <p class="cold-start-text">去评分更多电影，解锁你的观影画像</p>
                <p class="cold-start-sub">至少与 3 部电影互动后即可生成画像分析</p>
                <div class="cold-start-actions">
                    <el-button type="primary" @click="router.push('/movies/filter')">浏览电影库</el-button>
                    <el-button @click="router.push('/recommend')">查看推荐</el-button>
                </div>
            </div>

            <template v-if="profileData && !isColdStart">
                <!-- 统计概览卡片 -->
                <div class="profile-stat-cards">
                    <div class="profile-stat-card">
                        <div class="profile-stat-num accent">{{ profileData.summary.liked_count }}</div>
                        <div class="profile-stat-label">喜欢</div>
                    </div>
                    <div class="profile-stat-card">
                        <div class="profile-stat-num info">{{ profileData.summary.want_to_watch_count }}</div>
                        <div class="profile-stat-label">想看</div>
                    </div>
                    <div class="profile-stat-card">
                        <div class="profile-stat-num warning">{{ profileData.summary.rating_count }}</div>
                        <div class="profile-stat-label">评分</div>
                    </div>
                    <div class="profile-stat-card">
                        <div class="profile-stat-num rating">{{ profileData.summary.avg_rating }}</div>
                        <div class="profile-stat-label">平均分</div>
                    </div>
                </div>

                <!-- 图表区域：标签云 + 雷达图并排 -->
                <div class="charts-grid charts-grid-2col">
                    <!-- 兴趣标签云 -->
                    <div class="chart-card" v-if="profileData.tag_cloud?.length">
                        <h3 class="chart-title">
                            兴趣标签云
                            <span class="chart-legend">
                                <span class="tag-legend-item"><span class="tag-dot" style="background:#e6a23c"></span>类型</span>
                                <span class="tag-legend-item"><span class="tag-dot" style="background:#409eff"></span>导演</span>
                                <span class="tag-legend-item"><span class="tag-dot" style="background:#67c23a"></span>演员</span>
                            </span>
                        </h3>
                        <div ref="wordCloudRef" class="chart-canvas"></div>
                    </div>

                    <!-- 类型偏好雷达图 -->
                    <div class="chart-card" v-if="profileData.genre_distribution?.length">
                        <h3 class="chart-title">类型偏好</h3>
                        <div ref="radarChartRef" class="chart-canvas"></div>
                    </div>
                </div>

                <!-- 常看导演/演员 -->
                <div class="people-grid" v-if="profileData.top_directors?.length || profileData.top_actors?.length">
                    <div class="people-card" v-if="profileData.top_directors?.length">
                        <h3 class="chart-title">常看导演</h3>
                        <div class="people-list">
                            <div v-for="(d, idx) in profileData.top_directors" :key="d.pid" class="people-item"
                                @click="router.push(`/persons/${d.pid}`)">
                                <span class="people-rank">{{ idx + 1 }}</span>
                                <span class="people-name">{{ d.name }}</span>
                                <span class="people-meta">{{ d.count }} 部<template v-if="d.avg_rating"> · {{ d.avg_rating }}</template></span>
                            </div>
                        </div>
                    </div>
                    <div class="people-card" v-if="profileData.top_actors?.length">
                        <h3 class="chart-title">常看演员</h3>
                        <div class="people-list">
                            <div v-for="(a, idx) in profileData.top_actors" :key="a.pid" class="people-item"
                                @click="router.push(`/persons/${a.pid}`)">
                                <span class="people-rank">{{ idx + 1 }}</span>
                                <span class="people-name">{{ a.name }}</span>
                                <span class="people-meta">{{ a.count }} 部<template v-if="a.avg_rating"> · {{ a.avg_rating }}</template></span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 用户画像图谱 -->
                <div class="profile-graph-section">
                    <h3 class="chart-title">我的观影图谱</h3>
                    <p class="graph-hint">以你为中心，展示你交互过的电影及其关联的导演、演员和类型</p>

                    <div class="profile-graph-controls">
                        <div class="profile-control-group">
                            <span class="profile-control-label">电影上限: {{ profileMovieLimit }}</span>
                            <el-slider v-model="profileMovieLimit" :min="5" :max="100" :step="5"
                                style="width: 130px" @change="fetchProfileGraph" />
                        </div>
                        <div class="profile-control-group">
                            <span class="profile-control-label">图例</span>
                            <div class="profile-legend-toggles">
                                <button class="profile-legend-btn" :class="{ disabled: !profileTypeFilters.Movie }"
                                    @click="toggleProfileType('Movie')">
                                    <span class="profile-legend-dot" style="background:#409eff"></span>
                                    电影 ({{ profileTypeCounts.Movie }})
                                </button>
                                <button class="profile-legend-btn" :class="{ disabled: !profileTypeFilters.Person }"
                                    @click="toggleProfileType('Person')">
                                    <span class="profile-legend-dot" style="background:#67c23a"></span>
                                    影人 ({{ profileTypeCounts.Person }})
                                </button>
                                <button class="profile-legend-btn" :class="{ disabled: !profileTypeFilters.Genre }"
                                    @click="toggleProfileType('Genre')">
                                    <span class="profile-legend-dot" style="background:#e6a23c"></span>
                                    类型 ({{ profileTypeCounts.Genre }})
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="profile-graph-wrap">
                        <KnowledgeGraph
                            :nodes="profileGraphNodes"
                            :edges="profileGraphEdges"
                            :loading="profileGraphLoading"
                            :highlight-id="`user_${authStore.user?.id}`"
                            :hidden-types="profileHiddenTypes"
                            layout="force"
                            :min-height="420"
                            @node-click="handleProfileGraphNodeClick"
                            @node-hover="(n) => (profileHoveredNode = n)"
                        />
                    </div>
                    <div class="graph-status" v-if="profileGraphMeta">
                        <div class="graph-status-meta">
                            <span>节点: {{ profileGraphMeta.node_count }}</span>
                            <span>边: {{ profileGraphMeta.edge_count }}</span>
                            <span>{{ profileGraphMeta.query_time_ms }}ms</span>
                            <el-tag v-if="profileGraphMeta.truncated" type="warning" size="small" effect="plain">结果已截断</el-tag>
                        </div>
                        <div class="profile-selected-info" v-if="profileHoveredNode">
                            <span>{{ profileHoveredNode.type === 'Movie' ? '🎬' : profileHoveredNode.type === 'Person' ? '🧑' : profileHoveredNode.type === 'User' ? '👤' : '🏷️' }}</span>
                            <strong>{{ profileHoveredNode.label }}</strong>
                            <template v-if="profileHoveredNode.properties?.rating"> · ⭐ {{ profileHoveredNode.properties.rating }}</template>
                            <template v-if="profileHoveredNode.properties?.year"> · {{ profileHoveredNode.properties.year }}</template>
                            <template v-if="profileHoveredNode.properties?.profession"> · {{ profileHoveredNode.properties.profession }}</template>
                            <span class="profile-click-hint" v-if="profileHoveredNode.type === 'Movie' || profileHoveredNode.type === 'Person'">（点击跳转详情）</span>
                        </div>
                    </div>
                </div>
            </template>
        </div>
    </div>
</template>

<style scoped lang="scss">
.profile-view {
    padding-top: var(--space-xl);
    padding-bottom: var(--space-2xl);
}

/* 用户信息卡片 */
.user-card {
    display: flex;
    align-items: center;
    gap: var(--space-lg);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--space-xl);
    margin-bottom: var(--space-xl);
    box-shadow: var(--shadow-sm);
}

.user-info { flex: 1; }

.user-name {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-xs);
}

.user-detail {
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin-bottom: 2px;
}

/* ==================== 偏好/评分列表 ==================== */
.tabs-section {
    margin-bottom: var(--space-md);
}

.empty-state {
    text-align: center;
    padding: var(--space-2xl) 0;
    color: var(--text-muted);
    font-size: 1rem;
}

.item-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: var(--space-md);
}

.item-card {
    display: flex;
    gap: var(--space-md);
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

.item-poster {
    flex-shrink: 0;
    cursor: pointer;

    img {
        width: 80px;
        height: 120px;
        object-fit: cover;
        border-radius: var(--radius-sm);
        transition: transform var(--transition-fast);
    }

    &:hover img { transform: scale(1.05); }
}

.item-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.item-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &:hover { color: var(--color-accent); }
}

.item-meta {
    display: flex;
    gap: var(--space-sm);
    color: var(--text-muted);
    font-size: 0.8rem;
}

.item-rating { color: var(--color-rating); }

.item-my-rating {
    font-size: 0.85rem;
    color: var(--text-secondary);

    strong {
        color: var(--color-rating);
        font-size: 1rem;
    }
}

.item-date {
    color: var(--text-muted);
    font-size: 0.75rem;
}

.pagination-wrap {
    display: flex;
    justify-content: center;
    margin-top: var(--space-xl);
}

/* ==================== 用户画像分析 ==================== */
.portrait-section {
    margin-top: var(--space-2xl);
    margin-bottom: var(--space-xl);
}

.section-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-lg);
}

/* 冷启动 */
.cold-start-hint {
    text-align: center;
    padding: var(--space-2xl) var(--space-lg);
    background: var(--bg-card);
    border: 1px dashed var(--border-color);
    border-radius: var(--radius-lg);
}

.cold-start-icon {
    font-size: 3rem;
    margin-bottom: var(--space-md);
}

.cold-start-text {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--space-xs);
}

.cold-start-sub {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: var(--space-lg);
}

.cold-start-actions {
    display: flex;
    justify-content: center;
    gap: var(--space-sm);
}

/* 统计卡片 */
.profile-stat-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-lg);
}

.profile-stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-md) var(--space-lg);
    text-align: center;
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--color-accent);
        box-shadow: var(--shadow-sm);
    }
}

.profile-stat-num {
    font-size: 1.75rem;
    font-weight: 700;
    line-height: 1.2;

    &.accent { color: var(--color-accent); }
    &.info { color: #409eff; }
    &.warning { color: #e6a23c; }
    &.rating { color: var(--color-rating, #f7ba2a); }
}

.profile-stat-label {
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin-top: var(--space-xs);
}

/* 图表 */
.charts-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-lg);
    margin-bottom: var(--space-lg);
}

.charts-grid-2col {
    grid-template-columns: 1fr 1fr;
}

.chart-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-lg);

    &.wide {
        grid-column: 1 / -1;
    }
}

.chart-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);
    display: flex;
    align-items: center;
    gap: var(--space-md);
}

.chart-legend {
    display: flex;
    gap: var(--space-sm);
    font-size: 0.8rem;
    font-weight: 400;
    color: var(--text-muted);
}

.tag-legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
}

.tag-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
}

.chart-canvas {
    height: 280px;
    width: 100%;
}

/* 常看导演/演员 */
.people-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-lg);
    margin-bottom: var(--space-lg);
}

.people-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
}

.people-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.people-item {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: all var(--transition-fast);

    &:hover {
        background: var(--bg-secondary);
    }
}

.people-rank {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--text-muted);
    background: var(--bg-secondary);
    border-radius: 50%;
    flex-shrink: 0;
}

.people-name {
    flex: 1;
    font-size: 0.9rem;
    color: var(--text-primary);
    font-weight: 500;
}

.people-meta {
    font-size: 0.8rem;
    color: var(--text-muted);
}

/* 用户画像图谱 */
.profile-graph-section {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    margin-bottom: var(--space-lg);
}

.graph-hint {
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: var(--space-md);
}

.profile-graph-controls {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-lg);
    align-items: center;
    padding: var(--space-sm) var(--space-md);
    margin-bottom: var(--space-md);
    background: var(--bg-secondary);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
}

.profile-control-group {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}

.profile-control-label {
    font-size: 0.85rem;
    color: var(--text-secondary);
    white-space: nowrap;
}

.profile-legend-toggles {
    display: flex;
    gap: var(--space-xs);
}

.profile-legend-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 14px;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-secondary);
    font-size: 0.8rem;
    cursor: pointer;
    transition: all var(--transition-fast);

    &:hover { border-color: var(--border-color-light); }
    &.disabled { opacity: 0.35; }
}

.profile-legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.profile-graph-wrap {
    height: 420px;
    min-height: 420px;
    margin-bottom: var(--space-sm);
    overflow: hidden;
}

.graph-status {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-sm);
    font-size: 0.82rem;
    padding: var(--space-sm) var(--space-md);
    background: var(--bg-secondary);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
}

.graph-status-meta {
    display: flex;
    gap: var(--space-md);
    align-items: center;
    color: var(--text-muted);
}

.profile-selected-info {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
    color: var(--text-secondary);
    font-size: 0.85rem;

    strong {
        color: var(--text-primary);
    }
}

.profile-click-hint {
    color: var(--text-muted);
    font-size: 0.75rem;
    margin-left: var(--space-xs);
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
    .user-card {
        flex-direction: column;
        text-align: center;
    }

    .profile-stat-cards {
        grid-template-columns: repeat(2, 1fr);
    }

    .charts-grid-2col {
        grid-template-columns: 1fr;
    }

    .people-grid {
        grid-template-columns: 1fr;
    }

    .item-grid {
        grid-template-columns: 1fr;
    }
}
</style>
