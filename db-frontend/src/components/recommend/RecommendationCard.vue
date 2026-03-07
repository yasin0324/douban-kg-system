<script setup>
import { computed } from "vue";
import { proxyImage } from "@/utils/image";
import { formatSourceAlgorithmLabel } from "@/utils/recommendation";

const props = defineProps({
    item: {
        type: Object,
        required: true,
    },
    compact: {
        type: Boolean,
        default: false,
    },
    showActions: {
        type: Boolean,
        default: false,
    },
    feedbackState: {
        type: Object,
        default: () => ({
            is_liked: false,
            is_want_to_watch: false,
        }),
    },
    feedbackLoading: {
        type: Boolean,
        default: false,
    },
});

const emit = defineEmits(["open", "toggle-preference"]);

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjMwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjMwMCIgZmlsbD0iIzFhMWEyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjQwIiBmaWxsPSIjNDA0MDYwIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

const movie = computed(() => props.item.movie || {});
const visibleReasons = computed(() =>
    (props.item.reasons || []).slice(0, props.compact ? 1 : 2),
);
</script>

<template>
    <article
        class="recommendation-card"
        :class="{ compact }"
        @click="emit('open', item)"
    >
        <div class="poster-wrap">
            <img
                :src="proxyImage(movie.cover) || defaultCover"
                :alt="movie.title"
                loading="lazy"
                @error="(e) => (e.target.src = defaultCover)"
            />
            <div class="rating-badge" v-if="movie.rating">
                ★ {{ movie.rating.toFixed(1) }}
            </div>
            <div class="rating-badge empty" v-else>暂无评分</div>
        </div>

        <div class="content-wrap">
            <div class="title-row">
                <h3 class="movie-title" :title="movie.title">{{ movie.title }}</h3>
                <span class="year-chip" v-if="movie.year">{{ movie.year }}</span>
            </div>

            <p class="genre-line" v-if="movie.genres?.length">
                {{ movie.genres.slice(0, 3).join(" / ") }}
            </p>

            <div class="reason-tags" v-if="visibleReasons.length">
                <el-tag
                    v-for="reason in visibleReasons"
                    :key="reason"
                    size="small"
                    effect="plain"
                    round
                    class="reason-tag"
                >
                    {{ reason }}
                </el-tag>
            </div>

            <div class="source-tags" v-if="item.source_algorithms?.length">
                <span class="source-label">来源</span>
                <el-tag
                    v-for="algorithm in item.source_algorithms"
                    :key="algorithm"
                    size="small"
                    type="success"
                    effect="plain"
                >
                    {{ formatSourceAlgorithmLabel(algorithm) }}
                </el-tag>
            </div>

            <div class="footer-row">
                <el-button
                    text
                    type="primary"
                    class="reason-link"
                    @click.stop="emit('open', item)"
                >
                    查看原因
                </el-button>

                <div v-if="showActions" class="action-buttons">
                    <el-button
                        size="small"
                        :loading="feedbackLoading"
                        :type="feedbackState?.is_liked ? 'danger' : 'default'"
                        @click.stop="
                            emit('toggle-preference', {
                                mid: movie.mid,
                                prefType: 'like',
                            })
                        "
                    >
                        {{ feedbackState?.is_liked ? "已喜欢" : "喜欢" }}
                    </el-button>
                    <el-button
                        size="small"
                        :loading="feedbackLoading"
                        :type="
                            feedbackState?.is_want_to_watch
                                ? 'warning'
                                : 'default'
                        "
                        @click.stop="
                            emit('toggle-preference', {
                                mid: movie.mid,
                                prefType: 'want_to_watch',
                            })
                        "
                    >
                        {{
                            feedbackState?.is_want_to_watch ? "已想看" : "想看"
                        }}
                    </el-button>
                    <el-button
                        size="small"
                        @click.stop="emit('open', item)"
                    >
                        去评分
                    </el-button>
                </div>
            </div>
        </div>
    </article>
</template>

<style scoped lang="scss">
.recommendation-card {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    overflow: hidden;
    cursor: pointer;
    transition:
        transform var(--transition-fast),
        box-shadow var(--transition-fast),
        border-color var(--transition-fast);

    &:hover {
        transform: translateY(-4px);
        box-shadow: var(--shadow-md);
        border-color: rgba(0, 181, 29, 0.25);
    }

    &.compact {
        .poster-wrap {
            aspect-ratio: 2.2 / 3;
        }

        .content-wrap {
            gap: var(--space-sm);
            padding: var(--space-md);
        }
    }
}

.poster-wrap {
    position: relative;
    aspect-ratio: 16 / 10;
    overflow: hidden;
    background: var(--bg-secondary);

    img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
}

.rating-badge {
    position: absolute;
    top: var(--space-sm);
    right: var(--space-sm);
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.68);
    color: #f8d24a;
    font-size: 0.78rem;
    font-weight: 700;

    &.empty {
        color: #fff;
        font-weight: 500;
    }
}

.content-wrap {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-md);
    padding: var(--space-lg);
}

.title-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-sm);
}

.movie-title {
    font-size: 1.02rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.35;
}

.year-chip {
    flex-shrink: 0;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--bg-primary);
    color: var(--text-muted);
    font-size: 0.78rem;
}

.genre-line {
    color: var(--text-secondary);
    font-size: 0.88rem;
}

.reason-tags,
.source-tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
}

.reason-tag {
    max-width: 100%;

    :deep(.el-tag__content) {
        max-width: 100%;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
}

.source-label {
    color: var(--text-muted);
    font-size: 0.8rem;
    align-self: center;
}

.footer-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
    margin-top: auto;
    padding-top: var(--space-sm);
    border-top: 1px solid var(--border-color);
}

.reason-link {
    padding-left: 0;
    padding-right: 0;
}

.action-buttons {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-xs);
}

@media (max-width: 768px) {
    .content-wrap {
        padding: var(--space-md);
    }

    .footer-row {
        flex-direction: column;
        align-items: stretch;
    }

    .action-buttons {
        width: 100%;
        justify-content: stretch;

        .el-button {
            flex: 1;
        }
    }
}
</style>
