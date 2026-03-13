<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import { useRecommendationHistory } from "@/composables/useRecommendationHistory";
import { useRecommendationFeed } from "@/composables/useRecommendations";
import { useAuthStore } from "@/stores/auth";
import { proxyImage } from "@/utils/image";
import api from "@/api/index";
import { moviesApi } from "@/api/movies";
import { usersApi } from "@/api/users";

const authStore = useAuthStore();

const algorithmOptions = [
    { value: "kg_path", label: "KG 路径推荐", type: "KG" },
    { value: "kg_embed", label: "KG 嵌入推荐", type: "KG" },
    { value: "content", label: "基于内容推荐", type: "基线" },
    { value: "item_cf", label: "协同过滤推荐", type: "基线" },
];
const RECOMMEND_BATCH_SIZE = 12;
const SCROLL_LOAD_THRESHOLD = 300;

const selectedAlgorithm = ref("kg_path");
const { rememberMovies, buildRerollParams } = useRecommendationHistory();

const {
    loading: recommendLoading,
    error: recommendError,
    loadRecommendations,
} = useRecommendationFeed({
    algorithm: "kg_path",
    limit: RECOMMEND_BATCH_SIZE,
});

const selectedRecommendation = ref(null);
const recommendationDrawerVisible = ref(false);
const evalData = ref(null);
const evalLoading = ref(false);
const activeTab = ref("recommend");
const recommendItems = ref([]);
const recommendLoadingMore = ref(false);
const recommendNoMore = ref(false);

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgZmlsbD0iIzBmMTcyYSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjQyIiBmaWxsPSIjMzM0MTU1IiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

const displayItems = computed(() => recommendItems.value);

const currentAlgoLabel = computed(() => {
    const opt = algorithmOptions.find(
        (o) => o.value === selectedAlgorithm.value,
    );
    return opt ? opt.label : selectedAlgorithm.value;
});

// ────────────── 冷启动状态 ──────────────
const COLD_START_THRESHOLD = 3;
const coldStartMode = ref(false);
const effectiveSignalCount = ref(0);
const coldStartSkipped = ref(false);
const topMovies = ref([]);
const topMoviesLoading = ref(false);
const interactedMids = ref(new Set()); // 本次会话中已交互的 mid（用于 UI 进度）

// 分页 + 无限滚动
const topPage = ref(1);
const topPageSize = 24;
const loadingMore = ref(false);
const noMore = ref(false);
const showBackTop = ref(false);

// 评分弹层状态
const ratingDialogVisible = ref(false);
const ratingDialogMovie = ref(null);
const ratingDialogValue = ref(0);
const ratingSubmitting = ref(false);

// 每张卡片上的 action 按钮 loading 状态
const actionLoading = ref({});

onMounted(async () => {
    await loadPage();
    window.addEventListener("scroll", handleScroll);
});

onUnmounted(() => {
    window.removeEventListener("scroll", handleScroll);
});

function resetColdStartState() {
    coldStartMode.value = false;
    coldStartSkipped.value = false;
    effectiveSignalCount.value = 0;
    interactedMids.value = new Set();
    recommendItems.value = [];
    recommendLoadingMore.value = false;
    recommendNoMore.value = false;
    actionLoading.value = {};
    ratingDialogVisible.value = false;
    ratingDialogMovie.value = null;
    ratingDialogValue.value = 0;
    ratingSubmitting.value = false;
}

async function syncColdStartInteractions() {
    try {
        // 冷启动用户的唯一交互电影数 < 3，这里一次取够即可还原完整集合。
        const [ratingsRes, prefsRes] = await Promise.all([
            usersApi.getRatings({ page: 1, size: COLD_START_THRESHOLD }),
            usersApi.getPreferences({ page: 1, size: COLD_START_THRESHOLD }),
        ]);
        const mids = new Set();

        for (const item of ratingsRes.data?.items || []) {
            if (item?.mid) {
                mids.add(String(item.mid));
            }
        }
        for (const item of prefsRes.data?.items || []) {
            if (item?.mid) {
                mids.add(String(item.mid));
            }
        }

        interactedMids.value = mids;
        effectiveSignalCount.value = mids.size;
    } catch (err) {
        console.error("冷启动交互同步失败:", err);
        interactedMids.value = new Set();
    }
}

watch(
    () => authStore.isLoggedIn,
    async (loggedIn) => {
        if (loggedIn) {
            await loadPage();
            return;
        }
        selectedRecommendation.value = null;
        recommendationDrawerVisible.value = false;
        resetColdStartState();
    },
);

