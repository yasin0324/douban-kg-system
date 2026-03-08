<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import MovieList from "@/components/movie/MovieList.vue";
import RecommendationCard from "@/components/recommend/RecommendationCard.vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import { moviesApi } from "@/api/movies";
import { useAuthStore } from "@/stores/auth";
import { useRecommendationFeed } from "@/composables/useRecommendations";
import { useRecommendationFeedback } from "@/composables/useRecommendationFeedback";
import { useRecommendationHistory } from "@/composables/useRecommendationHistory";
import {
    ALGORITHM_OPTIONS,
    formatAlgorithmLabel,
    formatGenerationModeLabel,
} from "@/utils/recommendation";

const router = useRouter();
const authStore = useAuthStore();

const algorithm = ref("cfkg");
const sampleMovies = ref([]);
const sampleLoading = ref(false);
const selectedRecommendation = ref(null);
const recommendationDrawerVisible = ref(false);

const {
    data: recommendData,
    loading: recommendLoading,
    error: recommendError,
    loadRecommendations,
} = useRecommendationFeed({
    algorithm: "cfkg",
    limit: 12,
});
const {
    preferenceStateMap,
    preferenceLoadingMap,
    hydratePreferenceState,
    togglePreference,
} = useRecommendationFeedback();
const { rememberMovies, buildRerollParams } = useRecommendationHistory();

const activeAlgorithm = computed(
    () =>
        ALGORITHM_OPTIONS.find((item) => item.value === algorithm.value) ||
        ALGORITHM_OPTIONS[0],
);
const recommendItems = computed(() => recommendData.value?.items || []);
const profileSummary = computed(() => recommendData.value?.profile_summary || null);
const profileHighlights = computed(
    () => recommendData.value?.profile_highlights || [],
);
const behaviorBadges = computed(() => {
    const summary = profileSummary.value;
    if (!summary) {
        return [];
    }
    return [
        summary.rating_count ? `${summary.rating_count} 次评分` : "",
        summary.likes ? `${summary.likes} 部喜欢` : "",
        summary.wants ? `${summary.wants} 部想看` : "",
        summary.positive_movie_count
            ? `${summary.positive_movie_count} 部正向兴趣电影`
            : "",
    ].filter(Boolean);
});
const statusDescription = computed(() => {
    if (!recommendData.value) {
        return "等待生成推荐结果";
    }
    if (recommendData.value.cold_start) {
        return "当前行为数据仍然偏少，系统会混合已有兴趣信号和冷启动兜底结果。";
    }
    return "系统已根据你的评分、喜欢、想看和知识图谱特征聚合出用户画像。";
});

const loadSampleMovies = async () => {
    sampleLoading.value = true;
    try {
        const { data } = await moviesApi.getTop(8);
        sampleMovies.value = data || [];
    } catch (err) {
        console.error("推荐页样本电影加载失败:", err);
        sampleMovies.value = [];
    } finally {
        sampleLoading.value = false;
    }
};

const applyRecommendationPayload = async (payload) => {
    const movieIds = (payload.items || [])
        .map((item) => item.movie?.mid)
        .filter(Boolean);
    await hydratePreferenceState(movieIds);
    rememberMovies(algorithm.value, movieIds);
};

const loadRecommendationPage = async ({ reroll = false } = {}) => {
    if (!authStore.isLoggedIn) {
        return;
    }
    try {
        const payload = await loadRecommendations({
            algorithm: algorithm.value,
            limit: 12,
            ...(reroll ? buildRerollParams(algorithm.value) : {}),
        });
        await applyRecommendationPayload(payload);
    } catch (err) {
        console.error("推荐页加载失败:", err);
    }
};

const handleRefresh = async () => {
    await loadRecommendationPage({ reroll: true });
};

const handlePreferenceToggle = async ({ mid, prefType }) => {
    try {
        await togglePreference(mid, prefType);
        await loadRecommendationPage();
    } catch (err) {
        console.error("推荐反馈失败:", err);
    }
};

const openRecommendationDetail = (item) => {
    selectedRecommendation.value = item;
    recommendationDrawerVisible.value = true;
};

onMounted(async () => {
    if (authStore.isLoggedIn) {
        await loadRecommendationPage();
        return;
    }
    await loadSampleMovies();
});

watch(
    () => authStore.isLoggedIn,
    async (loggedIn) => {
        if (loggedIn) {
            await loadRecommendationPage();
            return;
        }
        selectedRecommendation.value = null;
        recommendationDrawerVisible.value = false;
        await loadSampleMovies();
    },
);

watch(algorithm, async () => {
    if (!authStore.isLoggedIn) {
        return;
    }
    await loadRecommendationPage();
});
</script>

