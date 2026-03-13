<script setup>
import { computed, ref, watch } from "vue";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import { fetchRecommendationExplanation } from "@/composables/useRecommendations";
import { proxyImage } from "@/utils/image";

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
        default: "kg_path",
    },
});

const emit = defineEmits(["update:modelValue"]);

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgZmlsbD0iIzBjMTExYiIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjQyIiBmaWxsPSIjMzM0MTU1IiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

const drawerVisible = computed({
    get: () => props.modelValue,
    set: (value) => emit("update:modelValue", value),
});

const explainLoading = ref(false);
const explainPayload = ref(null);
const explainError = ref("");
const cacheKey = ref("");

const currentMovie = computed(() => props.item?.movie || null);
const currentReasons = computed(() => props.item?.reasons || []);
const fallbackPath = computed(() => props.item?.pathNodes || []);
const matchedEntities = computed(
    () => explainPayload.value?.matched_entities || [],
);
const reasonPaths = computed(() => explainPayload.value?.reason_paths || []);
const graphNodes = computed(() => explainPayload.value?.nodes || []);
const graphEdges = computed(() => explainPayload.value?.edges || []);
const graphHighlightId = computed(() =>
    currentMovie.value?.mid ? `movie_${currentMovie.value.mid}` : "",
);

const headline = computed(() => {
    if (currentReasons.value.length) {
        return currentReasons.value[0];
    }
    return "推荐路径与用户兴趣画像存在明确关联。";
});

const loadExplanation = async () => {
    if (!drawerVisible.value || !currentMovie.value?.mid) {
        return;
    }
    if (props.item?.sample) {
        explainPayload.value = null;
        explainError.value = "";
        return;
    }

    const nextKey = `${props.algorithm}:${currentMovie.value.mid}`;
    if (cacheKey.value === nextKey) {
        return;
    }

    explainLoading.value = true;
    explainError.value = "";
    try {
        explainPayload.value = await fetchRecommendationExplanation({
            target_mid: currentMovie.value.mid,
            algorithm: props.algorithm,
        });
        cacheKey.value = nextKey;
    } catch (err) {
        explainPayload.value = null;
        explainError.value = err.response?.data?.detail || "知识路径加载失败";
    } finally {
        explainLoading.value = false;
    }
};

watch(
    () => [drawerVisible.value, currentMovie.value?.mid, props.algorithm],
    ([visible]) => {
        if (visible) {
            loadExplanation();
        }
    },
);
</script>