async function loadPage() {
    if (!authStore.isLoggedIn) return;
    resetColdStartState();

    try {
        // 1. 先查行为汇总
        const { data } = await api.get("/users/activity-summary");
        effectiveSignalCount.value = data.effective_signal_count;

        if (data.meets_personalization_threshold) {
            // 有足够信号 → 正常推荐
            coldStartMode.value = false;
            await loadWithAlgorithm(selectedAlgorithm.value);
        } else {
            // 冷启动模式
            coldStartMode.value = true;
            await syncColdStartInteractions();
            await loadTopMovies();
        }
    } catch (err) {
        console.error("页面初始化失败:", err);
        // 降级：尝试加载热门
        coldStartMode.value = true;
        await loadTopMovies();
    }
}

async function loadTopMovies() {
    topMoviesLoading.value = true;
    topPage.value = 1;
    noMore.value = false;
    try {
        const { data } = await moviesApi.filter({
            page: 1,
            size: topPageSize,
            sort_by: "weighted",
        });
        topMovies.value = data.items || [];
        if ((data.items || []).length < topPageSize) {
            noMore.value = true;
        }
    } catch (err) {
        console.error("热门电影加载失败:", err);
        topMovies.value = [];
    } finally {
        topMoviesLoading.value = false;
    }
}

async function loadMoreTopMovies() {
    if (loadingMore.value || noMore.value) return;
    loadingMore.value = true;
    topPage.value += 1;
    try {
        const { data } = await moviesApi.filter({
            page: topPage.value,
            size: topPageSize,
            sort_by: "weighted",
        });
        const items = data.items || [];
        topMovies.value.push(...items);
        if (items.length < topPageSize) {
            noMore.value = true;
        }
    } catch (err) {
        console.error("加载更多失败:", err);
        topPage.value -= 1;
    } finally {
        loadingMore.value = false;
    }
}

async function loadWithAlgorithm(algo) {
    return loadRecommendBatch(algo, { replace: true });
}

function getRecommendationItemMid(item) {
    return String(item?.movie?.mid || item?.mid || "");
}

function replaceRecommendationItems(items = []) {
    const nextItems = [];
    const seen = new Set();
    items.forEach((item) => {
        const mid = getRecommendationItemMid(item);
        if (!mid || seen.has(mid)) {
            return;
        }
        seen.add(mid);
        nextItems.push(item);
    });
    recommendItems.value = nextItems;
}

function appendRecommendationItems(items = []) {
    const seen = new Set(
        recommendItems.value.map((item) => getRecommendationItemMid(item)),
    );
    const merged = [...recommendItems.value];
    items.forEach((item) => {
        const mid = getRecommendationItemMid(item);
        if (!mid || seen.has(mid)) {
            return;
        }
        seen.add(mid);
        merged.push(item);
    });
    recommendItems.value = merged;
}

function getDisplayedRecommendationIds() {
    return recommendItems.value
        .map((item) => getRecommendationItemMid(item))
        .filter(Boolean);
}

async function loadRecommendBatch(
    algo,
    { replace = false, reroll = false } = {},
) {
    try {
        const params = {
            algorithm: algo,
            limit: RECOMMEND_BATCH_SIZE,
        };
        if (reroll) {
            Object.assign(params, buildRerollParams(algo));
        } else if (!replace) {
            const excludeMovieIds = getDisplayedRecommendationIds();
            if (!excludeMovieIds.length) {
                recommendNoMore.value = true;
                return null;
            }
            params.exclude_movie_ids = excludeMovieIds;
        }

        const payload = await loadRecommendations(params, {
            silentLoading: !replace,
        });
        const items = payload?.items || [];
        const movieIds = items
            .map((item) => getRecommendationItemMid(item))
            .filter(Boolean);

        if (replace) {
            if (items.length || !recommendItems.value.length || !reroll) {
                replaceRecommendationItems(items);
            }
        } else {
            appendRecommendationItems(items);
        }

        rememberMovies(algo, movieIds);
        recommendNoMore.value = items.length < RECOMMEND_BATCH_SIZE;

        if (!payload?.items?.length && !topMovies.value.length) {
            await loadTopMovies();
        }
        return payload;
    } catch (err) {
        console.error("推荐页加载失败:", err);
        // 个性化推荐失败 → 回退到热门保底
        if (!topMovies.value.length) {
            await loadTopMovies();
        }
        return null;
    }
}

async function handleReroll() {
    if (recommendLoading.value || recommendLoadingMore.value) return;
    recommendNoMore.value = false;
    await loadRecommendBatch(selectedAlgorithm.value, {
        replace: true,
        reroll: true,
    });
}

