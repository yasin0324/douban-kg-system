<script setup>
import { ref, onMounted, watch, computed } from "vue";
import { useRouter } from "vue-router";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import { graphApi } from "@/api/graph";

const props = defineProps({
    type: { type: String, required: true }, // "movie" | "person"
    id: { type: String, required: true },
});

const router = useRouter();

// --- 数据 ---
const nodes = ref([]);
const edges = ref([]);
const meta = ref(null);
const loading = ref(true);
const selectedNode = ref(null);

// --- 控制面板 ---
const depth = ref(1);
const nodeLimit = ref(150);
const hiddenTypes = ref([]);

// --- 中心节点信息 ---
const centerNode = computed(() => {
    const centerId = `${props.type}_${props.id}`;
    return nodes.value.find((n) => n.id === centerId) || null;
});

const highlightId = computed(() => `${props.type}_${props.id}`);

const pageTitle = computed(() => {
    if (centerNode.value) return centerNode.value.label;
    return props.type === "movie" ? "电影图谱" : "影人图谱";
});

// --- API 调用 ---
const fetchGraph = async () => {
    loading.value = true;
    selectedNode.value = null;
    try {
        const params = {
            depth: depth.value,
            nodeLimit: nodeLimit.value,
        };
        const res =
            props.type === "movie"
                ? await graphApi.getMovieGraph(props.id, params)
                : await graphApi.getPersonGraph(props.id, params);

        nodes.value = res.data.nodes || [];
        edges.value = res.data.edges || [];
        meta.value = res.data.meta || null;
    } catch (err) {
        console.error("图谱加载失败:", err);
        nodes.value = [];
        edges.value = [];
    } finally {
        loading.value = false;
    }
};

// --- 节点点击 ---
const handleNodeClick = (node) => {
    selectedNode.value = node;

    // 提取实际 ID（去掉 type_ 前缀）
    const idParts = node.id.split("_");
    const rawId = idParts.slice(1).join("_");

    if (node.type === "Movie") {
        router.push(`/movies/${rawId}`);
    } else if (node.type === "Person") {
        router.push(`/persons/${rawId}`);
    } else if (node.type === "Genre") {
        router.push({ path: "/movies/filter", query: { genre: node.label } });
    }
};

// --- 图例过滤 ---
const typeFilters = ref({
    Movie: true,
    Person: true,
    Genre: true,
});

const toggleType = (type) => {
    typeFilters.value[type] = !typeFilters.value[type];
    hiddenTypes.value = Object.entries(typeFilters.value)
        .filter(([, v]) => !v)
        .map(([k]) => k);
};

// --- 控制面板变化时重新加载 ---
const handleDepthChange = () => {
    fetchGraph();
};

const handleLimitChange = () => {
    fetchGraph();
};

// --- 返回详情页 ---
const goBack = () => {
    if (props.type === "movie") {
        router.push(`/movies/${props.id}`);
    } else {
        router.push(`/persons/${props.id}`);
    }
};

// --- 节点类型统计 ---
const typeCounts = computed(() => {
    const counts = { Movie: 0, Person: 0, Genre: 0 };
    nodes.value.forEach((n) => {
        if (counts[n.type] !== undefined) counts[n.type]++;
    });
    return counts;
});

onMounted(fetchGraph);

watch(() => [props.type, props.id], fetchGraph);
</script>