<template>
    <el-drawer
        v-model="drawerVisible"
        class="insight-drawer"
        size="min(94vw, 1080px)"
    >
        <template #header>
            <div v-if="currentMovie" class="drawer-header">
                <div class="poster-shell">
                    <img
                        :src="proxyImage(currentMovie.cover) || defaultCover"
                        :alt="currentMovie.title"
                        @error="(e) => (e.target.src = defaultCover)"
                    />
                </div>
                <div class="header-copy">
                    <span class="header-kicker">知识路径</span>
                    <h2>{{ currentMovie.title }}</h2>
                    <p>{{ headline }}</p>
                </div>
            </div>
        </template>

        <div v-if="currentMovie" class="drawer-body">
            <section class="drawer-panel">
                <span class="panel-kicker">推荐逻辑</span>
                <p class="panel-copy">{{ headline }}</p>
            </section>

            <section class="drawer-panel">
                <span class="panel-kicker">路径摘要</span>

                <div v-if="reasonPaths.length" class="path-list">
                    <article
                        v-for="path in reasonPaths"
                        :key="`${path.representative_mid}-${path.relation_type}`"
                        class="path-card"
                    >
                        <strong>{{
                            path.template || path.relation_label
                        }}</strong>
                        <p>
                            {{ path.representative_title }} ·
                            {{ (path.matched_entities || []).join(" / ") }}
                        </p>
                    </article>
                </div>

                <div v-else-if="fallbackPath.length" class="fallback-path">
                    <span
                        v-for="step in fallbackPath"
                        :key="step"
                        class="fallback-chip"
                    >
                        {{ step }}
                    </span>
                </div>

                <el-empty
                    v-else-if="!explainLoading"
                    :image-size="56"
                    description="暂无路径数据"
                />
            </section>

            <section v-if="matchedEntities.length" class="drawer-panel">
                <span class="panel-kicker">命中实体</span>
                <div class="entity-groups">
                    <div
                        v-for="group in matchedEntities"
                        :key="group.type"
                        class="entity-group"
                    >
                        <strong>{{ group.type }}</strong>
                        <div class="entity-tags">
                            <span
                                v-for="entity in group.items"
                                :key="entity"
                                class="entity-tag"
                            >
                                {{ entity }}
                            </span>
                        </div>
                    </div>
                </div>
            </section>

            <section class="drawer-panel graph-panel">
                <span class="panel-kicker">知识图谱</span>

                <div
                    v-if="explainLoading && !graphNodes.length"
                    class="graph-placeholder"
                >
                    正在载入知识路径...
                </div>

                <div v-else-if="graphNodes.length" class="graph-shell">
                    <KnowledgeGraph
                        :nodes="graphNodes"
                        :edges="graphEdges"
                        :loading="explainLoading"
                        :highlight-id="graphHighlightId"
                        layout="force"
                        :min-height="340"
                    />
                </div>

                <div v-else class="graph-placeholder">暂无图谱证据</div>
            </section>

            <el-alert
                v-if="explainError"
                class="drawer-alert"
                type="warning"
                show-icon
                :closable="false"
                :title="explainError"
            />
        </div>
    </el-drawer>
</template>

<style scoped lang="scss">
.drawer-header {
    display: grid;
    grid-template-columns: 180px minmax(0, 1fr);
    gap: var(--space-lg);
    width: 100%;
}

.poster-shell {
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--bg-primary);
    min-height: 240px;

    img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
}

.header-copy {
    display: grid;
    align-content: center;
    gap: var(--space-sm);
}

.header-kicker,
.panel-kicker {
    font-size: 0.78rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 600;
    color: var(--text-muted);
}

.header-copy h2,
.panel-copy,
.path-card p,
.entity-group strong {
    margin: 0;
}

.header-copy h2 {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-primary);
}

.header-copy p {
    color: var(--text-secondary);
    line-height: 1.7;
}

.drawer-body {
    display: grid;
    gap: var(--space-md);
}

.drawer-panel {
    padding: var(--space-lg);
    border-radius: var(--radius-lg);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
}

.path-list,
.entity-groups {
    display: grid;
    gap: var(--space-sm);
    margin-top: var(--space-sm);
}

.path-card {
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-md);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
}

.path-card strong {
    display: block;
    margin-bottom: 4px;
    color: var(--text-primary);
    font-weight: 600;
}

.panel-copy,
.path-card p,
.graph-placeholder {
    line-height: 1.7;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.fallback-path {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
    margin-top: var(--space-sm);
}

.fallback-chip,
.entity-tag {
    display: inline-flex;
    align-items: center;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    font-size: 0.85rem;
    border: 1px solid var(--border-color-light);
    color: var(--text-secondary);
    background: var(--bg-secondary);
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--color-accent);
        color: var(--color-accent);
        background: var(--color-accent-bg);
    }
}

.entity-group strong {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.entity-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
    margin-top: var(--space-sm);
}

.graph-shell,
.graph-placeholder {
    margin-top: var(--space-sm);
}

.graph-placeholder {
    min-height: 220px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    border: 1px dashed var(--border-color-light);
    color: var(--text-muted);
    font-size: 0.9rem;
}

.drawer-alert {
    margin-top: 4px;
}

@media (max-width: 860px) {
    .drawer-header {
        grid-template-columns: 1fr;
    }

    .poster-shell {
        max-width: 200px;
    }
}
</style>