async function loadMoreRecommendations() {
    if (
        recommendLoading.value ||
        recommendLoadingMore.value ||
        recommendNoMore.value
    ) {
        return;
    }
    recommendLoadingMore.value = true;
    try {
        await loadRecommendBatch(selectedAlgorithm.value, { replace: false });
    } finally {
        recommendLoadingMore.value = false;
    }
}

// ────────────── 滚动 ──────────────
const handleScroll = () => {
    showBackTop.value = window.scrollY > 600;
    if (activeTab.value !== "recommend") {
        return;
    }

    const scrollBottom =
        document.documentElement.scrollHeight -
        window.scrollY -
        window.innerHeight;
    if (scrollBottom < SCROLL_LOAD_THRESHOLD) {
        // 冷启动 / 跳过 / 保底：分页加载更多热门
        if (coldStartMode.value || showFallbackGrid.value) {
            loadMoreTopMovies();
        } else {
            loadMoreRecommendations();
        }
    }
};

const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
};

async function onAlgorithmChange(algo) {
    selectedAlgorithm.value = algo;
    recommendNoMore.value = false;
    await loadWithAlgorithm(algo);
}

async function loadEvaluation() {
    evalLoading.value = true;
    try {
        const { default: api } = await import("@/api/index");
        const response = await api.get("/recommend/evaluate");
        evalData.value = response.data;
    } catch (err) {
        console.error("评估报告加载失败:", err);
    } finally {
        evalLoading.value = false;
    }
}

function openRecommendationDetail(item) {
    selectedRecommendation.value = item;
    recommendationDrawerVisible.value = true;
}

// ────────────── 冷启动交互 ──────────────

function getMovieMid(movie) {
    return String(movie.mid || movie.douban_id);
}

function getMovieTitle(movie) {
    return movie.title || movie.name || "未知电影";
}

function getMovieRating(movie) {
    const r = movie.rating ?? movie.douban_score;
    return r ? Number(r) : null;
}

function getMovieCover(movie) {
    return proxyImage(movie.cover) || defaultCover;
}

async function handleLike(movie) {
    const mid = getMovieMid(movie);
    const key = `like_${mid}`;
    if (actionLoading.value[key]) return;
    actionLoading.value[key] = true;
    try {
        await api.post("/users/preferences", { mid, pref_type: "like" });
        recordSignal(mid);
    } catch (err) {
        console.error("喜欢操作失败:", err);
    } finally {
        actionLoading.value[key] = false;
    }
}

async function handleWantToWatch(movie) {
    const mid = getMovieMid(movie);
    const key = `want_${mid}`;
    if (actionLoading.value[key]) return;
    actionLoading.value[key] = true;
    try {
        await api.post("/users/preferences", {
            mid,
            pref_type: "want_to_watch",
        });
        recordSignal(mid);
    } catch (err) {
        console.error("想看操作失败:", err);
    } finally {
        actionLoading.value[key] = false;
    }
}

function openRatingDialog(movie) {
    ratingDialogMovie.value = movie;
    ratingDialogValue.value = 0;
    ratingDialogVisible.value = true;
}

async function submitRating() {
    if (!ratingDialogMovie.value || ratingDialogValue.value <= 0) return;
    const mid = getMovieMid(ratingDialogMovie.value);
    ratingSubmitting.value = true;
    try {
        await api.post("/users/ratings", {
            mid,
            rating: ratingDialogValue.value,
        });
        ratingDialogVisible.value = false;
        recordSignal(mid);
    } catch (err) {
        console.error("评分失败:", err);
    } finally {
        ratingSubmitting.value = false;
    }
}

function recordSignal(mid) {
    if (!interactedMids.value.has(mid)) {
        interactedMids.value.add(mid);
        effectiveSignalCount.value++;
    }
    // 达到门槛 → 自动切换到个性化推荐
    if (effectiveSignalCount.value >= COLD_START_THRESHOLD) {
        switchToPersonalized();
    }
}

async function switchToPersonalized() {
    coldStartMode.value = false;
    await loadWithAlgorithm(selectedAlgorithm.value);

    // 若个性化推荐也为空 → 保留热门保底
    if (!displayItems.value.length && !recommendLoading.value) {
        if (!topMovies.value.length) await loadTopMovies();
    }
}

function skipColdStart() {
    coldStartSkipped.value = true;
}

const showFallbackGrid = computed(
    () =>
        !coldStartMode.value &&
        !recommendLoading.value &&
        !displayItems.value.length &&
        topMovies.value.length > 0,
);

const progressPercent = computed(() =>
    Math.min((effectiveSignalCount.value / COLD_START_THRESHOLD) * 100, 100),
);

const isMovieInteracted = (movie) =>
    interactedMids.value.has(getMovieMid(movie));
