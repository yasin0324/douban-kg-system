<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import MovieList from "@/components/movie/MovieList.vue";
import RecommendationCard from "@/components/recommend/RecommendationCard.vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import { moviesApi } from "@/api/movies";
import { statsApi } from "@/api/stats";
import { useAuthStore } from "@/stores/auth";
import { useRecommendationFeed } from "@/composables/useRecommendations";
import { useRecommendationFeedback } from "@/composables/useRecommendationFeedback";
import { useRecommendationHistory } from "@/composables/useRecommendationHistory";
import { formatGenerationModeLabel } from "@/utils/recommendation";

const router = useRouter();
const authStore = useAuthStore();

const topMovies = ref([]);
const overview = ref(null);
const genres = ref([]);
const loading = ref(true);
const searchQuery = ref("");

const page = ref(1);
const pageSize = 24;
const loadingMore = ref(false);
const noMore = ref(false);

const {
    data: recommendData,
    loading: recommendLoading,
    error: recommendError,
    loadRecommendations,
} = useRecommendationFeed({
    algorithm: "cfkg",
    limit: 6,
});
const {
    preferenceStateMap,
    preferenceLoadingMap,
    hydratePreferenceState,
    togglePreference,
} = useRecommendationFeedback();
const { rememberMovies, buildRerollParams } = useRecommendationHistory();
const recommendationDrawerVisible = ref(false);
const selectedRecommendation = ref(null);

const showBackTop = ref(false);

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
    ].filter(Boolean);
});
const guestSampleMovies = computed(() => topMovies.value.slice(0, 6));
const previewDescription = computed(() => {
    if (!recommendData.value) {
        return "系统正在聚合你的评分、喜欢与想看行为。";
    }
    if (recommendData.value.cold_start) {
        return "当前仍处于冷启动阶段，结果中会混合少量兜底推荐。";
    }
    return "系统已根据你的行为构建用户画像，并结合知识图谱生成结果。";
});

const applyRecommendationPayload = async (payload) => {
    const movieIds = (payload.items || [])
        .map((item) => item.movie?.mid)
        .filter(Boolean);
    await hydratePreferenceState(movieIds);
    rememberMovies("cfkg", movieIds);
};

const loadRecommendationPreview = async ({ reroll = false } = {}) => {
    if (!authStore.isLoggedIn) {
        return;
    }
    try {
        const payload = await loadRecommendations({
            algorithm: "cfkg",
            limit: 6,
            ...(reroll ? buildRerollParams("cfkg") : {}),
        });
        await applyRecommendationPayload(payload);
    } catch (err) {
        console.error("首页推荐加载失败:", err);
    }
};

const openRecommendationDetail = (item) => {
    selectedRecommendation.value = item;
    recommendationDrawerVisible.value = true;
};

const handlePreviewPreferenceToggle = async ({ mid, prefType }) => {
    try {
        await togglePreference(mid, prefType);
        await loadRecommendationPreview();
    } catch (err) {
        console.error("更新推荐偏好失败:", err);
    }
};

const handleRefreshPreview = async () => {
    await loadRecommendationPreview({ reroll: true });
};

onMounted(async () => {
    loading.value = true;
    try {
        const [moviesRes, overviewRes, genresRes] = await Promise.all([
            moviesApi.filter({
                page: 1,
                size: pageSize,
                sort_by: "weighted",
            }),
            statsApi.getOverview(),
            moviesApi.getGenres(),
        ]);
        topMovies.value = moviesRes.data.items;
        if (moviesRes.data.items.length < pageSize) {
            noMore.value = true;
        }
        overview.value = overviewRes.data;
        genres.value = genresRes.data;
    } catch (err) {
        console.error("首页数据加载失败:", err);
    } finally {
        loading.value = false;
    }

    if (authStore.isLoggedIn) {
        await loadRecommendationPreview();
    }

    window.addEventListener("scroll", handleScroll);
});

