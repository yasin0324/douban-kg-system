<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import { fetchRecommendationExplanation } from "@/composables/useRecommendations";
import {
    formatAlgorithmLabel,
    formatScore,
    formatSourceAlgorithmLabel,
} from "@/utils/recommendation";

const props = defineProps({
    modelValue: {
        type: Boolean,
        default: false,
    },
    item: {
        type: Object,
        default: null,
    },
    algorithm: {
        type: String,
        default: "cfkg",
    },
});

const emit = defineEmits(["update:modelValue"]);

const router = useRouter();
const drawerVisible = computed({
    get: () => props.modelValue,
    set: (value) => emit("update:modelValue", value),
});
const activeTab = ref("reasons");
const metricsPanels = ref([]);
const explainLoading = ref(false);
const explainError = ref("");
const explainPayload = ref(null);
const explainCacheKey = ref("");

const currentMovie = computed(() => props.item?.movie || null);
const breakdownEntries = computed(() =>
    Object.entries(props.item?.score_breakdown || {}).sort(
        (a, b) => b[1] - a[1],
    ),
);
const profileHighlights = computed(
    () => explainPayload.value?.profile_highlights || [],
);
const representativeMovies = computed(
    () => explainPayload.value?.representative_movies || [],
);
const profileReasons = computed(() => {
    const reasons = [
        ...(props.item?.reasons || []),
        ...(explainPayload.value?.profile_reasons || []),
    ];
    return [...new Set(reasons.filter(Boolean))].slice(0, 4);
});
const negativeSignals = computed(() => {
    const signals = [
        ...(props.item?.negative_signals || []),
        ...(explainPayload.value?.negative_signals || []),
    ];
    return [...new Set(signals.filter(Boolean))].slice(0, 3);
});

const loadExplanation = async () => {
    if (!drawerVisible.value || !currentMovie.value?.mid) {
        return;
    }

    const cacheKey = [currentMovie.value.mid, props.algorithm].join("|");
    if (cacheKey === explainCacheKey.value) {
        return;
    }

    explainLoading.value = true;
    explainError.value = "";
    try {
        explainPayload.value = await fetchRecommendationExplanation({
            target_mid: currentMovie.value.mid,
            algorithm: props.algorithm,
        });
        explainCacheKey.value = cacheKey;
    } catch (err) {
        explainError.value =
            err.response?.data?.detail || "推荐解释加载失败，请稍后重试";
        explainPayload.value = null;
    } finally {
        explainLoading.value = false;
    }
};

const handleNodeClick = (node) => {
    const rawId = node.id.split("_").slice(1).join("_");
    drawerVisible.value = false;
    if (node.type === "Movie") {
        router.push(`/movies/${rawId}`);
        return;
    }
    if (node.type === "Person") {
        router.push(`/persons/${rawId}`);
        return;
    }
    if (node.type === "Genre") {
        router.push({ path: "/movies/filter", query: { genre: node.label } });
    }
};

const goMovieDetail = () => {
    if (!currentMovie.value?.mid) return;
    drawerVisible.value = false;
    router.push(`/movies/${currentMovie.value.mid}`);
};

const goMovieGraph = () => {
    if (!currentMovie.value?.mid) return;
    drawerVisible.value = false;
    router.push(`/graph/movie/${currentMovie.value.mid}`);
};

watch(
    () => [drawerVisible.value, currentMovie.value?.mid, props.algorithm],
    ([visible]) => {
        if (visible) {
            loadExplanation();
            return;
        }
        activeTab.value = "reasons";
        metricsPanels.value = [];
    },
);
</script>

