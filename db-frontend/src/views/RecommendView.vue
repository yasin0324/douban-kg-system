<script setup>
import { computed, onMounted, ref, watch } from "vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import { fetchRecommendationExplanation, useRecommendationFeed } from "@/composables/useRecommendations";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { proxyImage } from "@/utils/image";
import { formatSourceAlgorithmLabel } from "@/utils/recommendation";

const authStore = useAuthStore();
const themeStore = useThemeStore();

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
        const labels = highlights.slice(0, 3).map((item) => item.label).join("、");
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
        const payload = await loadRecommendations({ algorithm: "cfkg", limit: 6 });
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
    <div
        class="insights-view"
        :class="themeStore.isDark ? 'theme-dark' : 'theme-light'"
    >
        <div class="insights-shell">
            <header class="page-header">
                <span class="page-route">核心可解释推荐页 /recommend</span>
            </header>

            <template v-if="authStore.isLoggedIn">
                <section class="dna-panel">
                    <h2>用户兴趣基因</h2>
                    <div class="dna-tags">
                        <span
                            v-for="tag in dnaTags"
                            :key="tag"
                            class="dna-tag"
                        >
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

                <section
                    class="evidence-panel"
                    v-loading="recommendLoading"
                >
                    <h2>可解释证据</h2>

                    <article
                        v-for="item in displayItems"
                        :key="item.movie.mid"
                        class="insight-card"
                    >
                        <div class="visual-layer">
                            <div class="poster-frame">
                                <img
                                    :src="proxyImage(item.movie.cover) || defaultCover"
                                    :alt="item.movie.title"
                                    @error="(e) => (e.target.src = defaultCover)"
                                />
                            </div>
                            <div class="visual-copy">
                                <h3>{{ item.movie.title }}</h3>
                                <div class="rating-line">
                                    {{ item.movie.rating ? `${item.movie.rating.toFixed(1)}/10` : "暂无评分" }}
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
                                            :class="{ active: index === item.pathSteps.length - 1 }"
                                        />
                                        <div
                                            v-if="index !== item.pathSteps.length - 1"
                                            class="path-line"
                                        />
                                        <span class="path-label">{{ step }}</span>
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

            <section v-else class="guest-panel">
                <h2>登录后查看可解释推荐</h2>
                <p>推荐页会展示真实的用户兴趣基因、推荐逻辑、路径证据和知识图谱解释。</p>
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
    padding: 20px 0 40px;
}

.theme-dark {
    background:
        radial-gradient(circle at top center, rgba(93, 136, 168, 0.18), transparent 22%),
        linear-gradient(180deg, #0a0f18 0%, #0d1119 100%);
    color: #eef2f7;
}

.theme-light {
    background:
        radial-gradient(circle at top center, rgba(93, 136, 168, 0.08), transparent 24%),
        linear-gradient(180deg, #f4f4f2 0%, #eeefec 100%);
    color: #17202b;
}

.insights-shell {
    width: min(1280px, calc(100vw - 48px));
    margin: 0 auto;
}

.page-header {
    padding: 12px 8px 18px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    margin-bottom: 18px;
}

.page-route,
.dna-panel h2,
.evidence-panel h2,
.visual-copy h3 {
    font-family: "Iowan Old Style", "Times New Roman", serif;
}

.page-route {
    font-size: 1.15rem;
}

.dna-panel,
.evidence-panel,
.guest-panel {
    margin-bottom: 18px;
}

.dna-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin: 14px 0;
}

.dna-tag {
    padding: 0.85rem 1.5rem;
    border-radius: 14px;
    font-size: 1rem;
    font-family: "Iowan Old Style", "Times New Roman", serif;
}

.theme-dark .dna-tag {
    border: 1px solid rgba(173, 220, 235, 0.62);
    background: linear-gradient(180deg, rgba(11, 19, 31, 0.86), rgba(18, 28, 39, 0.9));
    color: #f3f4f6;
    box-shadow:
        inset 0 0 0 1px rgba(212, 248, 255, 0.08),
        0 0 24px rgba(151, 211, 229, 0.1);
}

.theme-light .dna-tag {
    border: 1px solid rgba(84, 116, 132, 0.34);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(236, 240, 243, 0.96));
    color: #15202b;
    box-shadow:
        inset 0 0 0 1px rgba(255, 255, 255, 0.64),
        0 8px 18px rgba(72, 88, 102, 0.08);
}

.dna-logic,
.guest-panel p,
.logic-block p {
    line-height: 1.7;
}

.theme-dark .dna-logic,
.theme-dark .guest-panel p,
.theme-dark .logic-block p,
.theme-dark .logic-note {
    color: #d3d8e1;
}

.theme-light .dna-logic,
.theme-light .guest-panel p,
.theme-light .logic-block p,
.theme-light .logic-note {
    color: #485467;
}

.page-alert {
    margin-bottom: 16px;
}

.insight-card {
    display: grid;
    grid-template-columns: 290px minmax(0, 1fr) 220px;
    gap: 0;
    margin-top: 14px;
    border-radius: 16px;
    overflow: hidden;
}

.theme-dark .insight-card {
    border: 1px solid rgba(148, 163, 184, 0.18);
    background: linear-gradient(180deg, rgba(17, 24, 39, 0.96), rgba(15, 23, 42, 0.92));
    box-shadow: 0 16px 40px rgba(0, 0, 0, 0.25);
}

