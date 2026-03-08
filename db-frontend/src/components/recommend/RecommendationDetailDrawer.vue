<script setup>
import { computed, ref, watch } from "vue";
import KnowledgeGraph from "@/components/graph/KnowledgeGraph.vue";
import { fetchRecommendationExplanation } from "@/composables/useRecommendations";
import { useThemeStore } from "@/stores/theme";
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
        default: "cfkg",
    },
});

const emit = defineEmits(["update:modelValue"]);
const themeStore = useThemeStore();

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
        explainError.value =
            err.response?.data?.detail || "知识路径加载失败";
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
            <div
                v-if="currentMovie"
                class="drawer-header"
                :class="themeStore.isDark ? 'theme-dark' : 'theme-light'"
            >
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

        <div
            v-if="currentMovie"
            class="drawer-body"
            :class="themeStore.isDark ? 'theme-dark' : 'theme-light'"
        >
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
                        <strong>{{ path.template || path.relation_label }}</strong>
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

            <section
                v-if="matchedEntities.length"
                class="drawer-panel"
            >
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

                <div
                    v-else-if="graphNodes.length"
                    class="graph-shell"
                >
                    <KnowledgeGraph
                        :nodes="graphNodes"
                        :edges="graphEdges"
                        :loading="explainLoading"
                        layout="force"
                        :min-height="340"
                    />
                </div>

                <div
                    v-else
                    class="graph-placeholder"
                >
                    暂无图谱证据
                </div>
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
    gap: 20px;
    width: 100%;
}

.poster-shell {
    border-radius: 18px;
    overflow: hidden;
    background: #0f172a;
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
    gap: 10px;
}

.header-kicker,
.panel-kicker {
    font-size: 0.82rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.theme-dark .header-kicker,
.theme-dark .panel-kicker {
    color: #8bb8c8;
}

.theme-light .header-kicker,
.theme-light .panel-kicker {
    color: #46687a;
}

.header-copy h2,
.panel-copy,
.path-card p,
.entity-group strong {
    margin: 0;
}

.header-copy h2 {
    font-size: 2rem;
    font-family: "Iowan Old Style", "Times New Roman", serif;
}

.drawer-body {
    display: grid;
    gap: 16px;
}

.drawer-panel {
    padding: 20px;
    border-radius: 18px;
}

.theme-dark .drawer-panel {
    background: #111827;
    border: 1px solid rgba(148, 163, 184, 0.16);
}

.theme-light .drawer-panel {
    background: #ffffff;
    border: 1px solid rgba(148, 163, 184, 0.16);
}

.path-list,
.entity-groups {
    display: grid;
    gap: 12px;
    margin-top: 12px;
}

.path-card {
    padding: 14px 16px;
    border-radius: 14px;
}

.theme-dark .path-card {
    background: rgba(148, 163, 184, 0.08);
}

.theme-light .path-card {
    background: rgba(148, 163, 184, 0.08);
}

.path-card strong {
    display: block;
    margin-bottom: 6px;
}

.theme-dark .path-card strong,
.theme-dark .header-copy p,
.theme-dark .panel-copy,
.theme-dark .path-card p,
.theme-dark .graph-placeholder {
    color: #c8d0dc;
}

.theme-light .path-card strong,
.theme-light .header-copy p,
.theme-light .panel-copy,
.theme-light .path-card p,
.theme-light .graph-placeholder {
    color: #475569;
}

.header-copy p,
.panel-copy,
.path-card p,
.graph-placeholder {
    line-height: 1.7;
}

.fallback-path {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 12px;
}

.fallback-chip,
.entity-tag {
    display: inline-flex;
    align-items: center;
    padding: 0.45rem 0.8rem;
    border-radius: 999px;
}

.theme-dark .fallback-chip,
.theme-dark .entity-tag {
    border: 1px solid rgba(148, 163, 184, 0.24);
    color: #dbe4f0;
    background: rgba(148, 163, 184, 0.08);
}

.theme-light .fallback-chip,
.theme-light .entity-tag {
    border: 1px solid rgba(148, 163, 184, 0.24);
    color: #334155;
    background: rgba(148, 163, 184, 0.08);
}

.entity-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 10px;
}

.graph-shell,
.graph-placeholder {
    margin-top: 14px;
}

.graph-placeholder {
    min-height: 220px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 16px;
}

.theme-dark .graph-placeholder {
    border: 1px dashed rgba(148, 163, 184, 0.24);
}

.theme-light .graph-placeholder {
    border: 1px dashed rgba(148, 163, 184, 0.24);
}

.drawer-alert {
    margin-top: 4px;
}

@media (max-width: 860px) {
    .drawer-header {
        grid-template-columns: 1fr;
    }

    .poster-shell {
        max-width: 220px;
    }
}
</style>