</script>

<template>
    <div class="insights-view">
        <div class="insights-shell">
            <header class="page-header">
                <h1 class="page-title">🎯 个性化推荐</h1>
            </header>

            <template v-if="authStore.isLoggedIn">
                <!-- 标签页切换 -->
                <div class="tab-bar">
                    <button
                        :class="[
                            'tab-btn',
                            { active: activeTab === 'recommend' },
                        ]"
                        @click="activeTab = 'recommend'"
                    >
                        推荐结果
                    </button>
                    <button
                        :class="[
                            'tab-btn',
                            { active: activeTab === 'evaluate' },
                        ]"
                        @click="
                            activeTab = 'evaluate';
                            loadEvaluation();
                        "
                    >
                        算法评估对比
                    </button>
                </div>

                <!-- 推荐结果标签页 -->
                <template v-if="activeTab === 'recommend'">
                    <!-- ========== 冷启动模式 ========== -->
                    <template v-if="coldStartMode && !coldStartSkipped">
                        <!-- 引导区 -->
                        <section class="cold-start-hero">
                            <div class="hero-icon">🎬</div>
                            <h2 class="hero-title">你喜欢哪些电影？</h2>
                            <p class="hero-desc">
                                任选
                                <strong>{{ COLD_START_THRESHOLD }}</strong>
                                部你感兴趣的电影即可生成个性化推荐
                            </p>
                            <div class="progress-bar-wrapper">
                                <div class="progress-bar">
                                    <div
                                        class="progress-fill"
                                        :style="{
                                            width: progressPercent + '%',
                                        }"
                                    />
                                </div>
                                <span class="progress-text">
                                    {{ effectiveSignalCount }} /
                                    {{ COLD_START_THRESHOLD }}
                                </span>
                            </div>
                            <button class="skip-btn" @click="skipColdStart">
                                暂时跳过，浏览热门
                            </button>
                        </section>

                        <!-- 种子电影网格 -->
                        <section
                            class="evidence-panel"
                            v-loading="topMoviesLoading"
                        >
                            <h2 class="panel-label">高分热门电影</h2>
                            <div class="movie-grid">
                                <article
                                    v-for="movie in topMovies"
                                    :key="getMovieMid(movie)"
                                    :class="[
                                        'movie-card',
                                        'seed-card',
                                        {
                                            interacted:
                                                isMovieInteracted(movie),
                                        },
                                    ]"
                                >
                                    <div class="poster-frame">
                                        <img
                                            :src="getMovieCover(movie)"
                                            :alt="getMovieTitle(movie)"
                                            @error="
                                                (e) =>
                                                    (e.target.src =
                                                        defaultCover)
                                            "
                                        />
                                        <div
                                            class="interacted-badge"
                                            v-if="isMovieInteracted(movie)"
                                        >
                                            ✓
                                        </div>
                                    </div>
                                    <div class="movie-info">
                                        <h3 class="movie-title">
                                            {{ getMovieTitle(movie) }}
                                        </h3>
                                        <div class="movie-meta">
                                            <span
                                                v-if="getMovieRating(movie)"
                                                class="rating"
                                            >
                                                ⭐
                                                {{
                                                    getMovieRating(
                                                        movie,
                                                    ).toFixed(1)
                                                }}
                                            </span>
                                            <span
                                                v-if="movie.year"
                                                class="year"
                                            >
                                                {{ movie.year }}
                                            </span>
                                        </div>
                                        <!-- 操作按钮 -->
                                        <div class="action-buttons">
                                            <button
                                                class="action-btn like-btn"
                                                :disabled="
                                                    isMovieInteracted(movie)
                                                "
                                                @click.stop="handleLike(movie)"
                                            >
                                                ❤️ 喜欢
                                            </button>
                                            <button
                                                class="action-btn want-btn"
                                                :disabled="
                                                    isMovieInteracted(movie)
                                                "
                                                @click.stop="
                                                    handleWantToWatch(movie)
                                                "
                                            >
                                                👀 想看
                                            </button>
                                            <button
                                                class="action-btn rate-btn"
                                                :disabled="
                                                    isMovieInteracted(movie)
                                                "
                                                @click.stop="
                                                    openRatingDialog(movie)
                                                "
                                            >
                                                ⭐ 评分
                                            </button>
                                        </div>
                                    </div>
                                </article>
                            </div>
                        </section>
                    </template>

                    <!-- ========== 跳过冷启动 → 热门保底 ========== -->
                    <template v-else-if="coldStartMode && coldStartSkipped">
                        <el-alert
                            class="page-alert"
                            type="info"
                            show-icon
                            :closable="true"
                            title="随时可以对电影添加偏好来生成个性化推荐 🎯"
                        />

                        <section
                            class="evidence-panel"
                            v-loading="topMoviesLoading"
                        >
                            <h2 class="panel-label">热门推荐</h2>
                            <div class="movie-grid">
                                <article
                                    v-for="movie in topMovies"
                                    :key="getMovieMid(movie)"
                                    class="movie-card"
                                >
                                    <div class="poster-frame">
                                        <img
                                            :src="getMovieCover(movie)"
                                            :alt="getMovieTitle(movie)"
                                            @error="
                                                (e) =>
                                                    (e.target.src =
                                                        defaultCover)
                                            "
                                        />
                                    </div>
                                    <div class="movie-info">
                                        <h3 class="movie-title">
                                            {{ getMovieTitle(movie) }}
                                        </h3>
                                        <div class="movie-meta">
                                            <span
                                                v-if="getMovieRating(movie)"
                                                class="rating"
                                            >
                                                ⭐
                                                {{
                                                    getMovieRating(
                                                        movie,
                                                    ).toFixed(1)
                                                }}
                                            </span>
                                            <span
                                                v-if="movie.year"
                                                class="year"
                                            >
                                                {{ movie.year }}
                                            </span>
                                        </div>
                                    </div>
                                </article>
                            </div>
                        </section>
                    </template>

                    <!-- ========== 正常推荐模式 ========== -->
                    <template v-else>
                        <!-- 算法选择器 -->
                        <section class="algo-selector">
                            <span class="algo-label">推荐算法：</span>
                            <div class="algo-buttons">
                                <button
                                    v-for="opt in algorithmOptions"
                                    :key="opt.value"
                                    :class="[
                                        'algo-btn',
                                        {
                                            active:
                                                selectedAlgorithm === opt.value,
                                        },
                                    ]"
                                    @click="onAlgorithmChange(opt.value)"
                                >
                                    <span
                                        class="algo-type-badge"
                                        :class="
                                            opt.type === 'KG'
                                                ? 'kg'
                                                : 'baseline'
                                        "
                                    >
                                        {{ opt.type }}
                                    </span>
                                    {{ opt.label }}
                                </button>
                            </div>
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
                            <div class="recommend-toolbar">
                                <h2 class="panel-label">
                                    {{ currentAlgoLabel }} 推荐结果
                                </h2>
                                <button
                                    class="reroll-btn"
                                    :disabled="
                                        recommendLoading || recommendLoadingMore
                                    "
                                    @click="handleReroll"
                                >
                                    换一批
                                </button>
                            </div>

                            <div class="movie-grid">
                                <article
                                    v-for="item in displayItems"
                                    :key="item.movie.mid"
                                    class="movie-card"
                                    @click="openRecommendationDetail(item)"
                                >
                                    <div class="poster-frame">
                                        <img
                                            :src="
                                                proxyImage(item.movie.cover) ||
                                                defaultCover
                                            "
                                            :alt="item.movie.title"
                                            @error="
                                                (e) =>
                                                    (e.target.src =
                                                        defaultCover)
                                            "
                                        />
                                        <div
                                            class="score-badge"
                                            v-if="item.score"
                                        >
                                            {{ (item.score * 100).toFixed(0) }}
                                        </div>
                                    </div>
                                    <div class="movie-info">
                                        <h3 class="movie-title">
                                            {{ item.movie.title }}
                                        </h3>
                                        <div class="movie-meta">
                                            <span
                                                v-if="item.movie.rating"
                                                class="rating"
                                            >
                                                ⭐
                                                {{
                                                    item.movie.rating.toFixed(1)
                                                }}
                                            </span>
                                            <span
                                                v-if="item.movie.year"
                                                class="year"
                                            >
                                                {{ item.movie.year }}
                                            </span>
                                        </div>
                                        <p class="reason-text">
                                            {{ item.reasons?.[0] || "" }}
                                        </p>
                                    </div>
                                </article>
                            </div>

                            <div
                                v-if="displayItems.length && !showFallbackGrid"
                                class="recommend-feed-state"
                            >
                                <span v-if="recommendLoadingMore">
                                    正在加载更多推荐...
                                </span>
                                <span v-else-if="recommendNoMore">
                                    暂无更多推荐结果
                                </span>
                                <span v-else>下拉到底部继续加载</span>
                            </div>

                            <!-- 个性化推荐为空 → 热门保底 -->
                            <template v-if="showFallbackGrid">
                                <el-alert
                                    class="page-alert fallback-alert"
                                    type="info"
                                    show-icon
                                    :closable="false"
                                    title="个性化推荐暂无结果，以下为热门推荐"
                                />
                                <div class="movie-grid">
                                    <article
                                        v-for="movie in topMovies"
                                        :key="getMovieMid(movie)"
                                        class="movie-card"
                                    >
                                        <div class="poster-frame">
                                            <img
                                                :src="getMovieCover(movie)"
                                                :alt="getMovieTitle(movie)"
                                                @error="
                                                    (e) =>
                                                        (e.target.src =
                                                            defaultCover)
                                                "
                                            />
                                        </div>
                                        <div class="movie-info">
                                            <h3 class="movie-title">
                                                {{ getMovieTitle(movie) }}
                                            </h3>
                                            <div class="movie-meta">
                                                <span
                                                    v-if="getMovieRating(movie)"
                                                    class="rating"
                                                >
                                                    ⭐
                                                    {{
                                                        getMovieRating(
                                                            movie,
                                                        ).toFixed(1)
                                                    }}
                                                </span>
                                                <span
                                                    v-if="movie.year"
                                                    class="year"
                                                >
                                                    {{ movie.year }}
                                                </span>
                                            </div>
                                        </div>
                                    </article>
                                </div>
                            </template>

                            <el-empty
                                v-if="
                                    !recommendLoading &&
                                    !displayItems.length &&
                                    !showFallbackGrid
                                "
                                :image-size="72"
                                description="当前没有可展示的推荐结果"
                            />
                        </section>
                    </template>
                </template>

                <!-- 评估对比标签页 -->
                <template v-if="activeTab === 'evaluate'">
                    <section class="eval-panel" v-loading="evalLoading">
                        <h2 class="panel-label">离线评估报告</h2>

                        <template v-if="evalData?.results">
                            <p class="eval-summary">
                                评估方法: <strong>leave-one-out</strong> |
                                测试用户:
                                <strong>{{ evalData.n_test_users }}</strong>
                            </p>

                            <div
                                v-for="k in [5, 10, 20]"
                                :key="k"
                                class="eval-table-wrapper"
                            >
                                <h3 class="eval-k-label">K = {{ k }}</h3>
                                <table class="eval-table">
                                    <thead>
                                        <tr>
                                            <th>算法</th>
                                            <th>类型</th>
                                            <th>Precision@{{ k }}</th>
                                            <th>Recall@{{ k }}</th>
                                            <th>NDCG@{{ k }}</th>
                                            <th>Hit Rate@{{ k }}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr
                                            v-for="(
                                                data, algoName
                                            ) in evalData.results"
                                            :key="algoName"
                                            :class="{
                                                'kg-row':
                                                    algoName.startsWith('kg_'),
                                            }"
                                        >
                                            <td>{{ data.display_name }}</td>
                                            <td>
                                                <span
                                                    class="algo-type-badge"
                                                    :class="
                                                        algoName.startsWith(
                                                            'kg_',
                                                        )
                                                            ? 'kg'
                                                            : 'baseline'
                                                    "
                                                >
                                                    {{
                                                        algoName.startsWith(
                                                            "kg_",
                                                        )
                                                            ? "KG"
                                                            : "基线"
                                                    }}
                                                </span>
                                            </td>
                                            <td>
                                                {{
                                                    data.metrics[
                                                        k
                                                    ]?.precision?.toFixed(4) ||
                                                    "-"
                                                }}
                                            </td>
                                            <td>
                                                {{
                                                    data.metrics[
                                                        k
                                                    ]?.recall?.toFixed(4) || "-"
                                                }}
                                            </td>
                                            <td>
                                                {{
                                                    data.metrics[
                                                        k
                                                    ]?.ndcg?.toFixed(4) || "-"
                                                }}
                                            </td>
                                            <td>
                                                {{
                                                    data.metrics[
                                                        k
                                                    ]?.hit_rate?.toFixed(4) ||
                                                    "-"
                                                }}
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </template>

                        <el-empty
                            v-else-if="!evalLoading && evalData?.message"
                            :image-size="72"
                            :description="evalData.message"
                        />
                        <el-empty
                            v-else-if="!evalLoading"
                            :image-size="72"
                            description="点击加载评估报告"
                        />
                    </section>
                </template>
            </template>

            <section v-else class="guest-panel card">
                <h2>登录后查看推荐</h2>
                <p>
                    推荐页会展示真实的推荐结果、推荐逻辑，以及不同算法的评估对比。
                </p>
            </section>
        </div>

        <RecommendationDetailDrawer
            v-model="recommendationDrawerVisible"
            :item="selectedRecommendation"
            :algorithm="selectedAlgorithm"
        />

        <!-- 评分弹层 -->
        <el-dialog
            v-model="ratingDialogVisible"
            title="为这部电影评分"
            width="360px"
            :close-on-click-modal="true"
            class="rating-dialog"
        >
            <div class="rating-dialog-body" v-if="ratingDialogMovie">
                <p class="rating-movie-name">
                    {{ getMovieTitle(ratingDialogMovie) }}
                </p>
                <el-rate
                    v-model="ratingDialogValue"
                    :max="5"
                    allow-half
                    size="large"
                    show-score
                    :score-template="ratingDialogValue + ' 分'"
                />
            </div>
            <template #footer>
                <el-button @click="ratingDialogVisible = false">取消</el-button>
                <el-button
                    type="primary"
                    :loading="ratingSubmitting"
                    :disabled="ratingDialogValue <= 0"
                    @click="submitRating"
                >
                    确认评分
                </el-button>
            </template>
        </el-dialog>

        <!-- 回到顶部 -->
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
.insights-view {
    min-height: 100%;
    padding: var(--space-xl) 0 var(--space-2xl);
}