.theme-light .insight-card {
    border: 1px solid rgba(148, 163, 184, 0.2);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(245, 247, 250, 0.98));
    box-shadow: 0 16px 32px rgba(15, 23, 42, 0.08);
}

.visual-layer,
.logic-layer,
.signal-layer {
    padding: 18px;
}

.visual-layer {
    display: grid;
    grid-template-columns: 118px minmax(0, 1fr);
    gap: 16px;
}

.logic-layer {
    border-left: 1px solid rgba(148, 163, 184, 0.12);
    border-right: 1px solid rgba(148, 163, 184, 0.12);
}

.poster-frame {
    border-radius: 12px;
    overflow: hidden;
    background: #0f172a;
    aspect-ratio: 2 / 3;
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28);

    img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
}

.visual-copy {
    display: flex;
    flex-direction: column;
    justify-content: space-between;

    h3 {
        margin: 0;
        font-size: 1.15rem;
        line-height: 1.15;
    }
}

.rating-line {
    font-size: 1.9rem;
    font-family: "Iowan Old Style", "Times New Roman", serif;
}

.logic-title,
.signal-title {
    display: block;
    margin-bottom: 10px;
    font-family: "Iowan Old Style", "Times New Roman", serif;
}

.logic-block + .logic-block,
.signal-tags,
.signal-rows {
    margin-top: 16px;
}

.path-rail {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-top: 12px;
    overflow-x: auto;
}

.path-step {
    position: relative;
    min-width: 132px;
    padding-top: 18px;
    text-align: center;
    flex: 1 0 0;
}

.path-dot {
    position: absolute;
    top: 0;
    left: 50%;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    transform: translateX(-50%);
}

.theme-dark .path-dot {
    background: rgba(148, 163, 184, 0.18);
    border: 1px solid rgba(148, 163, 184, 0.42);
}

.theme-light .path-dot {
    background: rgba(148, 163, 184, 0.16);
    border: 1px solid rgba(100, 116, 139, 0.28);
}

.theme-dark .path-dot.active {
    background: #c6f0ff;
    box-shadow: 0 0 18px rgba(190, 239, 255, 0.42);
}

.theme-light .path-dot.active {
    background: #3e6c83;
    box-shadow: 0 0 14px rgba(62, 108, 131, 0.18);
}

.path-line {
    position: absolute;
    top: 8px;
    left: calc(50% + 9px);
    width: calc(100% - 18px);
    height: 2px;
}

.theme-dark .path-line {
    background: linear-gradient(90deg, rgba(120, 144, 156, 0.55), rgba(196, 240, 255, 0.65));
}

.theme-light .path-line {
    background: linear-gradient(90deg, rgba(148, 163, 184, 0.45), rgba(62, 108, 131, 0.48));
}

.path-label {
    display: block;
    line-height: 1.4;
    font-size: 0.95rem;
}

.score-line {
    font-family: "Iowan Old Style", "Times New Roman", serif;
    font-size: 1.35rem;
}

.signal-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.signal-tag {
    padding: 0.35rem 0.7rem;
    border-radius: 999px;
    font-size: 0.84rem;
}

.theme-dark .signal-tag {
    background: rgba(148, 163, 184, 0.12);
    color: #dbe4f0;
}

.theme-light .signal-tag {
    background: rgba(148, 163, 184, 0.1);
    color: #334155;
}

.signal-rows {
    display: grid;
    gap: 10px;
}

.signal-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.graph-button {
    margin-top: 20px;
    width: 100%;
    padding: 0.72rem 1rem;
    border-radius: 12px;
    cursor: pointer;
}

.theme-dark .graph-button {
    border: 1px solid rgba(227, 243, 252, 0.38);
    background: rgba(15, 23, 42, 0.6);
    color: #eef2f7;
}

.theme-light .graph-button {
    border: 1px solid rgba(62, 108, 131, 0.24);
    background: rgba(255, 255, 255, 0.82);
    color: #1f2937;
}

.guest-panel {
    padding: 28px;
    border-radius: 18px;
}

.theme-dark .guest-panel {
    background: rgba(17, 24, 39, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.16);
}

.theme-light .guest-panel {
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(148, 163, 184, 0.16);
}

@media (max-width: 1180px) {
    .insight-card {
        grid-template-columns: 240px minmax(0, 1fr);
    }

    .signal-layer {
        grid-column: 1 / -1;
        border-top: 1px solid rgba(148, 163, 184, 0.12);
    }
}

@media (max-width: 860px) {
    .insights-shell {
        width: min(100vw - 24px, 1280px);
    }

    .insight-card {
        grid-template-columns: 1fr;
    }

    .logic-layer {
        border-left: none;
        border-right: none;
        border-top: 1px solid rgba(148, 163, 184, 0.12);
        border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    }

    .visual-layer {
        grid-template-columns: 104px minmax(0, 1fr);
    }
}

@media (max-width: 640px) {
    .page-route {
        font-size: 1rem;
    }

    .dna-tag {
        width: 100%;
        text-align: center;
    }

    .visual-layer {
        grid-template-columns: 1fr;
    }

    .poster-frame {
        max-width: 180px;
    }

    .path-step {
        min-width: 120px;
    }
}
</style>
