<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import { graphApi } from "@/api/graph";
import { moviesApi } from "@/api/movies";
import { personsApi } from "@/api/persons";

const route = useRoute();
const router = useRouter();

const activeTab = ref("overview");

// ==================== 知识图谱全局概览 ====================
const overviewNodes = ref([]);
const overviewEdges = ref([]);
const overviewMeta = ref(null);
const overviewLoading = ref(false);
// 直接控制展示的电影数量（即 seed_count）
const overviewMovieLimit = ref(200);
const overviewHiddenTypes = ref([]);
const overviewTypeFilters = ref({ Movie: true, Person: true, Genre: true });
const overviewHoveredNode = ref(null);

const overviewTypeCounts = computed(() => {
    const counts = { Movie: 0, Person: 0, Genre: 0 };
    overviewNodes.value.forEach((n) => {
        if (counts[n.type] !== undefined) counts[n.type]++;
    });
    return counts;
});

const toggleOverviewType = (type) => {
    overviewTypeFilters.value[type] = !overviewTypeFilters.value[type];
    overviewHiddenTypes.value = Object.entries(overviewTypeFilters.value)
        .filter(([, v]) => !v)
        .map(([k]) => k);
};

const fetchOverviewGraph = async () => {
    overviewLoading.value = true;
    try {
        const seedCount = overviewMovieLimit.value;
        // nodeLimit 按电影数量的 4 倍估算（电影 + 影人 + 类型），上限 1500
        const nodeLimit = Math.min(seedCount * 4, 1500);
        const res = await graphApi.getOverviewGraph({
            nodeLimit,
            edgeLimit: Math.min(seedCount * 6, 3000),
            seedCount,
        });
        overviewNodes.value = res.data.nodes || [];
        overviewEdges.value = res.data.edges || [];
        overviewMeta.value = res.data.meta || null;
    } catch (err) {
        console.error("加载概览图谱失败:", err);
        overviewNodes.value = [];
        overviewEdges.value = [];
    } finally {
        overviewLoading.value = false;
    }
};

const handleOverviewNodeClick = (node) => {
    if (node.type === "Genre") return;
    const idParts = node.id.split("_");
    const rawId = idParts.slice(1).join("_");
    activeTab.value = "explore";
    nextTick(() => {
        exploreSelectedNode.value = { id: node.id, rawId, label: node.label, type: node.type };
        exploreQuery.value = node.label;
        fetchExploreGraph();
    });
};

// ==================== 图谱探索 ====================
const exploreQuery = ref("");
const exploreSelectedNode = ref(null);
const exploreNodes = ref([]);
const exploreEdges = ref([]);
const exploreMeta = ref(null);
const exploreLoading = ref(false);
const exploreDepth = ref(1);
const exploreNodeLimit = ref(150);
const exploreHiddenTypes = ref([]);
const exploreHistory = ref([]);
const exploreHoveredNode = ref(null);

const exploreTypeFilters = ref({ Movie: true, Person: true, Genre: true });

const exploreTypeCounts = computed(() => {
    const counts = { Movie: 0, Person: 0, Genre: 0 };
    exploreNodes.value.forEach((n) => {
        if (counts[n.type] !== undefined) counts[n.type]++;
    });
    return counts;
});

const toggleExploreType = (type) => {
    exploreTypeFilters.value[type] = !exploreTypeFilters.value[type];
    exploreHiddenTypes.value = Object.entries(exploreTypeFilters.value)
        .filter(([, v]) => !v)
        .map(([k]) => k);
};

