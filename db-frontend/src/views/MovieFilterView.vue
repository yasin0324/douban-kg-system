<script setup>
import { ref, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import MovieList from "@/components/movie/MovieList.vue";
import { moviesApi } from "@/api/movies";

const route = useRoute();
const router = useRouter();

const DEFAULT_YEAR_FROM = 1950;
const DEFAULT_YEAR_TO = 2026;
const DEFAULT_RATING_MIN = 0;
const DEFAULT_SORT_BY = "weighted";
const DEFAULT_PAGE = 1;

const selectedGenre = ref("");
const contentType = ref("");
const yearRange = ref([DEFAULT_YEAR_FROM, DEFAULT_YEAR_TO]);
const ratingMin = ref(DEFAULT_RATING_MIN);
const sortBy = ref(DEFAULT_SORT_BY);
const genres = ref([]);

const movies = ref([]);
const total = ref(0);
const page = ref(DEFAULT_PAGE);
const pageSize = 24;
const loading = ref(false);

const getQueryValue = (value) =>
    Array.isArray(value) ? value[0] : (value ?? "");
const parseIntWithFallback = (value, fallback) => {
    const parsed = Number.parseInt(getQueryValue(value), 10);
    return Number.isFinite(parsed) ? parsed : fallback;
};
const parseFloatWithFallback = (value, fallback) => {
    const parsed = Number.parseFloat(getQueryValue(value));
    return Number.isFinite(parsed) ? parsed : fallback;
};

const applyQueryState = () => {
    selectedGenre.value = getQueryValue(route.query.genre);
    contentType.value = getQueryValue(route.query.content_type);
    const yearFrom = parseIntWithFallback(
        route.query.year_from,
        DEFAULT_YEAR_FROM,
    );
    const yearTo = parseIntWithFallback(route.query.year_to, DEFAULT_YEAR_TO);
    yearRange.value = [
        Math.min(Math.max(yearFrom, DEFAULT_YEAR_FROM), DEFAULT_YEAR_TO),
        Math.min(Math.max(yearTo, DEFAULT_YEAR_FROM), DEFAULT_YEAR_TO),
    ];
    ratingMin.value = Math.min(
        Math.max(
            parseFloatWithFallback(route.query.rating_min, DEFAULT_RATING_MIN),
            0,
        ),
        9.5,
    );
    const sortByValue = getQueryValue(route.query.sort_by);
    sortBy.value = ["weighted", "rating", "votes"].includes(sortByValue)
        ? sortByValue
        : DEFAULT_SORT_BY;
    page.value = Math.max(
        parseIntWithFallback(route.query.page, DEFAULT_PAGE),
        DEFAULT_PAGE,
    );
};

const buildQueryState = () => {
    const query = {};
    if (selectedGenre.value) query.genre = selectedGenre.value;
    if (contentType.value) query.content_type = contentType.value;
    if (yearRange.value[0] > DEFAULT_YEAR_FROM) {
        query.year_from = String(yearRange.value[0]);
    }
    if (yearRange.value[1] < DEFAULT_YEAR_TO) {
        query.year_to = String(yearRange.value[1]);
    }
    if (ratingMin.value > DEFAULT_RATING_MIN) {
        query.rating_min = String(ratingMin.value);
    }
    if (sortBy.value !== DEFAULT_SORT_BY) query.sort_by = sortBy.value;
    if (page.value > DEFAULT_PAGE) query.page = String(page.value);
    return query;
};

const isSameQuery = (currentQuery, nextQuery) => {
    const currentKeys = Object.keys(currentQuery).sort();
    const nextKeys = Object.keys(nextQuery).sort();
    if (currentKeys.length !== nextKeys.length) return false;
    return currentKeys.every((key, index) => {
        if (key !== nextKeys[index]) return false;
        return String(getQueryValue(currentQuery[key])) === nextQuery[key];
    });
};

const syncRouteQuery = async () => {
    const nextQuery = buildQueryState();
    if (isSameQuery(route.query, nextQuery)) {
        return false;
    }
    await router.replace({ query: nextQuery });
    return true;
};

onMounted(async () => {
    try {
        const { data } = await moviesApi.getGenres();
        genres.value = data;
    } catch (err) {
        console.error("加载类型失败:", err);
    }
});

const fetchMovies = async () => {
    loading.value = true;
    try {
        const params = {
            page: page.value,
            size: pageSize,
            sort_by: sortBy.value,
        };
        if (selectedGenre.value) params.genre = selectedGenre.value;
        if (contentType.value) params.content_type = contentType.value;
        if (yearRange.value[0] > 1950) params.year_from = yearRange.value[0];
        if (yearRange.value[1] < 2026) params.year_to = yearRange.value[1];
        if (ratingMin.value > 0) params.rating_min = ratingMin.value;

        const { data } = await moviesApi.filter(params);
        movies.value = data.items;
        total.value = data.total;
    } catch (err) {
        console.error("筛选失败:", err);
    } finally {
        loading.value = false;
    }
};

watch(
    () => route.query,
    () => {
        applyQueryState();
        fetchMovies();
    },
    { immediate: true },
);

const handleFilter = async () => {
    page.value = DEFAULT_PAGE;
    const queryChanged = await syncRouteQuery();
    if (!queryChanged) {
        fetchMovies();
    }
};

const handlePage = async (p) => {
    page.value = p;
    const queryChanged = await syncRouteQuery();
    if (!queryChanged) {
        fetchMovies();
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
};

const selectGenre = (genre) => {
    selectedGenre.value = selectedGenre.value === genre ? "" : genre;
    handleFilter();
};

const resetFilters = () => {
    selectedGenre.value = "";
    contentType.value = "";
    yearRange.value = [DEFAULT_YEAR_FROM, DEFAULT_YEAR_TO];
    ratingMin.value = DEFAULT_RATING_MIN;
    sortBy.value = DEFAULT_SORT_BY;
    handleFilter();
};
</script>

<template>
    <div class="filter-view container">
        <h1 class="page-title">🎞️ 电影库</h1>

        <!-- 筛选区域 -->
        <div class="filter-panel card">
            <!-- 类型筛选 -->
            <div class="filter-group">
                <label class="filter-label">类型</label>
                <div class="genre-options">
                    <el-tag
                        v-for="genre in genres"
                        :key="genre"
                        :effect="selectedGenre === genre ? 'dark' : 'plain'"
                        :type="selectedGenre === genre ? 'success' : 'info'"
                        round
                        class="genre-option"
                        @click="selectGenre(genre)"
                    >
                        {{ genre }}
                    </el-tag>
                </div>
            </div>

            <!-- 形式筛选 -->
            <div class="filter-group">
                <label class="filter-label">形式</label>
                <el-radio-group
                    v-model="contentType"
                    size="small"
                    @change="handleFilter"
                >
                    <el-radio-button value="">全部</el-radio-button>
                    <el-radio-button value="movie"
                        >电影 (Movie)</el-radio-button
                    >
                    <el-radio-button value="tv">剧集 (TV)</el-radio-button>
                </el-radio-group>
            </div>

            <!-- 年代范围 -->
            <div class="filter-group">
                <label class="filter-label"
                    >年代 ({{ yearRange[0] }} - {{ yearRange[1] }})</label
                >
                <el-slider
                    v-model="yearRange"
                    range
                    :min="1950"
                    :max="2026"
                    :step="1"
                    @change="handleFilter"
                />
            </div>

            <!-- 最低评分 -->
            <div class="filter-group">
                <label class="filter-label"
                    >最低评分
                    {{ ratingMin > 0 ? `(≥ ${ratingMin})` : "(不限)" }}</label
                >
                <el-slider
                    v-model="ratingMin"
                    :min="0"
                    :max="9.5"
                    :step="0.5"
                    :marks="{ 0: '不限', 5: '5', 7: '7', 8: '8', 9: '9' }"
                    @change="handleFilter"
                />
            </div>

            <div class="filter-actions">
                <div class="sort-wrap">
                    <label class="filter-label sort-label">排序</label>
                    <el-select
                        v-model="sortBy"
                        size="small"
                        style="width: 130px"
                        @change="handleFilter"
                    >
                        <el-option label="🏆 加权推荐" value="weighted" />
                        <el-option label="⭐ 评分最高" value="rating" />
                        <el-option label="💬 最多人评" value="votes" />
                    </el-select>
                </div>
                <el-button @click="resetFilters" size="small"
                    >重置筛选</el-button
                >
                <span class="result-count">共 {{ total }} 部电影</span>
            </div>
        </div>

        <!-- 电影列表 -->
        <MovieList :movies="movies" :loading="loading" />

        <!-- 分页 -->
        <div class="pagination-wrap" v-if="total > pageSize">
            <el-pagination
                :current-page="page"
                :page-size="pageSize"
                :total="total"
                layout="prev, pager, next, total"
                @current-change="handlePage"
            />
        </div>
    </div>
</template>

<style scoped lang="scss">
.filter-view {
    padding-top: var(--space-xl);
}

.filter-panel {
    padding: var(--space-lg);
    margin-bottom: var(--space-xl);

    &:hover {
        transform: none;
    }
}

.filter-group {
    margin-bottom: var(--space-lg);

    &:last-of-type {
        margin-bottom: var(--space-md);
    }
}

.filter-label {
    display: block;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: var(--space-sm);
}

.genre-options {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.genre-option {
    cursor: pointer;
    transition: all var(--transition-fast);
}

.filter-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--space-sm);
}

.sort-wrap {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
}

.sort-label {
    margin-bottom: 0;
    white-space: nowrap;
}

.result-count {
    font-size: 0.85rem;
    color: var(--text-muted);
}

.pagination-wrap {
    display: flex;
    justify-content: center;
    margin-top: var(--space-xl);
}

:deep(.el-slider__bar) {
    background-color: var(--color-accent);
}

:deep(.el-slider__button) {
    border-color: var(--color-accent);
}
</style>