.insights-shell {
    width: min(1280px, calc(100vw - 48px));
    margin: 0 auto;
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

.result-count {
    font-weight: 400;
    opacity: 0.7;
}

.recommend-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-md);
    margin-bottom: var(--space-md);

    .panel-label {
        margin-bottom: 0;
    }
}

.reroll-btn {
    padding: 0.48rem 0.95rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-fast);
    white-space: nowrap;

    &:hover:not(:disabled) {
        color: var(--text-primary);
        border-color: var(--border-color-light);
        transform: translateY(-1px);
    }

    &:disabled {
        opacity: 0.45;
        cursor: not-allowed;
    }
}

.recommend-feed-state {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: var(--space-md) 0 var(--space-xs);
    color: var(--text-muted);
    font-size: 0.88rem;
}

/* Tab Bar */
.tab-bar {
    display: flex;
    gap: var(--space-sm);
    margin-bottom: var(--space-lg);
    border-bottom: 1px solid var(--border-color);
    padding-bottom: var(--space-sm);
}

.tab-btn {
    padding: 0.6rem 1.2rem;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text-muted);
    border-bottom: 2px solid transparent;
    transition: all var(--transition-fast);

    &:hover {
        color: var(--text-primary);
    }

    &.active {
        color: var(--color-accent);
        border-bottom-color: var(--color-accent);
    }
}