const fetchExploreSuggestions = async (query, cb) => {
    if (!query || query.length < 1) { cb([]); return; }
    try {
        const [moviesRes, personsRes] = await Promise.allSettled([
            moviesApi.search({ q: query, page: 1, size: 6 }),
            personsApi.search({ q: query, page: 1, size: 6 }),
        ]);
        const results = [];
        if (moviesRes.status === "fulfilled") {
            (moviesRes.value.data?.items || moviesRes.value.data || []).forEach((m) => {
                results.push({
                    value: m.title + (m.year ? ` (${m.year})` : ""),
                    id: `movie_${m.mid}`, rawId: m.mid, label: m.title,
                    type: "Movie", extra: m.rating ? `${m.rating}` : "",
                });
            });
        }
        if (personsRes.status === "fulfilled") {
            (personsRes.value.data?.items || personsRes.value.data || []).forEach((p) => {
                results.push({
                    value: p.name + (p.profession ? ` · ${p.profession}` : ""),
                    id: `person_${p.pid}`, rawId: p.pid, label: p.name,
                    type: "Person", extra: p.profession || "",
                });
            });
        }
        cb(results);
    } catch { cb([]); }
};

const handleExploreSelect = (item) => {
    exploreSelectedNode.value = { id: item.id, rawId: item.rawId, label: item.label, type: item.type };
    exploreQuery.value = item.value;
    fetchExploreGraph();
};

const fetchExploreGraph = async () => {
    if (!exploreSelectedNode.value) return;
    exploreLoading.value = true;
    try {
        const params = { depth: exploreDepth.value, nodeLimit: exploreNodeLimit.value };
        const node = exploreSelectedNode.value;
        const res = node.type === "Movie"
            ? await graphApi.getMovieGraph(node.rawId, params)
            : await graphApi.getPersonGraph(node.rawId, params);
        exploreNodes.value = res.data.nodes || [];
        exploreEdges.value = res.data.edges || [];
        exploreMeta.value = res.data.meta || null;
        if (!exploreHistory.value.find((h) => h.id === node.id)) {
            exploreHistory.value.unshift({ ...node });
            if (exploreHistory.value.length > 10) exploreHistory.value.pop();
        }
    } catch (err) {
        console.error("图谱加载失败:", err);
        exploreNodes.value = [];
        exploreEdges.value = [];
    } finally {
        exploreLoading.value = false;
    }
};

const handleExploreNodeClick = (node) => {
    if (node.type === "Genre") return;
    const idParts = node.id.split("_");
    const rawId = idParts.slice(1).join("_");
    exploreSelectedNode.value = { id: node.id, rawId, label: node.label, type: node.type };
    exploreQuery.value = node.label;
    fetchExploreGraph();
};

const handleHistoryClick = (item) => {
    exploreSelectedNode.value = { ...item };
    exploreQuery.value = item.label;
    fetchExploreGraph();
};

// ==================== 路径查询 ====================
const fromQuery = ref("");
const toQuery = ref("");
const fromNode = ref(null);
const toNode = ref(null);

const pathNodes = ref([]);
const pathEdges = ref([]);
const pathMeta = ref(null);
const pathLoading = ref(false);
const pathSearched = ref(false);
const pathError = ref("");
const excludeGenre = ref(false);

const commonMovies = ref([]);
const commonLoading = ref(false);
const showCommon = ref(false);

const fetchPathSuggestions = async (query, cb) => {
    if (!query || query.length < 1) { cb([]); return; }
    try {
        const [moviesRes, personsRes] = await Promise.allSettled([
            moviesApi.search({ q: query, page: 1, size: 6 }),
            personsApi.search({ q: query, page: 1, size: 6 }),
        ]);
        const results = [];
        if (moviesRes.status === "fulfilled") {
            (moviesRes.value.data?.items || moviesRes.value.data || []).forEach((m) => {
                results.push({
                    value: m.title + (m.year ? ` (${m.year})` : ""),
                    id: `movie_${m.mid}`, rawId: m.mid, label: m.title,
                    type: "Movie", extra: m.rating ? `${m.rating}` : "",
                });
            });
        }
        if (personsRes.status === "fulfilled") {
            (personsRes.value.data?.items || personsRes.value.data || []).forEach((p) => {
                results.push({
                    value: p.name + (p.profession ? ` · ${p.profession}` : ""),
                    id: `person_${p.pid}`, rawId: p.pid, label: p.name,
                    type: "Person", extra: p.profession || "",
                });
            });
        }
        cb(results);
    } catch { cb([]); }
};

