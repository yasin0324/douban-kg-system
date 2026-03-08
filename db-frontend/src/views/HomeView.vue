<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import MovieList from "@/components/movie/MovieList.vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import { moviesApi } from "@/api/movies";
import { statsApi } from "@/api/stats";
import { useRecommendationFeed } from "@/composables/useRecommendations";
import { useAuthStore } from "@/stores/auth";
import { proxyImage } from "@/utils/image";
import { formatSourceAlgorithmLabel } from "@/utils/recommendation";

const router = useRouter();
const authStore = useAuthStore();

const topMovies = ref([]);
const overview = ref(null);
const genres = ref([]);
const loading = ref(true);
const searchQuery = ref("");
const showBackTop = ref(false);
const page = ref(1);
const pageSize = 24;
const loadingMore = ref(false);
const noMore = ref(false);
const selectedRecommendation = ref(null);
const recommendationDrawerVisible = ref(false);

const {
    data: recommendData,
    loading: recommendLoading,
    loadRecommendations,
} = useRecommendationFeed({
    algorithm: "cfkg",
    limit: 4,
});

const homeRecommendItems = computed(() =>
    (recommendData.value?.items || []).slice(0, 4).map((item) => ({
        ...item,
        overlay: item.source_algorithms?.length
            ? formatSourceAlgorithmLabel(item.source_algorithms[0])
            : "CFKG",
        summary: item.reasons?.[0] || "暂无推荐说明",
    })),
);

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
        await loadHomeRecommendations();
    }

    window.addEventListener("scroll", handleScroll);
});

watch(
    () => authStore.isLoggedIn,
    async (loggedIn) => {
        if (loggedIn) {
            await loadHomeRecommendations();
        }
    },
);

onUnmounted(() => {
    window.removeEventListener("scroll", handleScroll);
});

async function loadHomeRecommendations() {
    try {
        await loadRecommendations({ algorithm: "cfkg", limit: 4 });
    } catch (err) {
        console.error("首页推荐加载失败:", err);
    }
}

function openRecommendationDetail(item) {
    selectedRecommendation.value = item;
    recommendationDrawerVisible.value = true;
}

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
    page.value += 1;
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
        page.value -= 1;
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

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjIwIiBoZWlnaHQ9IjMzMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjIwIiBoZWlnaHQ9IjMzMCIgZmlsbD0iI2U1ZTdlYiIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjM2IiBmaWxsPSIjOTRhM2I4IiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";
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
                    <button
                        type="button"
                        class="section-link"
                        @click="router.push('/recommend')"
                    >
                        进入推荐页 →
                    </button>
                </div>

                <div
                    v-if="authStore.isLoggedIn && homeRecommendItems.length"
                    class="home-recommend-grid"
                    v-loading="recommendLoading"
                >
                    <article
                        v-for="item in homeRecommendItems"
                        :key="item.movie.mid"
                        class="home-recommend-card"
                        @click="openRecommendationDetail(item)"
                    >
                        <div class="home-poster-shell">
                            <img
                                :src="proxyImage(item.movie.cover) || defaultCover"
                                :alt="item.movie.title"
                                @error="(e) => (e.target.src = defaultCover)"
                            />
                            <span class="home-overlay">
                                {{ item.overlay }}
                            </span>
                        </div>

                        <div class="home-copy">
                            <h3>{{ item.movie.title }}</h3>
                            <span class="home-year">{{ item.movie.year || "—" }}</span>
                            <p>推荐理由：{{ item.summary }}</p>
                        </div>
                    </article>
                </div>

                <div v-else class="recommend-empty card">
                    <p>登录后查看真实的个性化推荐结果与知识路径解释。</p>
                </div>
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
            algorithm="cfkg"
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

.genre-section,
.recommend-section,
.top-section {
    margin-bottom: var(--space-xl);
}

.section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
}

.section-link {
    border: none;
    background: transparent;
    color: #3296d1;
    cursor: pointer;
    font-size: 1rem;
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

.home-recommend-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 24px;
}

.home-recommend-card {
    cursor: pointer;
    display: grid;
    gap: 12px;
}

.home-poster-shell {
    position: relative;
    padding: 14px;
    border-radius: 18px;
    background: #ffffff;
    border: 1px solid #d8dadd;
    box-shadow: 0 14px 26px rgba(15, 23, 42, 0.08);

    img {
        width: 100%;
        aspect-ratio: 2 / 3;
        object-fit: cover;
        border-radius: 10px;
        display: block;
    }
}

.home-overlay {
    position: absolute;
    top: 20px;
    right: 20px;
    padding: 0.34rem 0.7rem;
    border-radius: 999px;
    background: rgba(216, 227, 224, 0.95);
    color: #22323a;
    font-size: 0.78rem;
    font-weight: 600;
}

.home-copy {
    display: grid;
    gap: 6px;

    h3 {
        margin: 0;
        font-size: 1.15rem;
        font-family: "Iowan Old Style", "Times New Roman", serif;
    }

    p {
        margin: 0;
        color: #1f2937;
        line-height: 1.6;
    }
}

.home-year {
    color: #6b7280;
}

.recommend-empty {
    padding: 28px;
    color: var(--text-secondary);
}

.load-more-area {
    text-align: center;
    margin: var(--space-xl) 0;
}

.loading-indicator {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--text-secondary);
}

.no-more {
    color: var(--text-muted);
}

.back-top-btn {
    position: fixed;
    right: 24px;
    bottom: 32px;
    width: 44px;
    height: 44px;
    border: none;
    border-radius: 50%;
    background: var(--color-accent);
    color: #fff;
    font-size: 1.25rem;
    font-weight: 700;
    cursor: pointer;
    box-shadow: var(--shadow-lg);
}

.fade-btn-enter-active,
.fade-btn-leave-active {
    transition: opacity var(--transition-fast);
}

.fade-btn-enter-from,
.fade-btn-leave-to {
    opacity: 0;
}

@media (max-width: 1200px) {
    .home-recommend-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 768px) {
    .hero-title {
        font-size: 2rem;
    }

    .stats-overview {
        gap: var(--space-lg);
    }

    .section-header {
        align-items: flex-start;
        flex-direction: column;
    }

    .home-recommend-grid {
        grid-template-columns: 1fr;
    }
}
</style>
