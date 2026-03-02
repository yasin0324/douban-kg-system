<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import { graphApi } from "@/api/graph";
import { moviesApi } from "@/api/movies";
import { personsApi } from "@/api/persons";

const router = useRouter();

// --- 搜索状态 ---
const fromQuery = ref("");
const toQuery = ref("");
const fromNode = ref(null); // { id, label, type }
const toNode = ref(null);
const fromSuggestions = ref([]);
const toSuggestions = ref([]);

// --- 结果 ---
const nodes = ref([]);
const edges = ref([]);
const meta = ref(null);
const loading = ref(false);
const searched = ref(false);
const errorMsg = ref("");

// --- 共同电影 ---
const commonMovies = ref([]);
const commonLoading = ref(false);
const showCommon = ref(false);

// --- 搜索联想 ---
const fetchSuggestions = async (query, cb) => {
    if (!query || query.length < 1) {
        cb([]);
        return;
    }

    try {
        const [moviesRes, personsRes] = await Promise.allSettled([
            moviesApi.search({ q: query, page: 1, size: 6 }),
            personsApi.search({ q: query, page: 1, size: 6 }),
        ]);

        const results = [];

        if (moviesRes.status === "fulfilled") {
            const items =
                moviesRes.value.data?.items || moviesRes.value.data || [];
            items.forEach((m) => {
                results.push({
                    value: m.title + (m.year ? ` (${m.year})` : ""),
                    id: `movie_${m.mid}`,
                    rawId: m.mid,
                    label: m.title,
                    type: "Movie",
                    extra: m.rating ? `⭐${m.rating}` : "",
                });
            });
        }

        if (personsRes.status === "fulfilled") {
            const items =
                personsRes.value.data?.items || personsRes.value.data || [];
            items.forEach((p) => {
                results.push({
                    value: p.name + (p.profession ? ` · ${p.profession}` : ""),
                    id: `person_${p.pid}`,
                    rawId: p.pid,
                    label: p.name,
                    type: "Person",
                    extra: p.profession || "",
                });
            });
        }

        cb(results);
    } catch {
        cb([]);
    }
};

const handleFromSelect = (item) => {
    fromNode.value = {
        id: item.id,
        label: item.label,
        type: item.type,
        rawId: item.rawId,
    };
    fromQuery.value = item.value;
};

const handleToSelect = (item) => {
    toNode.value = {
        id: item.id,
        label: item.label,
        type: item.type,
        rawId: item.rawId,
    };
    toQuery.value = item.value;
};

// --- 查询最短路径 ---
const searchPath = async () => {
    if (!fromNode.value || !toNode.value) {
        errorMsg.value = "请先选择起点和终点";
        return;
    }
    if (fromNode.value.id === toNode.value.id) {
        errorMsg.value = "起点和终点不能相同";
        return;
    }

    errorMsg.value = "";
    loading.value = true;
    searched.value = true;
    commonMovies.value = [];
    showCommon.value = false;

    try {
        const res = await graphApi.getPath(
            fromNode.value.rawId,
            toNode.value.rawId,
        );
        nodes.value = res.data.nodes || [];
        edges.value = res.data.edges || [];
        meta.value = res.data.meta || null;

        if (nodes.value.length === 0) {
            errorMsg.value = "未找到路径，两个节点之间可能不存在连接";
        }

        // 如果两端都是 Person，自动查询共同电影
        if (
            fromNode.value.type === "Person" &&
            toNode.value.type === "Person"
        ) {
            fetchCommonMovies();
        }
    } catch (err) {
        console.error("路径查询失败:", err);
        errorMsg.value = "查询失败，请稍后重试";
        nodes.value = [];
        edges.value = [];
    } finally {
        loading.value = false;
    }
};

// --- 共同电影 ---
const fetchCommonMovies = async () => {
    if (!fromNode.value?.rawId || !toNode.value?.rawId) return;
    commonLoading.value = true;
    showCommon.value = true;
    try {
        const res = await graphApi.getCommon(
            fromNode.value.rawId,
            toNode.value.rawId,
        );
        commonMovies.value = res.data.movies || [];
    } catch {
        commonMovies.value = [];
    } finally {
        commonLoading.value = false;
    }
};