const handleFromSelect = (item) => {
    fromNode.value = { id: item.id, label: item.label, type: item.type, rawId: item.rawId };
    fromQuery.value = item.value;
};

const handleToSelect = (item) => {
    toNode.value = { id: item.id, label: item.label, type: item.type, rawId: item.rawId };
    toQuery.value = item.value;
};

const searchPath = async () => {
    if (!fromNode.value || !toNode.value) { pathError.value = "请先选择起点和终点"; return; }
    if (fromNode.value.id === toNode.value.id) { pathError.value = "起点和终点不能相同"; return; }
    pathError.value = "";
    pathLoading.value = true;
    pathSearched.value = true;
    commonMovies.value = [];
    showCommon.value = false;
    try {
        const res = await graphApi.getPath(fromNode.value.rawId, toNode.value.rawId, 6, excludeGenre.value);
        pathNodes.value = res.data.nodes || [];
        pathEdges.value = res.data.edges || [];
        pathMeta.value = res.data.meta || null;
        if (pathNodes.value.length === 0) pathError.value = "未找到路径，两个节点之间可能不存在连接";
        if (fromNode.value.type === "Person" && toNode.value.type === "Person") fetchCommonMovies();
    } catch {
        pathError.value = "查询失败，请稍后重试";
        pathNodes.value = [];
        pathEdges.value = [];
    } finally {
        pathLoading.value = false;
    }
};

const fetchCommonMovies = async () => {
    if (!fromNode.value?.rawId || !toNode.value?.rawId) return;
    commonLoading.value = true;
    showCommon.value = true;
    try {
        const res = await graphApi.getCommon(fromNode.value.rawId, toNode.value.rawId);
        commonMovies.value = res.data.movies || [];
    } catch { commonMovies.value = []; }
    finally { commonLoading.value = false; }
};

const handlePathNodeClick = (node) => {
    const idParts = node.id.split("_");
    const rawId = idParts.slice(1).join("_");
    if (node.type === "Movie") router.push(`/movies/${rawId}`);
    else if (node.type === "Person") router.push(`/persons/${rawId}`);
};

const swapNodes = () => {
    const tmpNode = fromNode.value;
    const tmpQuery = fromQuery.value;
    fromNode.value = toNode.value;
    fromQuery.value = toQuery.value;
    toNode.value = tmpNode;
    toQuery.value = tmpQuery;
};

const pathLength = computed(() => pathMeta.value?.depth || 0);

// ==================== 生命周期 ====================
onMounted(async () => {
    fetchOverviewGraph();

    const fromId = route.query.from;
    const toId = route.query.to;
    if (fromId && toId) {
        activeTab.value = "path";
        try {
            const [fromRes, toRes] = await Promise.all([
                personsApi.getDetail(fromId),
                personsApi.getDetail(toId),
            ]);
            if (fromRes.data) {
                const f = fromRes.data;
                fromNode.value = { id: `person_${f.pid}`, rawId: f.pid, label: f.name, type: "Person" };
                fromQuery.value = f.name;
            }
            if (toRes.data) {
                const t = toRes.data;
                toNode.value = { id: `person_${t.pid}`, rawId: t.pid, label: t.name, type: "Person" };
                toQuery.value = t.name;
            }
            if (fromNode.value && toNode.value) searchPath();
        } catch (err) {
            console.error("预填路径参数失败:", err);
        }
    }
});
</script>