watch(
    () => authStore.isLoggedIn,
    async (loggedIn) => {
        if (loggedIn) {
            await loadRecommendationPreview();
            return;
        }
        selectedRecommendation.value = null;
        recommendationDrawerVisible.value = false;
    },
);

onUnmounted(() => {
    window.removeEventListener("scroll", handleScroll);
});

const handleScroll = () => {
    showBackTop.value = window.scrollY > 600;

    const scrollBottom =
        document.documentElement.scrollHeight -
        window.scrollY -
        window.innerHeight;
    if (scrollBottom < 300 && !loadingMore.value && !noMore.value) {
        loadMore();
    }
};

const loadMore = async () => {
    loadingMore.value = true;
    page.value++;
    try {
        const { data } = await moviesApi.filter({
            page: page.value,
            size: pageSize,
            sort_by: "weighted",
        });
        topMovies.value.push(...data.items);
        if (data.items.length < pageSize) {
            noMore.value = true;
        }
    } catch (err) {
        console.error("加载更多失败:", err);
        page.value--;
    } finally {
        loadingMore.value = false;
    }
};

const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
};

const handleSearch = () => {
    const q = searchQuery.value.trim();
    if (q) {
        router.push({ path: "/search", query: { q } });
    }
};

const filterByGenre = (genre) => {
    router.push({ path: "/movies/filter", query: { genre } });
};

const formatNum = (num) => {
    if (!num) return "0";
    if (num >= 10000) return `${(num / 10000).toFixed(1)}万`;
    return num.toLocaleString();
};
</script>

