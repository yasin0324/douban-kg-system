<script setup>
import { computed, onMounted, ref, watch } from "vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import {
    fetchRecommendationExplanation,
    useRecommendationFeed,
} from "@/composables/useRecommendations";
import { useAuthStore } from "@/stores/auth";
import { proxyImage } from "@/utils/image";
import { formatSourceAlgorithmLabel } from "@/utils/recommendation";

const authStore = useAuthStore();

const {
    data: recommendData,
    loading: recommendLoading,
    error: recommendError,
    loadRecommendations,
} = useRecommendationFeed({
    algorithm: "cfkg",
    limit: 6,
});

const explainMap = ref({});
const explainLoading = ref(false);
const selectedRecommendation = ref(null);
const recommendationDrawerVisible = ref(false);

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgZmlsbD0iIzBmMTcyYSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjQyIiBmaWxsPSIjMzM0MTU1IiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

const dnaTags = computed(() => {
    const highlights = recommendData.value?.profile_highlights || [];
    if (highlights.length) {
        return highlights.map((item) => item.label).slice(0, 6);
    }
    if (recommendData.value?.cold_start) {
        return ["冷启动中"];
    }
    return ["画像构建中"];
});

const dnaLogic = computed(() => {
    const highlights = recommendData.value?.profile_highlights || [];
    if (highlights.length) {
        const labels = highlights
            .slice(0, 3)
            .map((item) => item.label)
            .join("、");
        return `系统根据你近期高权重行为、导演偏好、类型共现和主题路径，构建出当前的兴趣基因画像（${labels}）。`;
    }
    if (recommendData.value?.cold_start) {
        return "当前仍处于冷启动阶段，系统会优先结合有限行为信号与稳定候选完成推荐。";
    }
    return "系统正在根据你的评分、喜欢和想看行为，逐步形成稳定的兴趣基因画像。";
});

const displayItems = computed(() =>
    (recommendData.value?.items || []).slice(0, 4).map((item) => {
        const explain = explainMap.value[item.movie.mid] || null;
        const path = explain?.reason_paths?.[0] || null;
        return {
            ...item,
            explain,
            pathSteps: path
                ? [
                      "用户",
                      `偏好电影：${path.representative_title}`,
                      `${path.relation_label}${path.matched_entities?.[0] ? `：${path.matched_entities[0]}` : ""}`,
                      `推荐结果：${item.movie.title}`,
                  ]
                : [],
            signalRows: Object.entries(item.score_breakdown || {})
                .sort((a, b) => b[1] - a[1])
                .map(([source, value]) => ({
                    label: formatSourceAlgorithmLabel(source),
                    value: Number(value).toFixed(3),
                })),
        };
    }),
);

onMounted(async () => {
    await loadPage();
});

watch(
    () => authStore.isLoggedIn,
    async (loggedIn) => {
        if (loggedIn) {
            await loadPage();
            return;
        }
        explainMap.value = {};
    },
);

async function loadPage() {
    if (!authStore.isLoggedIn) {
        return;
    }
    try {
        const payload = await loadRecommendations({
            algorithm: "cfkg",
            limit: 6,
        });
        await loadExplainSummaries(payload?.items || []);
    } catch (err) {
        console.error("推荐页加载失败:", err);
    }
}

async function loadExplainSummaries(items) {
    const topItems = items.slice(0, 4);
    if (!topItems.length) {
        explainMap.value = {};
        return;
    }

    explainLoading.value = true;
    const results = await Promise.allSettled(
        topItems.map((item) =>
            fetchRecommendationExplanation({
                target_mid: item.movie.mid,
                algorithm: "cfkg",
            }),
        ),
    );

    const nextMap = {};
    results.forEach((result, index) => {
        if (result.status === "fulfilled") {
            nextMap[topItems[index].movie.mid] = result.value;
        }
    });
    explainMap.value = nextMap;
    explainLoading.value = false;
}

function openRecommendationDetail(item) {
    selectedRecommendation.value = item;
    recommendationDrawerVisible.value = true;
}
</script>