<template>
    <div class="kg-explore-view container">
        <h1 class="page-title"><span>🌐</span> 知识图谱</h1>
        <p class="page-desc">探索豆瓣电影知识图谱中的实体与关联</p>

        <el-tabs v-model="activeTab" class="kg-tabs">
            <!-- ==================== 知识图谱全局概览 ==================== -->
            <el-tab-pane label="知识图谱" name="overview">
                <div class="overview-section">
                    <div class="control-panel card">
                        <div class="control-group">
                            <span class="control-label">电影上限: {{ overviewMovieLimit }}</span>
                            <el-slider v-model="overviewMovieLimit" :min="50" :max="500" :step="10"
                                style="width: 160px" @change="fetchOverviewGraph" />
                        </div>
                        <div class="control-group">
                            <span class="control-label">图例</span>
                            <div class="legend-toggles">
                                <button class="legend-btn" :class="{ disabled: !overviewTypeFilters.Movie }"
                                    @click="toggleOverviewType('Movie')">
                                    <span class="legend-dot" style="background:#409eff"></span>
                                    电影 ({{ overviewTypeCounts.Movie }})
                                </button>
                                <button class="legend-btn" :class="{ disabled: !overviewTypeFilters.Person }"
                                    @click="toggleOverviewType('Person')">
                                    <span class="legend-dot" style="background:#67c23a"></span>
                                    影人 ({{ overviewTypeCounts.Person }})
                                </button>
                                <button class="legend-btn" :class="{ disabled: !overviewTypeFilters.Genre }"
                                    @click="toggleOverviewType('Genre')">
                                    <span class="legend-dot" style="background:#e6a23c"></span>
                                    类型 ({{ overviewTypeCounts.Genre }})
                                </button>
                            </div>
                        </div>
                        <div class="control-group">
                            <el-button size="small" :loading="overviewLoading" @click="fetchOverviewGraph">
                                换一批
                            </el-button>
                        </div>
                    </div>

                    <div class="overview-graph">
                        <KnowledgeGraph
                            :nodes="overviewNodes"
                            :edges="overviewEdges"
                            :loading="overviewLoading"
                            :hidden-types="overviewHiddenTypes"
                            layout="force"
                            :min-height="560"
                            @node-click="handleOverviewNodeClick"
                            @node-hover="(n) => (overviewHoveredNode = n)"
                        />
                    </div>

                    <div class="status-bar" v-if="overviewMeta">
                        <div class="status-items">
                            <span class="status-item">节点: {{ overviewMeta.node_count }}</span>
                            <span class="status-item">边: {{ overviewMeta.edge_count }}</span>
                            <span class="status-item">{{ overviewMeta.query_time_ms }}ms</span>
                            <el-tag v-if="overviewMeta.truncated" type="warning" size="small" effect="plain">结果已截断</el-tag>
                        </div>
                        <div class="selected-info" v-if="overviewHoveredNode">
                            <span>{{ overviewHoveredNode.type === 'Movie' ? '🎬' : overviewHoveredNode.type === 'Person' ? '🧑' : '🏷️' }}</span>
                            <strong>{{ overviewHoveredNode.label }}</strong>
                            <template v-if="overviewHoveredNode.properties?.rating"> · ⭐ {{ overviewHoveredNode.properties.rating }}</template>
                            <template v-if="overviewHoveredNode.properties?.year"> · {{ overviewHoveredNode.properties.year }}</template>
                            <template v-if="overviewHoveredNode.properties?.profession"> · {{ overviewHoveredNode.properties.profession }}</template>
                            <span class="click-hint">（点击节点进入图谱探索）</span>
                        </div>
                        <span class="status-hint" v-else>点击节点可进入图谱探索深入查看</span>
                    </div>
                </div>
            </el-tab-pane>

            <!-- ==================== 图谱探索 ==================== -->
            <el-tab-pane label="图谱探索" name="explore">
                <div class="explore-section">
                    <div class="explore-search card">
                        <el-autocomplete
                            v-model="exploreQuery"
                            :fetch-suggestions="fetchExploreSuggestions"
                            placeholder="搜索电影或影人，开始探索图谱..."
                            clearable
                            @select="handleExploreSelect"
                            @clear="exploreSelectedNode = null"
                            class="explore-input"
                            :trigger-on-focus="false"
                        >
                            <template #default="{ item }">
                                <div class="suggestion-item">
                                    <span class="suggest-icon">{{ item.type === "Movie" ? "🎬" : "🧑" }}</span>
                                    <span class="suggest-name">{{ item.value }}</span>
                                    <span class="suggest-extra" v-if="item.extra">{{ item.extra }}</span>
                                </div>
                            </template>
                        </el-autocomplete>

                        <div class="explore-history" v-if="exploreHistory.length > 0">
                            <span class="history-label">最近探索：</span>
                            <el-tag v-for="h in exploreHistory" :key="h.id" size="small"
                                :type="h.type === 'Movie' ? '' : 'success'"
                                class="history-tag" @click="handleHistoryClick(h)">
                                {{ h.label }}
                            </el-tag>
                        </div>
                    </div>

                    <div class="control-panel card" v-if="exploreSelectedNode">
                        <div class="control-group">
                            <span class="control-label">当前节点</span>
                            <el-tag :type="exploreSelectedNode.type === 'Movie' ? '' : 'success'" effect="dark">
                                {{ exploreSelectedNode.type === "Movie" ? "🎬" : "🧑" }}
                                {{ exploreSelectedNode.label }}
                            </el-tag>
                        </div>
                        <div class="control-group">
                            <span class="control-label">展开深度</span>
                            <el-radio-group v-model="exploreDepth" size="small" @change="fetchExploreGraph">
                                <el-radio-button :value="1">1 跳</el-radio-button>
                                <el-radio-button :value="2">2 跳</el-radio-button>
                            </el-radio-group>
                        </div>
                        <div class="control-group">
                            <span class="control-label">节点上限: {{ exploreNodeLimit }}</span>
                            <el-slider v-model="exploreNodeLimit" :min="30" :max="500" :step="10"
                                style="width: 140px" @change="fetchExploreGraph" />
                        </div>
                        <div class="control-group">
                            <span class="control-label">图例</span>
                            <div class="legend-toggles">
                                <button class="legend-btn" :class="{ disabled: !exploreTypeFilters.Movie }"
                                    @click="toggleExploreType('Movie')">
                                    <span class="legend-dot" style="background:#409eff"></span>
                                    电影 ({{ exploreTypeCounts.Movie }})
                                </button>
                                <button class="legend-btn" :class="{ disabled: !exploreTypeFilters.Person }"
                                    @click="toggleExploreType('Person')">
                                    <span class="legend-dot" style="background:#67c23a"></span>
                                    影人 ({{ exploreTypeCounts.Person }})
                                </button>
                                <button class="legend-btn" :class="{ disabled: !exploreTypeFilters.Genre }"
                                    @click="toggleExploreType('Genre')">
                                    <span class="legend-dot" style="background:#e6a23c"></span>
                                    类型 ({{ exploreTypeCounts.Genre }})
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="explore-graph" v-if="exploreSelectedNode">
                        <KnowledgeGraph
                            :nodes="exploreNodes"
                            :edges="exploreEdges"
                            :loading="exploreLoading"
                            :highlight-id="exploreSelectedNode?.id || ''"
                            :hidden-types="exploreHiddenTypes"
                            layout="force"
                            :min-height="500"
                            @node-click="handleExploreNodeClick"
                            @node-hover="(n) => (exploreHoveredNode = n)"
                        />
                    </div>

                    <div class="status-bar" v-if="exploreMeta && exploreSelectedNode">
                        <div class="status-items">
                            <span class="status-item">节点: {{ exploreMeta.node_count }}</span>
                            <span class="status-item">边: {{ exploreMeta.edge_count }}</span>
                            <span class="status-item">{{ exploreMeta.query_time_ms }}ms</span>
                            <el-tag v-if="exploreMeta.truncated" type="warning" size="small" effect="plain">结果已截断</el-tag>
                        </div>
                        <div class="selected-info" v-if="exploreHoveredNode">
                            <span>{{ exploreHoveredNode.type === 'Movie' ? '🎬' : exploreHoveredNode.type === 'Person' ? '🧑' : '🏷️' }}</span>
                            <strong>{{ exploreHoveredNode.label }}</strong>
                            <template v-if="exploreHoveredNode.properties?.rating"> · ⭐ {{ exploreHoveredNode.properties.rating }}</template>
                            <template v-if="exploreHoveredNode.properties?.year"> · {{ exploreHoveredNode.properties.year }}</template>
                            <template v-if="exploreHoveredNode.properties?.profession"> · {{ exploreHoveredNode.properties.profession }}</template>
                        </div>
                        <span class="status-hint" v-else>悬浮节点可查看详情，点击节点就地展开关联图谱</span>
                    </div>

                    <div class="explore-empty" v-if="!exploreSelectedNode">
                        <div class="empty-icon">🔍</div>
                        <p>搜索一个电影或影人，开始探索知识图谱</p>
                    </div>
                </div>
            </el-tab-pane>

            <!-- ==================== 路径查询 ==================== -->
            <el-tab-pane label="路径查询" name="path">
                <div class="path-section">
                    <div class="search-panel card">
                        <div class="search-row">
                            <div class="search-field">
                                <label class="field-label">起点</label>
                                <el-autocomplete v-model="fromQuery" :fetch-suggestions="fetchPathSuggestions"
                                    placeholder="搜索电影或影人..." clearable @select="handleFromSelect"
                                    @clear="fromNode = null" class="search-input" :trigger-on-focus="false">
                                    <template #default="{ item }">
                                        <div class="suggestion-item">
                                            <span class="suggest-icon">{{ item.type === "Movie" ? "🎬" : "🧑" }}</span>
                                            <span class="suggest-name">{{ item.value }}</span>
                                            <span class="suggest-extra" v-if="item.extra">{{ item.extra }}</span>
                                        </div>
                                    </template>
                                </el-autocomplete>
                                <el-tag v-if="fromNode" size="small" :type="fromNode.type === 'Movie' ? '' : 'success'" class="selected-tag">
                                    {{ fromNode.type === "Movie" ? "🎬" : "🧑" }} {{ fromNode.label }}
                                </el-tag>
                            </div>

                            <el-button class="swap-btn" circle @click="swapNodes" title="交换起终点">⇄</el-button>

                            <div class="search-field">
                                <label class="field-label">终点</label>
                                <el-autocomplete v-model="toQuery" :fetch-suggestions="fetchPathSuggestions"
                                    placeholder="搜索电影或影人..." clearable @select="handleToSelect"
                                    @clear="toNode = null" class="search-input" :trigger-on-focus="false">
                                    <template #default="{ item }">
                                        <div class="suggestion-item">
                                            <span class="suggest-icon">{{ item.type === "Movie" ? "🎬" : "🧑" }}</span>
                                            <span class="suggest-name">{{ item.value }}</span>
                                            <span class="suggest-extra" v-if="item.extra">{{ item.extra }}</span>
                                        </div>
                                    </template>
                                </el-autocomplete>
                                <el-tag v-if="toNode" size="small" :type="toNode.type === 'Movie' ? '' : 'success'" class="selected-tag">
                                    {{ toNode.type === "Movie" ? "🎬" : "🧑" }} {{ toNode.label }}
                                </el-tag>
                            </div>
                        </div>

                        <div class="search-options">
                            <el-switch v-model="excludeGenre" active-text="排除类型节点" inactive-text="" class="genre-switch" />
                            <span class="option-hint">开启后路径将不经过类型节点，仅通过演职关系查找</span>
                        </div>

                        <div class="search-actions">
                            <el-button type="primary" size="large" @click="searchPath" :loading="pathLoading"
                                :disabled="!fromNode || !toNode">
                                查询路径
                            </el-button>
                        </div>

                        <el-alert v-if="pathError" :title="pathError" type="warning" show-icon :closable="false" class="error-alert" />
                    </div>

                    <template v-if="pathSearched && !pathLoading">
                        <div class="path-result" v-if="pathNodes.length > 0">
                            <div class="result-header">
                                <h2 class="section-title">路径结果</h2>
                                <div class="result-meta">
                                    <el-tag type="info" size="small" effect="plain">{{ pathLength }} 跳</el-tag>
                                    <span class="meta-text" v-if="pathMeta?.query_time_ms">{{ pathMeta.query_time_ms }}ms</span>
                                </div>
                            </div>

                            <div class="path-graph">
                                <KnowledgeGraph :nodes="pathNodes" :edges="pathEdges" :loading="false"
                                    layout="linear" @node-click="handlePathNodeClick" />
                            </div>

                            <div class="path-steps">
                                <div v-for="(node, idx) in pathNodes" :key="node.id" class="path-step">
                                    <div class="step-node" :class="node.type.toLowerCase()">
                                        <span class="step-icon">{{ node.type === "Movie" ? "🎬" : node.type === "Person" ? "🧑" : "🏷️" }}</span>
                                        <span class="step-label">{{ node.label }}</span>
                                    </div>
                                    <div v-if="idx < pathNodes.length - 1" class="step-arrow">→</div>
                                </div>
                            </div>
                        </div>

                        <div class="common-movies" v-if="showCommon && commonMovies.length > 0">
                            <h2 class="section-title">共同电影 ({{ commonMovies.length }})</h2>
                            <div class="common-list">
                                <div v-for="m in commonMovies" :key="m.mid" class="common-item card"
                                    @click="router.push(`/movies/${m.mid}`)">
                                    <span class="common-title">{{ m.title }}</span>
                                    <div class="common-meta">
                                        <span v-if="m.year">{{ m.year }}</span>
                                        <span v-if="m.rating" class="common-rating">{{ m.rating }}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                </div>
            </el-tab-pane>
        </el-tabs>
    </div>