// --- 节点点击 ---
const handleNodeClick = (node) => {
    const idParts = node.id.split("_");
    const rawId = idParts.slice(1).join("_");

    if (node.type === "Movie") {
        router.push(`/movies/${rawId}`);
    } else if (node.type === "Person") {
        router.push(`/persons/${rawId}`);
    }
};

// --- 交换起终点 ---
const swapNodes = () => {
    const tmpNode = fromNode.value;
    const tmpQuery = fromQuery.value;
    fromNode.value = toNode.value;
    fromQuery.value = toQuery.value;
    toNode.value = tmpNode;
    toQuery.value = tmpQuery;
};

// 路径长度
const pathLength = computed(() => meta.value?.depth || 0);
</script>

<template>
    <div class="path-view container">
        <h1 class="page-title"><span>🔗</span> 最短路径查询</h1>
        <p class="page-desc">查找两个电影或影人之间的最短关联路径</p>

        <!-- 搜索区域 -->
        <div class="search-panel card">
            <div class="search-row">
                <!-- 起点 -->
                <div class="search-field">
                    <label class="field-label">起点</label>
                    <el-autocomplete
                        v-model="fromQuery"
                        :fetch-suggestions="fetchSuggestions"
                        placeholder="搜索电影或影人..."
                        clearable
                        @select="handleFromSelect"
                        @clear="fromNode = null"
                        class="search-input"
                        :trigger-on-focus="false"
                    >
                        <template #default="{ item }">
                            <div class="suggestion-item">
                                <span class="suggest-icon">{{
                                    item.type === "Movie" ? "🎬" : "🧑"
                                }}</span>
                                <span class="suggest-name">{{
                                    item.value
                                }}</span>
                                <span class="suggest-extra" v-if="item.extra">{{
                                    item.extra
                                }}</span>
                            </div>
                        </template>
                    </el-autocomplete>
                    <el-tag
                        v-if="fromNode"
                        size="small"
                        :type="fromNode.type === 'Movie' ? '' : 'success'"
                        class="selected-tag"
                    >
                        {{ fromNode.type === "Movie" ? "🎬" : "🧑" }}
                        {{ fromNode.label }}
                    </el-tag>
                </div>

                <!-- 交换按钮 -->
                <el-button
                    class="swap-btn"
                    circle
                    @click="swapNodes"
                    title="交换起终点"
                >
                    ⇄
                </el-button>

                <!-- 终点 -->
                <div class="search-field">
                    <label class="field-label">终点</label>
                    <el-autocomplete
                        v-model="toQuery"
                        :fetch-suggestions="fetchSuggestions"
                        placeholder="搜索电影或影人..."
                        clearable
                        @select="handleToSelect"
                        @clear="toNode = null"
                        class="search-input"
                        :trigger-on-focus="false"
                    >
                        <template #default="{ item }">
                            <div class="suggestion-item">
                                <span class="suggest-icon">{{
                                    item.type === "Movie" ? "🎬" : "🧑"
                                }}</span>
                                <span class="suggest-name">{{
                                    item.value
                                }}</span>
                                <span class="suggest-extra" v-if="item.extra">{{
                                    item.extra
                                }}</span>
                            </div>
                        </template>
                    </el-autocomplete>
                    <el-tag
                        v-if="toNode"
                        size="small"
                        :type="toNode.type === 'Movie' ? '' : 'success'"
                        class="selected-tag"
                    >
                        {{ toNode.type === "Movie" ? "🎬" : "🧑" }}
                        {{ toNode.label }}
                    </el-tag>
                </div>
            </div>

            <div class="search-actions">
                <el-button
                    type="primary"
                    size="large"
                    @click="searchPath"
                    :loading="loading"
                    :disabled="!fromNode || !toNode"
                >
                    🔍 查询路径
                </el-button>
            </div>

            <el-alert
                v-if="errorMsg"
                :title="errorMsg"
                type="warning"
                show-icon
                :closable="false"
                class="error-alert"
            />
        </div>

        <!-- 路径结果 -->
        <template v-if="searched && !loading">
            <!-- 路径图谱 -->
            <div class="path-result" v-if="nodes.length > 0">
                <div class="result-header">
                    <h2 class="section-title">📍 路径结果</h2>
                    <div class="result-meta">
                        <el-tag type="info" size="small" effect="plain">
                            {{ pathLength }} 跳
                        </el-tag>
                        <span class="meta-text" v-if="meta?.query_time_ms">
                            ⏱️ {{ meta.query_time_ms }}ms
                        </span>
                    </div>
                </div>

                <div class="path-graph">
                    <KnowledgeGraph
                        :nodes="nodes"
                        :edges="edges"
                        :loading="false"
                        layout="linear"
                        @node-click="handleNodeClick"
                    />
                </div>

                <!-- 路径节点列表 -->
                <div class="path-steps">
                    <div
                        v-for="(node, idx) in nodes"
                        :key="node.id"
                        class="path-step"
                    >
                        <div class="step-node" :class="node.type.toLowerCase()">
                            <span class="step-icon">{{
                                node.type === "Movie"
                                    ? "🎬"
                                    : node.type === "Person"
                                      ? "🧑"
                                      : "🏷️"
                            }}</span>
                            <span class="step-label">{{ node.label }}</span>
                        </div>
                        <div v-if="idx < nodes.length - 1" class="step-arrow">
                            →
                        </div>
                    </div>
                </div>
            </div>

            <!-- 共同电影 -->
            <div
                class="common-movies"
                v-if="showCommon && commonMovies.length > 0"
            >
                <h2 class="section-title">
                    🎬 共同电影 ({{ commonMovies.length }})
                </h2>
                <div class="common-list">
                    <div
                        v-for="m in commonMovies"
                        :key="m.mid"
                        class="common-item card"
                        @click="router.push(`/movies/${m.mid}`)"
                    >
                        <span class="common-title">{{ m.title }}</span>
                        <div class="common-meta">
                            <span v-if="m.year">{{ m.year }}</span>
                            <span v-if="m.rating" class="common-rating"
                                >⭐ {{ m.rating }}</span
                            >
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<style scoped lang="scss">
.path-view {
    padding-top: var(--space-xl);
}