/* Algorithm Selector */
.algo-selector {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    margin-bottom: var(--space-lg);
    padding: var(--space-md);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
}

.algo-label {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-secondary);
    white-space: nowrap;
}

.algo-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
}

.algo-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-xs);
    padding: 0.45rem 0.9rem;
    border-radius: var(--radius-md);
    font-size: 0.88rem;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--border-color-light);
        color: var(--text-primary);
    }

    &.active {
        border-color: var(--color-accent);
        background: var(--color-accent-bg);
        color: var(--color-accent);
    }
}

.algo-type-badge {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.04em;

    &.kg {
        background: rgba(59, 130, 246, 0.15);
        color: #3b82f6;
    }

    &.baseline {
        background: rgba(156, 163, 175, 0.15);
        color: var(--text-muted);
    }
}

/* ────────── 冷启动引导区 ────────── */
.cold-start-hero {
    text-align: center;
    padding: var(--space-2xl) var(--space-xl);
    margin-bottom: var(--space-xl);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
}

.hero-icon {
    font-size: 3rem;
    margin-bottom: var(--space-md);
    animation: float 3s ease-in-out infinite;
}

@keyframes float {
    0%,
    100% {
        transform: translateY(0);
    }
    50% {
        transform: translateY(-8px);
    }
}