</template>

<style scoped lang="scss">
.kg-explore-view {
    padding-top: var(--space-xl);
    padding-bottom: var(--space-2xl);
}

.page-desc {
    color: var(--text-secondary);
    margin-bottom: var(--space-lg);
    font-size: 0.95rem;
}

.kg-tabs {
    :deep(.el-tabs__header) {
        margin-bottom: var(--space-lg);
    }
}

/* ==================== 全局概览 ==================== */
.overview-graph {
    height: 65vh;
    min-height: 560px;
    margin-bottom: var(--space-sm);
}

/* ==================== 共用控件 ==================== */
.control-panel {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-lg);
    align-items: center;
    padding: var(--space-md) var(--space-lg);
    margin-bottom: var(--space-md);

    &:hover { transform: none; }
}

.control-group {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}

.control-label {
    font-size: 0.85rem;
    color: var(--text-secondary);
    white-space: nowrap;
}

.legend-toggles {
    display: flex;
    gap: var(--space-xs);
}

.legend-btn {
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

.legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-sm);
    padding: var(--space-sm) var(--space-md);
    background: var(--bg-card);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
    font-size: 0.82rem;
}

.status-items {
    display: flex;
    gap: var(--space-md);
    align-items: center;
}

.status-item {
    color: var(--text-muted);
}

