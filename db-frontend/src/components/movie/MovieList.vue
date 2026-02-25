<script setup>
import MovieCard from "./MovieCard.vue";

defineProps({
    movies: {
        type: Array,
        default: () => [],
    },
    loading: {
        type: Boolean,
        default: false,
    },
});
</script>

<template>
    <div class="movie-list" v-loading="loading">
        <div v-if="movies.length" class="movie-grid">
            <MovieCard
                v-for="movie in movies"
                :key="movie.mid"
                :movie="movie"
            />
        </div>
        <el-empty v-else-if="!loading" description="暂无电影数据" />
    </div>
</template>

<style scoped lang="scss">
.movie-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: var(--space-lg);
}

@media (max-width: 768px) {
    .movie-grid {
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: var(--space-md);
    }
}
</style>