<template>
    <div class="insights-view">
        <div class="insights-shell">
            <header class="page-header">
                <h1 class="page-title">🎯 个性化推荐</h1>
                <p class="page-subtitle">基于知识图谱的可解释推荐结果</p>
            </header>

            <template v-if="authStore.isLoggedIn">
                <section class="dna-panel">
                    <h2 class="panel-label">用户兴趣基因</h2>
                    <div class="dna-tags">
                        <span v-for="tag in dnaTags" :key="tag" class="dna-tag">
                            {{ tag }}
                        </span>
                    </div>
                    <p class="dna-logic">{{ dnaLogic }}</p>
                </section>

                <el-alert
                    v-if="recommendError"
                    class="page-alert"
                    type="warning"
                    show-icon
                    :closable="false"
                    :title="recommendError"
                />

                <section class="evidence-panel" v-loading="recommendLoading">
                    <h2 class="panel-label">可解释证据</h2>

                    <article
                        v-for="item in displayItems"
                        :key="item.movie.mid"
                        class="insight-card"
                    >
                        <div class="visual-layer">
                            <div class="poster-frame">
                                <img
                                    :src="
                                        proxyImage(item.movie.cover) ||
                                        defaultCover
                                    "
                                    :alt="item.movie.title"
                                    @error="
                                        (e) => (e.target.src = defaultCover)
                                    "
                                />
                            </div>
                            <div class="visual-copy">
                                <h3>{{ item.movie.title }}</h3>
                                <div class="rating-line">
                                    {{
                                        item.movie.rating
                                            ? `${item.movie.rating.toFixed(1)}/10`
                                            : "暂无评分"
                                    }}
                                </div>
                            </div>
                        </div>

                        <div class="logic-layer">
                            <div class="logic-block">
                                <span class="logic-title">推荐逻辑</span>
                                <p>{{ item.reasons?.[0] || "暂无推荐说明" }}</p>
                            </div>

                            <div
                                v-if="item.pathSteps.length"
                                class="logic-block"
                            >
                                <span class="logic-title">路径可视化</span>
                                <div class="path-rail">
                                    <div
                                        v-for="(step, index) in item.pathSteps"
                                        :key="`${item.movie.mid}-${step}`"
                                        class="path-step"
                                    >
                                        <div
                                            class="path-dot"
                                            :class="{
                                                active:
                                                    index ===
                                                    item.pathSteps.length - 1,
                                            }"
                                        />
                                        <div
                                            v-if="
                                                index !==
                                                item.pathSteps.length - 1
                                            "
                                            class="path-line"
                                        />
                                        <span class="path-label">{{
                                            step
                                        }}</span>
                                    </div>
                                </div>
                            </div>

                            <div
                                v-else-if="explainLoading"
                                class="logic-block logic-note"
                            >
                                正在整理路径证据...
                            </div>
                        </div>

                        <div class="signal-layer">
                            <span class="signal-title">排序信号</span>
                            <div class="score-line">
                                推荐值 {{ Number(item.score || 0).toFixed(3) }}
                            </div>

                            <div
                                v-if="item.source_algorithms?.length"
                                class="signal-tags"
                            >
                                <span
                                    v-for="source in item.source_algorithms"
                                    :key="source"
                                    class="signal-tag"
                                >
                                    {{ formatSourceAlgorithmLabel(source) }}
                                </span>
                            </div>

                            <div
                                v-if="item.signalRows.length"
                                class="signal-rows"
                            >
                                <div
                                    v-for="row in item.signalRows"
                                    :key="row.label"
                                    class="signal-row"
                                >
                                    <span>{{ row.label }}</span>
                                    <strong>{{ row.value }}</strong>
                                </div>
                            </div>

                            <button
                                type="button"
                                class="graph-button"
                                @click="openRecommendationDetail(item)"
                            >
                                查看完整知识路径
                            </button>
                        </div>
                    </article>

                    <el-empty
                        v-if="!recommendLoading && !displayItems.length"
                        :image-size="72"
                        description="当前没有可展示的推荐结果"
                    />
                </section>
            </template>

            <section v-else class="guest-panel card">
                <h2>登录后查看可解释推荐</h2>
                <p>
                    推荐页会展示真实的用户兴趣基因、推荐逻辑、路径证据和知识图谱解释。
                </p>
            </section>
        </div>

        <RecommendationDetailDrawer
            v-model="recommendationDrawerVisible"
            :item="selectedRecommendation"
            algorithm="cfkg"
        />
    </div>
</template>

<style scoped lang="scss">
.insights-view {
    min-height: 100%;
    padding: var(--space-xl) 0 var(--space-2xl);
}

.insights-shell {
    width: min(1280px, calc(100vw - 48px));
    margin: 0 auto;
}

.page-header {
    padding-bottom: var(--space-lg);
    border-bottom: 1px solid var(--border-color);
    margin-bottom: var(--space-xl);
}

.page-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-xs);
}

.page-subtitle {
    font-size: 0.9rem;
    color: var(--text-muted);
}

.panel-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-bottom: var(--space-md);
}

.dna-panel,
.evidence-panel,
.guest-panel {
    margin-bottom: var(--space-lg);
}

.dna-panel {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
}

.dna-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
    margin-bottom: var(--space-md);
}

.dna-tag {
    padding: 0.4rem 0.9rem;
    border-radius: var(--radius-md);
    font-size: 0.88rem;
    font-weight: 500;
    background: var(--color-accent-bg);
    color: var(--color-accent);
    border: 1px solid rgba(0, 181, 29, 0.2);
    transition: all var(--transition-fast);

    &:hover {
        background: var(--color-accent);
        color: #fff;
    }
}