.status-hint {
    color: var(--text-muted);
    font-size: 0.8rem;
}

.selected-info {
    color: var(--text-secondary);
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;

    strong {
        color: var(--text-primary);
    }
}

.click-hint {
    color: var(--text-muted);
    font-size: 0.75rem;
    margin-left: var(--space-xs);
}

/* ==================== 图谱探索 ==================== */
.explore-search {
    padding: var(--space-lg);
    margin-bottom: var(--space-md);

    &:hover { transform: none; }
}

.explore-input {
    width: 100%;
}

.explore-history {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-xs);
    margin-top: var(--space-sm);
}

.history-label {
    font-size: 0.8rem;
    color: var(--text-muted);
}

.history-tag {
    cursor: pointer;
}

.explore-graph {
    height: 55vh;
    min-height: 500px;
    margin-bottom: var(--space-sm);
}

.explore-empty {
    text-align: center;
    padding: var(--space-2xl) 0;
    color: var(--text-muted);

    .empty-icon {
        font-size: 3rem;
        margin-bottom: var(--space-md);
    }

    p { font-size: 1rem; }
}

/* ==================== 路径查询 ==================== */
.search-panel {
    padding: var(--space-lg);
    margin-bottom: var(--space-xl);

    &:hover { transform: none; }
}