<template>
    <div class="recommend-view">
        <div class="container page-padding">
            <header class="page-hero card">
                <div class="hero-main">
                    <span class="hero-eyebrow">Recommendation Center</span>
                    <h1 class="page-title">智能推荐</h1>
                    <p class="hero-desc">
                        以 CFKG 联合建模为主链路，补充图协同过滤、图内容推荐和
                        Personalized PageRank 对比结果，直接展示“用户画像如何落到知识图谱上”。
                    </p>
                </div>
                <div class="hero-side">
                    <div class="hero-stat">
                        <strong>{{
                            authStore.isLoggedIn ? recommendItems.length : 4
                        }}</strong>
                        <span>{{
                            authStore.isLoggedIn ? "当前推荐结果" : "推荐算法"
                        }}</span>
                    </div>
                </div>
            </header>

            <section class="algorithm-panel card">
                <div class="panel-head">
                    <div>
                        <h2 class="section-title">算法切换</h2>
                        <p class="panel-desc">
                            单算法查看独立结果差异，默认使用 CFKG 主推荐链路。
                        </p>
                    </div>
                </div>

                <el-radio-group
                    v-model="algorithm"
                    size="large"
                    class="algorithm-switch"
                >
                    <el-radio-button
                        v-for="item in ALGORITHM_OPTIONS"
                        :key="item.value"
                        :value="item.value"
                    >
                        {{ item.label }}
                    </el-radio-button>
                </el-radio-group>

                <p class="algorithm-intro">
                    {{ activeAlgorithm.description }}
                </p>
            </section>

            <template v-if="authStore.isLoggedIn">
                <section class="status-panel card">
                    <div class="status-copy">
                        <span class="status-eyebrow">{{
                            formatAlgorithmLabel(algorithm)
                        }}</span>
                        <h2 class="status-title">
                            系统正在根据你的用户画像生成推荐
                        </h2>
                        <p class="panel-desc">{{ statusDescription }}</p>

                        <div
                            v-if="recommendData?.generation_mode"
                            class="status-line"
                        >
                            <el-tag size="small" effect="plain" round>
                                {{
                                    formatGenerationModeLabel(
                                        recommendData.generation_mode,
                                    )
                                }}
                            </el-tag>
                        </div>

                        <div v-if="behaviorBadges.length" class="chip-row">
                            <el-tag
                                v-for="badge in behaviorBadges"
                                :key="badge"
                                size="small"
                                effect="plain"
                                round
                            >
                                {{ badge }}
                            </el-tag>
                        </div>

                        <div v-if="profileHighlights.length" class="chip-row">
                            <el-tag
                                v-for="highlight in profileHighlights"
                                :key="`${highlight.type}-${highlight.label}`"
                                size="small"
                                round
                            >
                                {{ highlight.label }}
                            </el-tag>
                        </div>
                    </div>

                    <div class="status-actions">
                        <div class="status-count">
                            <strong>{{ recommendItems.length }}</strong>
                            <span>结果数</span>
                        </div>
                        <el-button
                            type="primary"
                            plain
                            @click="handleRefresh"
                        >
                            重新生成
                        </el-button>
                        <el-button @click="router.push('/profile')">
                            查看我的行为
                        </el-button>
                    </div>
                </section>

                <el-alert
                    v-if="recommendData?.cold_start"
                    class="panel-alert"
                    type="info"
                    show-icon
                    :closable="false"
                    title="当前仍处于冷启动阶段。继续补充喜欢、想看和评分后，推荐会更贴近你的真实兴趣。"
                />

                <el-alert
                    v-if="recommendError"
                    class="panel-alert"
                    type="warning"
                    show-icon
                    :closable="false"
                    :title="recommendError"
                />

                <section v-if="recommendItems.length" class="results-section">
                    <div
                        class="recommend-grid"
                        v-loading="recommendLoading"
                        element-loading-text="正在生成推荐..."
                    >
                        <RecommendationCard
                            v-for="item in recommendItems"
                            :key="item.movie.mid"
                            :item="item"
                            show-actions
                            :feedback-state="
                                preferenceStateMap[item.movie.mid] || {}
                            "
                            :feedback-loading="
                                preferenceLoadingMap[item.movie.mid] || false
                            "
                            @open="openRecommendationDetail"
                            @toggle-preference="handlePreferenceToggle($event)"
                        />
                    </div>
                </section>

                <section
                    v-else-if="!recommendLoading"
                    class="empty-panel card"
                >
                    <h2>当前没有可展示的推荐结果</h2>
                    <p>
                        先标记一些喜欢/想看或补充评分，再回来生成推荐。
                    </p>
                    <div class="empty-actions">
                        <el-button
                            type="primary"
                            @click="router.push('/movies/filter')"
                        >
                            去找电影
                        </el-button>
                        <el-button @click="router.push('/profile')">
                            查看我的行为
                        </el-button>
                    </div>
                </section>
            </template>

            <template v-else>
                <section class="guest-panel card">
                    <div class="guest-copy">
                        <span class="status-eyebrow">未登录</span>
                        <h2 class="status-title">登录后生成你的专属推荐</h2>
                        <p class="panel-desc">
                            推荐页会结合你的历史评分、喜欢与想看，聚合出用户画像并解释图谱证据链。
                        </p>
                        <div class="empty-actions">
                            <el-button
                                type="primary"
                                @click="
                                    router.push({
                                        name: 'login',
                                        query: { redirect: '/recommend' },
                                    })
                                "
                            >
                                登录开启推荐
                            </el-button>
                            <el-button @click="router.push('/movies/filter')">
                                先逛电影库
                            </el-button>
                        </div>
                    </div>
                </section>

                <section class="sample-section">
                    <div class="panel-head">
                        <div>
                            <h2 class="section-title">示例 / 热门电影</h2>
                            <p class="panel-desc">
                                未登录时展示通用样本，便于先了解页面结构和系统能力。
                            </p>
                        </div>
                    </div>
                    <MovieList :movies="sampleMovies" :loading="sampleLoading" />
                </section>
            </template>
        </div>

        <RecommendationDetailDrawer
            v-model="recommendationDrawerVisible"
            :item="selectedRecommendation"
            :algorithm="recommendData?.algorithm || algorithm"
        />
    </div>