<template>
    <el-drawer
        v-model="drawerVisible"
        size="720px"
        class="recommendation-drawer"
    >
        <template #header>
            <div class="drawer-header" v-if="currentMovie">
                <div>
                    <h2 class="drawer-title">{{ currentMovie.title }}</h2>
                    <p class="drawer-subtitle">
                        {{ formatAlgorithmLabel(algorithm) }} · 推荐值
                        {{ formatScore(item?.score) }}
                    </p>
                </div>
                <div class="drawer-header-tags">
                    <el-tag
                        v-for="source in item?.source_algorithms || []"
                        :key="source"
                        type="success"
                        effect="plain"
                    >
                        {{ formatSourceAlgorithmLabel(source) }}
                    </el-tag>
                </div>
            </div>
        </template>

        <div v-if="currentMovie" class="drawer-body">
            <div class="drawer-summary card">
                <div class="summary-block">
                    <span class="summary-label">推荐理由</span>
                    <ul class="reason-list">
                        <li v-for="reason in profileReasons" :key="reason">
                            {{ reason }}
                        </li>
                    </ul>
                </div>

                <div v-if="profileHighlights.length" class="summary-block">
                    <span class="summary-label">画像标签</span>
                    <div class="chip-row">
                        <el-tag
                            v-for="highlight in profileHighlights"
                            :key="`${highlight.type}-${highlight.label}`"
                            size="small"
                            effect="plain"
                            round
                        >
                            {{ highlight.label }}
                        </el-tag>
                    </div>
                </div>

                <div
                    v-if="representativeMovies.length"
                    class="summary-block"
                >
                    <span class="summary-label">代表兴趣电影</span>
                    <div class="chip-row">
                        <el-tag
                            v-for="movie in representativeMovies"
                            :key="movie.mid"
                            size="small"
                            round
                        >
                            {{ movie.title }}
                        </el-tag>
                    </div>
                </div>

                <div class="summary-actions">
                    <el-button type="primary" @click="goMovieDetail">
                        电影详情
                    </el-button>
                    <el-button @click="goMovieGraph">知识图谱</el-button>
                    <el-button plain @click="goMovieDetail">前往评分</el-button>
                </div>
            </div>

            <el-tabs v-model="activeTab" class="drawer-tabs">
                <el-tab-pane label="推荐理由" name="reasons">
                    <div class="panel-stack">
                        <div class="info-card card">
                            <h3 class="panel-title">画像命中点</h3>
                            <ul
                                v-if="profileReasons.length"
                                class="reason-list compact"
                            >
                                <li v-for="reason in profileReasons" :key="reason">
                                    {{ reason }}
                                </li>
                            </ul>
                            <el-empty
                                v-else-if="!explainLoading"
                                description="当前结果暂无更多画像命中说明"
                            />
                        </div>

                        <div class="info-card card">
                            <h3 class="panel-title">命中解释路径</h3>
                            <div
                                v-if="explainPayload?.reason_paths?.length"
                                class="reason-paths"
                            >
                                <div
                                    v-for="path in explainPayload.reason_paths"
                                    :key="
                                        `${path.representative_mid}-${path.relation_type}`
                                    "
                                    class="reason-path-item"
                                >
                                    <span class="path-title">
                                        {{ path.representative_title }} ·
                                        {{ path.relation_label }}
                                    </span>
                                    <div class="chip-row">
                                        <el-tag
                                            v-for="entity in path.matched_entities"
                                            :key="entity"
                                            size="small"
                                            effect="plain"
                                        >
                                            {{ entity }}
                                        </el-tag>
                                    </div>
                                </div>
                            </div>
                            <el-empty
                                v-else-if="!explainLoading"
                                description="暂无更细粒度的路径说明"
                            />
                        </div>

                        <div class="info-card card">
                            <h3 class="panel-title">图谱命中实体</h3>
                            <div
                                v-if="explainPayload?.matched_entities?.length"
                                class="entity-groups"
                            >
                                <div
                                    v-for="group in explainPayload.matched_entities"
                                    :key="group.type"
                                    class="entity-group"
                                >
                                    <span class="entity-title">
                                        {{ group.type }}
                                    </span>
                                    <div class="chip-row">
                                        <el-tag
                                            v-for="entity in group.items"
                                            :key="entity"
                                            size="small"
                                        >
                                            {{ entity }}
                                        </el-tag>
                                    </div>
                                </div>
                            </div>
                            <el-empty
                                v-else-if="!explainLoading"
                                description="当前结果主要由算法聚合信号支撑"
                            />
                        </div>
                    </div>
                </el-tab-pane>

                <el-tab-pane label="关系可视化" name="graph">
                    <div class="graph-panel card">
                        <div class="graph-header">
                            <div>
                                <h3 class="panel-title">推荐证据小图</h3>
                                <p class="graph-hint">
                                    仅展示少量代表兴趣电影与目标电影之间的关键证据链。
                                </p>
                            </div>
                        </div>
                        <el-alert
                            v-if="explainError"
                            :title="explainError"
                            type="warning"
                            show-icon
                            :closable="false"
                        />
                        <KnowledgeGraph
                            v-else
                            :nodes="explainPayload?.nodes || []"
                            :edges="explainPayload?.edges || []"
                            :loading="explainLoading"
                            :highlight-id="`movie_${currentMovie.mid}`"
                            layout="force"
                            :min-height="320"
                            @node-click="handleNodeClick"
                        />
                        <p
                            v-if="
                                explainPayload &&
                                explainPayload.meta &&
                                !explainPayload.meta.has_graph_evidence
                            "
                            class="graph-empty-tip"
                        >
                            当前卡片更依赖画像聚合和算法信号，因此图中补充了偏好提示节点。
                        </p>
                    </div>
                </el-tab-pane>

                <el-tab-pane label="算法指标" name="metrics">
                    <div class="metrics-panel card">
                        <el-collapse v-model="metricsPanels">
                            <el-collapse-item
                                title="查看推荐值与分支贡献"
                                name="scores"
                            >
                                <div class="metrics-content">
                                    <div class="metric-row">
                                        <span>推荐值</span>
                                        <strong>{{ formatScore(item?.score) }}</strong>
                                    </div>
                                    <div
                                        v-if="breakdownEntries.length"
                                        class="metric-breakdown"
                                    >
                                        <div
                                            v-for="[source, score] in breakdownEntries"
                                            :key="source"
                                            class="metric-row"
                                        >
                                            <span>
                                                {{
                                                    formatSourceAlgorithmLabel(
                                                        source,
                                                    )
                                                }}
                                            </span>
                                            <strong>{{
                                                formatScore(score)
                                            }}</strong>
                                        </div>
                                    </div>
                                    <div
                                        v-if="negativeSignals.length"
                                        class="metric-signals"
                                    >
                                        <span class="summary-label">弱负反馈降权</span>
                                        <ul class="reason-list compact">
                                            <li
                                                v-for="signal in negativeSignals"
                                                :key="signal"
                                            >
                                                {{ signal }}
                                            </li>
                                        </ul>
                                    </div>
                                    <el-empty
                                        v-if="
                                            !breakdownEntries.length &&
                                            !negativeSignals.length
                                        "
                                        description="当前算法没有额外的指标明细"
                                    />
                                </div>
                            </el-collapse-item>
                        </el-collapse>
                    </div>
                </el-tab-pane>
            </el-tabs>
        </div>
    </el-drawer>