.hero-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);
}

.hero-desc {
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin-bottom: var(--space-lg);
    line-height: 1.6;

    strong {
        color: var(--color-accent);
    }
}

.progress-bar-wrapper {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    max-width: 320px;
    margin: 0 auto var(--space-lg);
}

.progress-bar {
    flex: 1;
    height: 8px;
    background: var(--bg-secondary);
    border-radius: 4px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--color-accent), #a78bfa);
    border-radius: 4px;
    transition: width 0.4s ease;
}

.progress-text {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--color-accent);
    white-space: nowrap;
}

.skip-btn {
    padding: 0.5rem 1.2rem;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    background: none;
    color: var(--text-muted);
    font-size: 0.85rem;
    cursor: pointer;
    transition: all var(--transition-fast);

    &:hover {
        color: var(--text-primary);
        border-color: var(--border-color-light);
    }
}

/* 种子卡片 */
.seed-card {
    position: relative;
    transition: all var(--transition-normal);

    &.interacted {
        opacity: 0.6;
        pointer-events: none;

        .poster-frame::after {
            content: "";
            position: absolute;
            inset: 0;
            background: rgba(0, 0, 0, 0.35);
        }
    }
}

.interacted-badge {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--color-accent);
    color: #fff;
    font-size: 1.2rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.action-buttons {
    display: flex;
    gap: 4px;
    margin-top: var(--space-xs);
}