</template>

<style scoped lang="scss">
.recommend-view {
    padding-top: var(--space-xl);
    padding-bottom: var(--space-2xl);
}

.page-padding {
    display: grid;
    gap: var(--space-lg);
}

.page-hero,
.algorithm-panel,
.status-panel,
.guest-panel,
.empty-panel {
    padding: var(--space-xl);
}

.page-hero {
    display: flex;
    justify-content: space-between;
    gap: var(--space-lg);
    background:
        radial-gradient(
            circle at top right,
            rgba(0, 181, 29, 0.14),
            transparent 42%
        ),
        var(--bg-card);
}

.hero-main {
    display: grid;
    gap: var(--space-sm);
}

.hero-eyebrow,
.status-eyebrow {
    color: var(--color-accent);
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.hero-desc,
.panel-desc {
    color: var(--text-secondary);
}

.hero-side {
    display: flex;
    align-items: center;
}

.hero-stat {
    display: grid;
    justify-items: end;

    strong {
        font-size: 2.3rem;
        color: var(--text-primary);
        line-height: 1;
    }

    span {
        color: var(--text-muted);
        font-size: 0.88rem;
    }
}

.panel-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
}

.algorithm-switch {
    margin-bottom: var(--space-sm);
    flex-wrap: wrap;
}

.algorithm-intro {
    color: var(--text-secondary);
}

.status-panel {
    display: flex;
    justify-content: space-between;
    gap: var(--space-lg);
    background:
        linear-gradient(
            140deg,
            rgba(0, 181, 29, 0.08),
            rgba(0, 181, 29, 0.02)
        ),
        var(--bg-card);
}

.status-copy {
    display: grid;
    gap: var(--space-sm);
}

.status-title {
    color: var(--text-primary);
    font-size: 1.3rem;
    font-weight: 700;
}

.status-line {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.status-actions {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-sm);
}

.status-count {
    display: grid;
    justify-items: end;

    strong {
        font-size: 1.9rem;
        line-height: 1;
        color: var(--text-primary);
    }

    span {
        color: var(--text-muted);
        font-size: 0.86rem;
    }
}

.panel-alert {
    margin-top: calc(var(--space-md) * -0.25);
}

.results-section {
    display: grid;
}

.recommend-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-lg);
}

.guest-copy {
    display: grid;
    gap: var(--space-sm);
}

.empty-panel {
    text-align: center;

    h2 {
        color: var(--text-primary);
        margin-bottom: var(--space-sm);
    }

    p {
        color: var(--text-secondary);
        margin-bottom: var(--space-md);
    }
}

.empty-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
}

@media (max-width: 1024px) {
    .recommend-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 768px) {
    .page-hero,
    .status-panel {
        flex-direction: column;
    }

    .status-actions,
    .status-count,
    .hero-stat {
        align-items: flex-start;
        justify-items: start;
    }

    .recommend-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--space-md);
    }

    .empty-actions {
        flex-direction: column;
    }
}
</style>