<template>
    <div class="graph-view">
        <div class="graph-body container">
            <!-- 顶部信息栏 -->
            <div class="graph-header">
                <div class="header-left">
                    <el-button text @click="goBack" class="back-btn">
                        ← 返回{{ type === "movie" ? "电影" : "影人" }}详情
                    </el-button>
                    <h1 class="graph-title">
                        <span class="title-icon">🕸️</span>
                        {{ pageTitle }}
                    </h1>
                </div>
            </div>

            <!-- 控制面板 -->
            <div class="control-panel card">
                <div class="control-group">
                    <span class="control-label">展开深度</span>
                    <el-radio-group
                        v-model="depth"
                        size="small"
                        @change="handleDepthChange"
                    >
                        <el-radio-button :value="1">1 跳</el-radio-button>
                        <el-radio-button :value="2">2 跳</el-radio-button>
                    </el-radio-group>
                </div>

                <div class="control-group">
                    <span class="control-label">节点上限: {{ nodeLimit }}</span>
                    <el-slider
                        v-model="nodeLimit"
                        :min="30"
                        :max="500"
                        :step="10"
                        style="width: 140px"
                        @change="handleLimitChange"
                    />
                </div>

                <div class="control-group">
                    <span class="control-label">图例</span>
                    <div class="legend-toggles">
                        <button
                            class="legend-btn"
                            :class="{ disabled: !typeFilters.Movie }"
                            @click="toggleType('Movie')"
                        >
                            <span
                                class="legend-dot"
                                style="background: #409eff"
                            ></span>
                            电影 ({{ typeCounts.Movie }})
                        </button>
                        <button
                            class="legend-btn"
                            :class="{ disabled: !typeFilters.Person }"
                            @click="toggleType('Person')"
                        >
                            <span
                                class="legend-dot"
                                style="background: #67c23a"
                            ></span>
                            影人 ({{ typeCounts.Person }})
                        </button>
                        <button
                            class="legend-btn"
                            :class="{ disabled: !typeFilters.Genre }"
                            @click="toggleType('Genre')"
                        >
                            <span
                                class="legend-dot"
                                style="background: #e6a23c"
                            ></span>
                            类型 ({{ typeCounts.Genre }})
                        </button>
                    </div>
                </div>
            </div>

            <!-- 图谱主区域 -->
            <div class="graph-main">
                <KnowledgeGraph
                    :nodes="nodes"
                    :edges="edges"
                    :loading="loading"
                    :highlight-id="highlightId"
                    :hidden-types="hiddenTypes"
                    layout="force"
                    @node-click="handleNodeClick"
                    @node-hover="(n) => (selectedNode = n)"
                />
            </div>

            <!-- 状态栏 -->
            <div class="status-bar" v-if="meta">
                <div class="status-items">
                    <span class="status-item">
                        📊 节点: {{ meta.node_count }}
                    </span>
                    <span class="status-item">
                        🔗 边: {{ meta.edge_count }}
                    </span>
                    <span class="status-item">
                        ⏱️ {{ meta.query_time_ms }}ms
                    </span>
                    <el-tag
                        v-if="meta.truncated"
                        type="warning"
                        size="small"
                        effect="plain"
                    >
                        结果已截断
                    </el-tag>
                </div>

                <!-- 选中节点信息 -->
                <div class="selected-info" v-if="selectedNode">
                    <span class="info-label">{{
                        selectedNode.type === "Movie"
                            ? "🎬"
                            : selectedNode.type === "Person"
                              ? "🧑"
                              : "🏷️"
                    }}</span>
                    <strong>{{ selectedNode.label }}</strong>
                    <template v-if="selectedNode.properties?.rating">
                        · ⭐ {{ selectedNode.properties.rating }}
                    </template>
                    <template v-if="selectedNode.properties?.year">
                        · {{ selectedNode.properties.year }}
                    </template>
                    <template v-if="selectedNode.properties?.profession">
                        · {{ selectedNode.properties.profession }}
                    </template>
                    <span class="click-hint">（点击节点跳转详情）</span>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.graph-view {
    min-height: calc(100vh - var(--header-height) - 100px);
    display: flex;
    flex-direction: column;
}

.graph-header {
    margin-bottom: var(--space-xs);
    text-align: left;
    width: 100%;
}

.header-left {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-start;
    width: 100%;
    gap: 0;
}

.back-btn {
    align-self: flex-start;
    color: var(--text-secondary) !important;
    padding-left: 0 !important;
    margin-left: -4px;
    font-size: 0.85rem;
}

.graph-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-primary);
    text-align: left;

    .title-icon {
        margin-right: var(--space-xs);
    }

    .title-sub {
        color: var(--text-muted);
        font-weight: 400;
        font-size: 1.1rem;
    }
}

.graph-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
}

.control-panel {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-lg);
    align-items: center;
    padding: var(--space-md) var(--space-lg);

    &:hover {
        transform: none;
    }
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

    &:hover {
        border-color: var(--border-color-light);
    }

    &.disabled {
        opacity: 0.35;
    }
}

.legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.graph-main {
    flex: 0 0 auto;
    height: 55vh;
    margin-bottom: 0;
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

.selected-info {
    color: var(--text-secondary);
    font-size: 0.85rem;

    strong {
        color: var(--text-primary);
    }
}

.click-hint {
    color: var(--text-muted);
    font-size: 0.75rem;
    margin-left: var(--space-xs);
}

@media (max-width: 768px) {
    .control-panel {
        flex-direction: column;
        align-items: flex-start;
    }

    .graph-title {
        font-size: 1.3rem;

        .title-sub {
            font-size: 0.9rem;
        }
    }

    .graph-main {
        min-height: 350px;
        height: 45vh;
    }

    .status-bar {
        flex-direction: column;
        align-items: flex-start;
    }
}
</style>
