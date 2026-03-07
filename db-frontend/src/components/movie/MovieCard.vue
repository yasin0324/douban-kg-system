<script setup>
import { useRouter } from "vue-router";
import { proxyImage } from "@/utils/image";

const props = defineProps({
    movie: {
        type: Object,
        required: true,
    },
});

const router = useRouter();

const goDetail = () => {
    router.push(`/movies/${props.movie.mid}`);
};

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjMwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjMwMCIgZmlsbD0iIzFhMWEyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjQwIiBmaWxsPSIjNDA0MDYwIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";
</script>

<template>
    <div class="movie-card" @click="goDetail">
        <div class="card-poster">
            <img
                :src="proxyImage(movie.cover) || defaultCover"
                :alt="movie.title"
                loading="lazy"
                @error="(e) => (e.target.src = defaultCover)"
            />
            <div class="card-rating" v-if="movie.rating">
                <span class="star">★</span>
                <span>{{ movie.rating.toFixed(1) }}</span>
            </div>
            <div class="card-rating no-rating" v-else>
                <span>暂无评分</span>
            </div>
        </div>
        <div class="card-info">
            <h3 class="card-title" :title="movie.title">{{ movie.title }}</h3>
            <div class="card-meta">
                <span v-if="movie.year" class="meta-year">{{
                    movie.year
                }}</span>
                <span
                    v-if="movie.genres && movie.genres.length"
                    class="meta-genres"
                >
                    {{ movie.genres.slice(0, 2).join(" / ") }}
                </span>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.movie-card {
    cursor: pointer;
    border-radius: var(--radius-md);
    overflow: hidden;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    transition: all var(--transition-normal);

    &:hover {
        transform: translateY(-6px);
        box-shadow: var(--shadow-lg);
        border-color: var(--color-accent);

        .card-poster img {
            transform: scale(1.05);
        }
    }
}

.card-poster {
    position: relative;
    aspect-ratio: 2 / 3;
    overflow: hidden;
    background: var(--bg-secondary);

    img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        transition: transform var(--transition-normal);
    }
}

.card-rating {
    position: absolute;
    top: var(--space-sm);
    right: var(--space-sm);
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(4px);
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--color-rating);
    display: flex;
    align-items: center;
    gap: 3px;

    .star {
        font-size: 0.7rem;
    }

    &.no-rating {
        color: var(--text-muted);
        background: rgba(0, 0, 0, 0.6);
        font-weight: normal;
        font-size: 0.75rem;
    }
}

.card-info {
    padding: var(--space-sm) var(--space-md);
}

.card-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 4px;
}

.card-meta {
    display: flex;
    gap: var(--space-sm);
    font-size: 0.8rem;
    color: var(--text-muted);
}
</style>
