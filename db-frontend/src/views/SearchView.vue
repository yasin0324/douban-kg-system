<script setup>
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import PersonCard from "@/components/person/PersonCard.vue";
import { moviesApi } from "@/api/movies";
import { personsApi } from "@/api/persons";
import { proxyImage } from "@/utils/image";

const route = useRoute();
const router = useRouter();

const activeTab = ref("movies");
const movieLoading = ref(false);
const personLoading = ref(false);

// 电影结果
const movieResults = ref([]);
const movieTotal = ref(0);
const moviePage = ref(1);

// 影人结果
const personResults = ref([]);
const personTotal = ref(0);
const personPage = ref(1);

const pageSize = 20;

// 搜索电影
const searchMovies = async () => {
    const q = route.query.q;
    if (!q) return;
    movieLoading.value = true;
    try {
        const { data } = await moviesApi.search({
            q,
            page: moviePage.value,
            size: pageSize,
        });
        movieResults.value = data.items;
        movieTotal.value = data.total;
    } catch (err) {
        console.error("电影搜索失败:", err);
    } finally {
        movieLoading.value = false;
    }
};

// 搜索影人
const searchPersons = async () => {
    const q = route.query.q;
    if (!q) return;
    personLoading.value = true;
    try {
        const { data } = await personsApi.search({
            q,
            page: personPage.value,
            size: pageSize,
        });
        personResults.value = data.items || data;
        personTotal.value = data.total || personResults.value.length;
    } catch (err) {
        console.error("影人搜索失败:", err);
    } finally {
        personLoading.value = false;
    }
};

// 监听查询参数变化
watch(
    () => route.query.q,
    () => {
        moviePage.value = 1;
        personPage.value = 1;
        searchMovies();
        searchPersons();
    },
    { immediate: true },
);

// 分页切换
const handleMoviePage = (page) => {
    moviePage.value = page;
    searchMovies();
};

const handlePersonPage = (page) => {
    personPage.value = page;
    searchPersons();
};
</script>

<template>
    <div class="search-view container">
        <h1 class="page-title">
            搜索: <span class="search-keyword">{{ route.query.q }}</span>
        </h1>

        <el-tabs v-model="activeTab" class="search-tabs">
            <!-- 电影结果 -->
            <el-tab-pane :label="`电影 (${movieTotal})`" name="movies">
                <!-- Loading 提示 -->
                <div v-if="movieLoading" class="loading-hint">
                    <span class="loading-spinner"></span>
                    <span>正在搜索电影，请稍候...</span>
                </div>

                <!-- 搜索结果 -->
                <template v-else>
                    <div v-if="movieResults.length" class="movie-results">
                        <div
                            v-for="movie in movieResults"
                            :key="movie.mid"
                            class="movie-result-item card"
                            @click="router.push(`/movies/${movie.mid}`)"
                        >
                            <img
                                class="result-cover"
                                :src="proxyImage(movie.cover) || ''"
                                :alt="movie.title"
                                loading="lazy"
                                @error="
                                    (e) => (e.target.style.display = 'none')
                                "
                            />
                            <div class="result-info">
                                <h3 class="result-title">{{ movie.title }}</h3>
                                <div class="result-meta">
                                    <span v-if="movie.year">{{
                                        movie.year
                                    }}</span>
                                    <span
                                        v-if="
                                            movie.genres && movie.genres.length
                                        "
                                    >
                                        {{ movie.genres.join(" / ") }}
                                    </span>
                                </div>
                                <div class="result-rating" v-if="movie.rating">
                                    <span class="star">★</span>
                                    {{ movie.rating.toFixed(1) }}
                                </div>
                            </div>
                        </div>
                    </div>
                    <el-empty
                        v-if="!movieLoading && movieResults.length === 0"
                        description="未找到相关电影"
                    />

                    <div class="pagination-wrap" v-if="movieTotal > pageSize">
                        <el-pagination
                            :current-page="moviePage"
                            :page-size="pageSize"
                            :total="movieTotal"
                            layout="prev, pager, next"
                            @current-change="handleMoviePage"
                        />
                    </div>
                </template>
            </el-tab-pane>

            <!-- 影人结果 -->
            <el-tab-pane :label="`影人 (${personTotal})`" name="persons">
                <!-- Loading 提示 -->
                <div v-if="personLoading" class="loading-hint">
                    <span class="loading-spinner"></span>
                    <span>正在搜索影人，请稍候...</span>
                </div>

                <!-- 搜索结果 -->
                <template v-else>
                    <div v-if="personResults.length" class="person-results">
                        <PersonCard
                            v-for="person in personResults"
                            :key="person.pid"
                            :person="person"
                        />
                    </div>
                    <el-empty
                        v-if="!personLoading && personResults.length === 0"
                        description="未找到相关影人"
                    />

                    <div class="pagination-wrap" v-if="personTotal > pageSize">
                        <el-pagination
                            :current-page="personPage"
                            :page-size="pageSize"
                            :total="personTotal"
                            layout="prev, pager, next"
                            @current-change="handlePersonPage"
                        />
                    </div>
                </template>
            </el-tab-pane>
        </el-tabs>
    </div>
</template>

<style scoped lang="scss">
.search-view {
    padding-top: var(--space-xl);
}

.search-keyword {
    color: var(--color-accent);
}

.search-tabs {
    :deep(.el-tabs__item) {
        color: var(--text-secondary);
        font-size: 1rem;

        &.is-active {
            color: var(--color-accent);
        }
    }

    :deep(.el-tabs__active-bar) {
        background-color: var(--color-accent);
    }
}

/* ========== Loading 提示 ========== */

.loading-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: var(--space-2xl) 0;
    color: var(--text-muted);
    font-size: 0.95rem;
}

.loading-spinner {
    width: 20px;
    height: 20px;
    border: 2.5px solid var(--border-color);
    border-top-color: var(--color-accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}

/* ========== 搜索结果样式 ========== */

.movie-results {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
}

.movie-result-item {
    display: flex;
    gap: var(--space-md);
    padding: var(--space-md);
    cursor: pointer;
}

.result-cover {
    width: 80px;
    height: 112px;
    object-fit: cover;
    border-radius: var(--radius-sm);
    flex-shrink: 0;
    background: var(--bg-secondary);
}

.result-info {
    flex: 1;
    min-width: 0;
}

.result-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 6px;
}

.result-meta {
    display: flex;
    gap: var(--space-sm);
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-bottom: 6px;
}

.result-rating {
    color: var(--color-rating);
    font-weight: 600;
    font-size: 0.9rem;

    .star {
        font-size: 0.8rem;
    }
}

.person-results {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: var(--space-sm);
}

.pagination-wrap {
    display: flex;
    justify-content: center;
    margin-top: var(--space-xl);
}
</style>
