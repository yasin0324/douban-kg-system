<script setup>
import { ref, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import MovieList from "@/components/movie/MovieList.vue";
import { moviesApi } from "@/api/movies";
import { statsApi } from "@/api/stats";

const router = useRouter();

// 数据
const topMovies = ref([]);
const overview = ref(null);
const genres = ref([]);
const loading = ref(true);
const searchQuery = ref("");

// 无限滚动
const page = ref(1);
const pageSize = 24;
const loadingMore = ref(false);
const noMore = ref(false);

// 回到顶部
const showBackTop = ref(false);

// 加载数据
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

    // 监听滚动
    window.addEventListener("scroll", handleScroll);
});

onUnmounted(() => {
    window.removeEventListener("scroll", handleScroll);
});

// 滚动处理：无限加载 + 回到顶部按钮
const handleScroll = () => {
    // 回到顶部按钮：滚动超过 600px 时显示
    showBackTop.value = window.scrollY > 600;

    // 无限加载：距离底部 300px 时触发
    const scrollBottom =
        document.documentElement.scrollHeight -
        window.scrollY -
        window.innerHeight;
    if (scrollBottom < 300 && !loadingMore.value && !noMore.value) {
        loadMore();
    }
};

// 加载更多
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

// 回到顶部
const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
};

// 搜索
const handleSearch = () => {
    const q = searchQuery.value.trim();
    if (q) {
        router.push({ path: "/search", query: { q } });
    }
};

// 跳转筛选页
const filterByGenre = (genre) => {
    router.push({ path: "/movies/filter", query: { genre } });
};

// 格式化数字
const formatNum = (num) => {
    if (!num) return "0";
    if (num >= 10000) return (num / 10000).toFixed(1) + "万";
    return num.toLocaleString();
};
</script>

<template>
    <div class="home-view">
        <!-- Hero 区域 -->
        <section class="hero-section">
            <div class="container">
                <h1 class="hero-title">
                    <span class="hero-icon">🎬</span>
                    豆瓣电影知识图谱
                </h1>

                <!-- 搜索框 -->
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

                <!-- 统计概览 -->
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
            <!-- 类型标签云 -->
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

            <!-- 高分电影 -->
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

                <!-- 加载更多状态 -->
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

        <!-- 回到顶部按钮 -->
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

.top-section {
    margin-bottom: var(--space-2xl);
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-md);
}

/* 加载更多 */
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

/* 回到顶部按钮 */
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
    font-size: 1.2rem;
    font-weight: 700;
    cursor: pointer;
    box-shadow: var(--shadow-md);
    z-index: 999;
    transition: all var(--transition-fast);
    display: flex;
    align-items: center;
    justify-content: center;

    &:hover {
        background: var(--color-accent);
        color: #fff;
        border-color: var(--color-accent);
        transform: translateY(-3px);
        box-shadow: var(--shadow-lg);
    }
}

.fade-btn-enter-active,
.fade-btn-leave-active {
    transition: all 0.3s ease;
}

.fade-btn-enter-from,
.fade-btn-leave-to {
    opacity: 0;
    transform: translateY(20px);
}

@media (max-width: 768px) {
    .hero-title {
        font-size: 1.8rem;
    }

    .stats-overview {
        gap: var(--space-lg);
    }

    .stat-number {
        font-size: 1.5rem;
    }

    .back-top-btn {
        bottom: 24px;
        right: 24px;
    }
}
</style>