.search-row {
    display: flex;
    align-items: flex-start;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
}

.search-field { flex: 1; }

.field-label {
    display: block;
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: var(--space-xs);
    font-weight: 500;
}

.search-input { width: 100%; }
.selected-tag { margin-top: var(--space-xs); }

.swap-btn {
    margin-top: 24px;
    font-size: 1.1rem;
}

.search-options {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin-bottom: var(--space-md);
    padding: var(--space-sm) 0;
}

.option-hint {
    color: var(--text-muted);
    font-size: 0.8rem;
}

.search-actions { text-align: center; }
.error-alert { margin-top: var(--space-md); }

.suggestion-item {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 4px 0;
}

.suggest-icon { font-size: 1rem; }
.suggest-name { flex: 1; font-size: 0.9rem; }

.suggest-extra {
    color: var(--text-muted);
    font-size: 0.8rem;
}

.path-result { padding-bottom: var(--space-xl); }

.result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.section-title {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--space-md);
}

.result-meta {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}

.meta-text {
    color: var(--text-muted);
    font-size: 0.82rem;
}

.path-graph {
    height: 350px;
    margin-bottom: var(--space-md);
    overflow: hidden;
}

.path-steps {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
    padding: var(--space-md);
    background: var(--bg-card);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    overflow-x: auto;
}