.page-desc {
    color: var(--text-secondary);
    margin-bottom: var(--space-lg);
    font-size: 0.95rem;
}

.search-panel {
    padding: var(--space-lg);
    margin-bottom: var(--space-xl);

    &:hover {
        transform: none;
    }
}

.search-row {
    display: flex;
    align-items: flex-start;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
}

.search-field {
    flex: 1;
}

.field-label {
    display: block;
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: var(--space-xs);
    font-weight: 500;
}

.search-input {
    width: 100%;
}

.selected-tag {
    margin-top: var(--space-xs);
}

.swap-btn {
    margin-top: 24px;
    font-size: 1.1rem;
}

.search-actions {
    text-align: center;
}

.error-alert {
    margin-top: var(--space-md);
}

.suggestion-item {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 4px 0;
}

.suggest-icon {
    font-size: 1rem;
}

.suggest-name {
    flex: 1;
    font-size: 0.9rem;
}

.suggest-extra {
    color: var(--text-muted);
    font-size: 0.8rem;
}

/* 路径结果 */
.path-result {
    margin-bottom: var(--space-xl);
}

.result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
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
}

/* 路径步骤 */
.path-steps {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-xs);
    padding: var(--space-md);
    background: var(--bg-card);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
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

/* 共同电影 */
.common-movies {
    margin-bottom: var(--space-xl);
}

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
}

.common-meta {
    display: flex;
    gap: var(--space-sm);
    color: var(--text-muted);
    font-size: 0.82rem;
}

.common-rating {
    color: var(--color-rating);
}

@media (max-width: 768px) {
    .search-row {
        flex-direction: column;
    }

    .swap-btn {
        align-self: center;
        margin-top: 0;
    }

    .path-steps {
        justify-content: center;
    }

    .path-graph {
        height: 280px;
    }
}
</style>