.dna-logic {
    line-height: 1.7;
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin: 0;
}

.page-alert {
    margin-bottom: var(--space-md);
}

.insight-card {
    display: grid;
    grid-template-columns: 290px minmax(0, 1fr) 220px;
    gap: 0;
    margin-top: var(--space-md);
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-sm);
    transition: all var(--transition-normal);

    &:hover {
        border-color: var(--border-color-light);
        box-shadow: var(--shadow-md);
        transform: translateY(-2px);
    }
}

.visual-layer,
.logic-layer,
.signal-layer {
    padding: var(--space-md);
}

.visual-layer {
    display: grid;
    grid-template-columns: 118px minmax(0, 1fr);
    gap: var(--space-md);
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-color);
}

.logic-layer {
    border-right: 1px solid var(--border-color);
}

.poster-frame {
    border-radius: var(--radius-md);
    overflow: hidden;
    background: var(--bg-primary);
    aspect-ratio: 2 / 3;
    box-shadow: var(--shadow-md);

    img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
}

.visual-copy {
    display: flex;
    flex-direction: column;
    justify-content: space-between;

    h3 {
        margin: 0;
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-primary);
        line-height: 1.4;
    }
}

.rating-line {
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--color-rating);
}

.logic-title,
.signal-title {
    display: block;
    margin-bottom: var(--space-sm);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
}

.logic-block p {
    line-height: 1.7;
    color: var(--text-secondary);
    font-size: 0.9rem;
    margin: 0;
}

.logic-note {
    font-size: 0.9rem;
    color: var(--text-muted);
}

.logic-block + .logic-block,
.signal-tags,
.signal-rows {
    margin-top: var(--space-md);
}

.path-rail {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-top: var(--space-sm);
    overflow-x: auto;
}

.path-step {
    position: relative;
    min-width: 120px;
    padding-top: 20px;
    text-align: center;
    flex: 1 0 0;
}

.path-dot {
    position: absolute;
    top: 0;
    left: 50%;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    transform: translateX(-50%);
    background: var(--bg-secondary);
    border: 2px solid var(--border-color-light);
    transition: all var(--transition-fast);

    &.active {
        background: var(--color-accent);
        border-color: var(--color-accent);
        box-shadow: 0 0 10px var(--color-accent-bg);
    }
}

.path-line {
    position: absolute;
    top: 6px;
    left: calc(50% + 7px);
    width: calc(100% - 14px);
    height: 2px;
    background: var(--border-color-light);
}

.path-label {
    display: block;
    line-height: 1.4;
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.score-line {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);
}

.signal-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.signal-tag {
    padding: 0.28rem 0.65rem;
    border-radius: 999px;
    font-size: 0.8rem;
    background: var(--color-accent-bg);
    color: var(--color-accent);
    border: 1px solid rgba(0, 181, 29, 0.2);
}

.signal-rows {
    display: grid;
    gap: var(--space-sm);
}

.signal-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
    font-size: 0.85rem;
    color: var(--text-secondary);

    strong {
        color: var(--text-primary);
        font-weight: 600;
    }
}

.graph-button {
    margin-top: var(--space-md);
    width: 100%;
    padding: 0.6rem 1rem;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 500;
    border: 1px solid var(--border-color-light);
    background: var(--bg-secondary);
    color: var(--text-primary);
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--color-accent);
        color: var(--color-accent);
        background: var(--color-accent-bg);
    }
}

.guest-panel {
    padding: var(--space-xl);
    text-align: center;

    h2 {
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: var(--space-sm);
    }

    p {
        color: var(--text-secondary);
        line-height: 1.7;
    }
}

@media (max-width: 1180px) {
    .insight-card {
        grid-template-columns: 240px minmax(0, 1fr);
    }

    .signal-layer {
        grid-column: 1 / -1;
        border-top: 1px solid var(--border-color);
    }
}

@media (max-width: 860px) {
    .insights-shell {
        width: min(100vw - 24px, 1280px);
    }

    .insight-card {
        grid-template-columns: 1fr;
    }

    .visual-layer {
        border-right: none;
        border-bottom: 1px solid var(--border-color);
        grid-template-columns: 104px minmax(0, 1fr);
    }

    .logic-layer {
        border-right: none;
        border-bottom: 1px solid var(--border-color);
    }
}

@media (max-width: 640px) {
    .page-title {
        font-size: 1.4rem;
    }

    .dna-tag {
        width: 100%;
        text-align: center;
    }

    .visual-layer {
        grid-template-columns: 1fr;
    }

    .poster-frame {
        max-width: 160px;
    }

    .path-step {
        min-width: 100px;
    }
}
</style>