<template>
    <div class="home-view">
        <section class="hero-section">
            <div class="container">
                <h1 class="hero-title">
                    <span class="hero-icon">🎬</span>
                    豆瓣电影知识图谱
                </h1>

                <div class="hero-search">
                    <el-input
                        v-model="searchQuery"
                        placeholder="搜索电影或影人..."
                        size="large"
                        clearable
                        @keyup.enter="handleSearch"
                    >
                        <template #append>
                            <el-button @click="handleSearch">搜索</el-button>
                        </template>
                    </el-input>
                </div>

                <div class="stats-overview" v-if="overview">
                    <div class="stat-item">
                        <span class="stat-number">{{
                            formatNum(overview.movie_count)
                        }}</span>
                        <span class="stat-label">电影</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{{
                            formatNum(overview.person_count)
                        }}</span>
                        <span class="stat-label">影人</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{{
                            formatNum(overview.genre_count)
                        }}</span>
                        <span class="stat-label">类型</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number">{{
                            formatNum(overview.relationship_count)
                        }}</span>
                        <span class="stat-label">关系</span>
                    </div>
                </div>
            </div>
        </section>

        <div class="container">
            <section class="genre-section" v-if="genres.length">
                <h2 class="section-title">🏷️ 类型探索</h2>
                <div class="genre-tags">
                    <el-tag
                        v-for="genre in genres"
                        :key="genre"
                        class="genre-tag"
                        effect="plain"
                        round
                        @click="filterByGenre(genre)"
                    >
                        {{ genre }}
                    </el-tag>
                </div>
            </section>

            <section class="recommend-section">
                <div class="section-header">
                    <h2 class="section-title">🎯 为你推荐</h2>
                    <el-button
                        text
                        type="primary"
                        @click="router.push('/recommend')"
                    >
                        查看更多 →
                    </el-button>
                </div>

                <template v-if="authStore.isLoggedIn">
                    <div class="recommend-state card">
                        <div class="state-copy">
                            <span class="state-eyebrow">CFKG 推荐预览</span>
                            <h3 class="state-title">
                                基于你的用户画像实时生成
                            </h3>
                            <p class="state-desc">
                                {{ previewDescription }}
                            </p>

                            <div
                                v-if="recommendData?.generation_mode"
                                class="chip-row"
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

                        <div class="state-side">
                            <strong class="state-count">
                                {{ recommendItems.length }}
                            </strong>
                            <span class="state-count-label">当前推荐数</span>
                            <el-button
                                type="primary"
                                plain
                                @click="handleRefreshPreview"
                            >
                                重新生成
                            </el-button>
                        </div>
                    </div>

                    <el-alert
                        v-if="recommendData?.cold_start"
                        class="recommend-alert"
                        type="info"
                        show-icon
                        :closable="false"
                        title="你的历史行为还比较少，当前结果带有冷启动兜底。完善喜欢、想看和评分后，推荐会更稳定。"
                    />

                    <el-alert
                        v-if="recommendError"
                        class="recommend-alert"
                        type="warning"
                        show-icon
                        :closable="false"
                        :title="recommendError"
                    />

                    <div
                        v-if="recommendItems.length"
                        class="recommend-grid"
                        v-loading="recommendLoading"
                    >
                        <RecommendationCard
                            v-for="item in recommendItems"
                            :key="item.movie.mid"
                            :item="item"
                            compact
                            show-actions
                            :feedback-state="
                                preferenceStateMap[item.movie.mid] || {}
                            "
                            :feedback-loading="
                                preferenceLoadingMap[item.movie.mid] || false
                            "
                            @open="openRecommendationDetail"
                            @toggle-preference="
                                handlePreviewPreferenceToggle($event)
                            "
                        />
                    </div>

                    <div
                        v-else-if="!recommendLoading"
                        class="recommend-empty card"
                    >
                        <h3>还没有形成稳定的个性化结果</h3>
                        <p>
                            先去电影详情页标记“喜欢 / 想看”或打分，系统就能更准确地生成推荐。
                        </p>
                        <div class="empty-actions">
                            <el-button
                                type="primary"
                                @click="router.push('/movies/filter')"
                            >
                                去找电影
                            </el-button>
                            <el-button @click="router.push('/recommend')">
                                打开推荐中心
                            </el-button>
                        </div>
                    </div>
                </template>

                <template v-else>
                    <div class="recommend-guest">
                        <div class="guest-callout card">
                            <span class="state-eyebrow">个性化推荐未开启</span>
                            <h3 class="state-title">登录后生成你的专属推荐</h3>
                            <p class="state-desc">
                                推荐系统会结合你的评分、喜欢、想看以及知识图谱关联来生成结果。
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
                                <el-button @click="router.push('/recommend')">
                                    先看看推荐页
                                </el-button>
                            </div>
                        </div>

                        <div class="guest-samples">
                            <div class="guest-samples-head">
                                <h3>示例 / 热门电影</h3>
                                <p>未登录时展示热门样本，不冒充个性化推荐。</p>
                            </div>
                            <MovieList
                                :movies="guestSampleMovies"
                                :loading="loading"
                            />
                        </div>
                    </div>
                </template>
            </section>

            <section class="top-section">
                <div class="section-header">
                    <h2 class="section-title">⭐ 高分电影</h2>
                    <el-button
                        text
                        type="primary"
                        @click="router.push('/movies/filter')"
                    >
                        查看更多 →
                    </el-button>
                </div>
                <MovieList :movies="topMovies" :loading="loading" />

                <div class="load-more-area">
                    <div v-if="loadingMore" class="loading-indicator">
                        <el-icon class="is-loading"><span>⏳</span></el-icon>
                        <span>加载中...</span>
                    </div>
                    <div
                        v-else-if="noMore && topMovies.length > 0"
                        class="no-more"
                    >
                        — 已经到底了 —
                    </div>
                </div>
            </section>
        </div>

        <transition name="fade-btn">
            <button
                v-show="showBackTop"
                class="back-top-btn"
                @click="scrollToTop"
                title="回到顶部"
            >
                ↑
            </button>
        </transition>

        <RecommendationDetailDrawer
            v-model="recommendationDrawerVisible"
            :item="selectedRecommendation"
            :algorithm="recommendData?.algorithm || 'cfkg'"
        />
    </div>