.path-step {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
}

.step-node {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;

    &.movie {
        background: rgba(64, 158, 255, 0.15);
        color: #409eff;
        border: 1px solid rgba(64, 158, 255, 0.3);
    }
    &.person {
        background: rgba(103, 194, 58, 0.15);
        color: #67c23a;
        border: 1px solid rgba(103, 194, 58, 0.3);
    }
    &.genre {
        background: rgba(230, 162, 60, 0.15);
        color: #e6a23c;
        border: 1px solid rgba(230, 162, 60, 0.3);
    }
}

.step-arrow {
    color: var(--text-muted);
    font-size: 1.1rem;
    padding: 0 4px;
}

.common-movies { margin-bottom: var(--space-xl); }

.common-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: var(--space-sm);
}

.common-item {
    padding: var(--space-md);
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.common-title {
    font-weight: 500;
    color: var(--text-primary);
    font-size: 0.9rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    min-width: 0;
}

.common-meta {
    display: flex;
    gap: var(--space-sm);
    color: var(--text-muted);
    font-size: 0.82rem;
}

.common-rating { color: var(--color-rating); }

@media (max-width: 768px) {
    .search-row { flex-direction: column; }
    .swap-btn { align-self: center; margin-top: 0; }
    .path-steps { justify-content: center; }
    .path-graph { height: 280px; }
    .control-panel { flex-direction: column; align-items: flex-start; }
    .explore-graph { height: 45vh; min-height: 300px; }
    .overview-graph { height: 50vh; min-height: 350px; }
}
</style>