.action-btn {
    flex: 1;
    padding: 0.3rem 0;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm, 4px);
    background: var(--bg-secondary);
    color: var(--text-secondary);
    font-size: 0.72rem;
    cursor: pointer;
    transition: all var(--transition-fast);
    white-space: nowrap;

    &:hover:not(:disabled) {
        border-color: var(--border-color-light);
        color: var(--text-primary);
        transform: translateY(-1px);
    }

    &:disabled {
        opacity: 0.4;
        cursor: not-allowed;
    }
}

.like-btn:hover:not(:disabled) {
    border-color: #f43f5e;
    color: #f43f5e;
    background: rgba(244, 63, 94, 0.08);
}

.want-btn:hover:not(:disabled) {
    border-color: #3b82f6;
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.08);
}

.rate-btn:hover:not(:disabled) {
    border-color: #eab308;
    color: #eab308;
    background: rgba(234, 179, 8, 0.08);
}

/* 评分弹层 */
.rating-dialog-body {
    text-align: center;
    padding: var(--space-md) 0;
}

.rating-movie-name {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--space-md);
}

.fallback-alert {
    margin-bottom: var(--space-md);
    margin-top: var(--space-lg);
}

/* Movie Grid */
.movie-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-md);
}

.movie-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    overflow: hidden;
    cursor: pointer;
    transition: all var(--transition-normal);

    &:hover {
        border-color: var(--border-color-light);
        box-shadow: var(--shadow-md);
        transform: translateY(-2px);
    }
}

.poster-frame {
    position: relative;
    aspect-ratio: 2 / 3;
    overflow: hidden;
    background: var(--bg-primary);

    img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
}

.score-badge {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--color-accent);
    color: #fff;
    font-size: 0.75rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.movie-info {
    padding: var(--space-sm) var(--space-md) var(--space-md);
}

.movie-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 var(--space-xs);
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.movie-meta {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: var(--space-xs);
}

.rating {
    color: var(--color-rating);
    font-weight: 600;
}

.reason-text {
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

/* Evaluation Panel */
.eval-panel {
    margin-top: var(--space-md);
}

.eval-summary {
    font-size: 0.9rem;
    color: var(--text-secondary);
    margin-bottom: var(--space-lg);
}

.eval-table-wrapper {
    margin-bottom: var(--space-xl);
}

.eval-k-label {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);
}

.eval-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    overflow: hidden;

    th,
    td {
        padding: 0.7rem 1rem;
        text-align: left;
        border-bottom: 1px solid var(--border-color);
    }

    th {
        background: var(--bg-secondary);
        font-weight: 600;
        color: var(--text-muted);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    td {
        color: var(--text-primary);
        font-variant-numeric: tabular-nums;
    }

    .kg-row {
        background: rgba(59, 130, 246, 0.04);
        font-weight: 500;
    }
}

.evidence-panel {
    margin-bottom: var(--space-lg);
}

.page-alert {
    margin-bottom: var(--space-md);
}

.guest-panel {
    padding: var(--space-xl);
    text-align: center;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);

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

@media (max-width: 860px) {
    .insights-shell {
        width: min(100vw - 24px, 1280px);
    }

    .algo-selector {
        flex-direction: column;
        align-items: flex-start;
    }

    .recommend-toolbar {
        flex-direction: column;
        align-items: stretch;
    }

    .reroll-btn {
        width: 100%;
    }

    .movie-grid {
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    }

    .eval-table {
        font-size: 0.8rem;

        th,
        td {
            padding: 0.5rem 0.6rem;
        }
    }
}

@media (max-width: 640px) {
    .page-title {
        font-size: 1.4rem;
    }

    .algo-buttons {
        width: 100%;
    }

    .algo-btn {
        width: 100%;
        justify-content: center;
    }

    .movie-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .action-btn {
        font-size: 0.65rem;
        padding: 0.25rem 0;
    }
}

/* 回到顶部 + 加载更多 */
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
    z-index: 100;
}

.fade-btn-enter-active,
.fade-btn-leave-active {
    transition: opacity var(--transition-fast);
}

.fade-btn-enter-from,
.fade-btn-leave-to {
    opacity: 0;
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
    font-size: 0.85rem;
}
</style>