</template>

<style scoped lang="scss">
.hero-section {
    text-align: center;
    padding: var(--space-2xl) 0;
    background: linear-gradient(
        180deg,
        rgba(0, 181, 29, 0.05) 0%,
        transparent 100%
    );
    border-bottom: 1px solid var(--border-color);
    margin-bottom: var(--space-xl);
}

.hero-title {
    font-size: 2.5rem;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);

    .hero-icon {
        font-size: 2.2rem;
    }
}

.hero-search {
    max-width: 560px;
    margin: 0 auto var(--space-xl);
}

.stats-overview {
    display: flex;
    justify-content: center;
    gap: var(--space-2xl);
    flex-wrap: wrap;
}

.stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
}

.stat-number {
    font-size: 2rem;
    font-weight: 700;
    color: var(--color-accent);
    line-height: 1.2;
}

.stat-label {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 2px;
}

.genre-section {
    margin-bottom: var(--space-xl);
}

.genre-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
}

.genre-tag {
    cursor: pointer;
    transition: all var(--transition-fast);
    background: var(--bg-card) !important;
    border-color: var(--border-color) !important;
    color: var(--text-secondary) !important;

    &:hover {
        border-color: var(--color-accent) !important;
        color: var(--color-accent) !important;
        background: var(--color-accent-bg) !important;
    }
}

.recommend-section {
    margin-bottom: var(--space-xl);
}

.recommend-state,
.guest-callout,
.recommend-empty {
    padding: var(--space-xl);
}

.recommend-state {
    display: flex;
    justify-content: space-between;
    gap: var(--space-lg);
    margin-bottom: var(--space-md);
    background:
        linear-gradient(
            140deg,
            rgba(0, 181, 29, 0.08),
            rgba(0, 181, 29, 0.02)
        ),
        var(--bg-card);
}

.state-copy {
    display: grid;
    gap: var(--space-sm);
}

.state-eyebrow {
    color: var(--color-accent);
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.state-title {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--text-primary);
}

.state-desc {
    color: var(--text-secondary);
}

.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.state-side {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: space-between;
    min-width: 140px;
}

.state-count {
    font-size: 2rem;
    line-height: 1;
    color: var(--text-primary);
}

.state-count-label {
    color: var(--text-muted);
    font-size: 0.86rem;
}

.recommend-alert {
    margin-bottom: var(--space-md);
}

.recommend-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-lg);
}

.recommend-empty {
    text-align: center;

    h3 {
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
    justify-content: center;
}

.recommend-guest {
    display: grid;
    gap: var(--space-lg);
}

.guest-samples {
    padding-top: var(--space-sm);
}

.guest-samples-head {
    margin-bottom: var(--space-md);

    h3 {
        color: var(--text-primary);
        font-size: 1.05rem;
        margin-bottom: 4px;
    }

    p {
        color: var(--text-secondary);
        font-size: 0.88rem;
    }
}

.top-section {
    margin-bottom: var(--space-2xl);
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-sm);
    margin-bottom: var(--space-md);
}

.load-more-area {
    text-align: center;
    padding: var(--space-xl) 0;
}

.loading-indicator {
    display: inline-flex;
    align-items: center;
    gap: var(--space-sm);
    color: var(--color-accent);
    font-size: 0.9rem;
}

.no-more {
    color: var(--text-muted);
    font-size: 0.85rem;
}

.back-top-btn {
    position: fixed;
    bottom: 40px;
    right: 40px;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
    box-shadow: var(--shadow-sm);
}

@media (max-width: 1024px) {
    .recommend-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 768px) {
    .stats-overview {
        gap: var(--space-lg);
    }

    .recommend-state {
        flex-direction: column;
    }

    .state-side {
        align-items: flex-start;
    }

    .recommend-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: var(--space-md);
    }

    .empty-actions {
        flex-direction: column;
    }

    .back-top-btn {
        right: 20px;
        bottom: 20px;
    }
}
</style>