</template>

<style scoped lang="scss">
.drawer-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-md);
    width: 100%;
}

.drawer-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
}

.drawer-subtitle {
    margin-top: 6px;
    color: var(--text-secondary);
    font-size: 0.92rem;
}

.drawer-header-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.drawer-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
}

.drawer-summary,
.info-card,
.graph-panel,
.metrics-panel {
    padding: var(--space-lg);
}

.drawer-summary {
    display: grid;
    gap: var(--space-lg);
}

.summary-label,
.panel-title,
.path-title,
.entity-title {
    color: var(--text-primary);
    font-weight: 600;
}

.reason-list {
    margin: var(--space-sm) 0 0;
    padding-left: 18px;
    color: var(--text-secondary);
}

.reason-list.compact {
    margin-top: var(--space-sm);
}

.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
    margin-top: var(--space-sm);
}

.summary-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
}

.panel-stack {
    display: grid;
    gap: var(--space-lg);
}

.reason-paths,
.entity-groups {
    display: grid;
    gap: var(--space-md);
    margin-top: var(--space-md);
}

.reason-path-item,
.entity-group {
    padding: var(--space-md);
    border-radius: var(--radius-md);
    background: var(--bg-primary);
}

.graph-panel {
    display: grid;
    gap: var(--space-md);
}

.graph-hint,
.graph-empty-tip {
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.metrics-content {
    display: grid;
    gap: var(--space-sm);
}

.metric-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-md);
    color: var(--text-secondary);
}

.metric-signals {
    padding-top: var(--space-sm);
    border-top: 1px solid var(--border-color);
}

@media (max-width: 768px) {
    .drawer-header {
        flex-direction: column;
    }

    .summary-actions {
        flex-direction: column;

        .el-button {
            width: 100%;
        }
    }
}
</style>
