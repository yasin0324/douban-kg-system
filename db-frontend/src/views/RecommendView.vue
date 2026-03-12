<script setup>
import { computed, onMounted, ref, watch } from "vue";
import RecommendationDetailDrawer from "@/components/recommend/RecommendationDetailDrawer.vue";
import { useRecommendationFeed } from "@/composables/useRecommendations";
import { useAuthStore } from "@/stores/auth";
import { proxyImage } from "@/utils/image";

const authStore = useAuthStore();

const algorithmOptions = [
    { value: "kg_path", label: "KG 路径推荐", type: "KG" },
    { value: "kg_embed", label: "KG 嵌入推荐", type: "KG" },
    { value: "content", label: "基于内容推荐", type: "基线" },
    { value: "item_cf", label: "协同过滤推荐", type: "基线" },
];

const selectedAlgorithm = ref("kg_path");

const {
    data: recommendData,
    loading: recommendLoading,
    error: recommendError,
    loadRecommendations,
} = useRecommendationFeed({
    algorithm: "kg_path",
    limit: 12,
});

const selectedRecommendation = ref(null);
const recommendationDrawerVisible = ref(false);
const evalData = ref(null);
const evalLoading = ref(false);
const activeTab = ref("recommend");

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgZmlsbD0iIzBmMTcyYSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjQyIiBmaWxsPSIjMzM0MTU1IiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

const displayItems = computed(() => recommendData.value?.items || []);

const currentAlgoLabel = computed(() => {
    const opt = algorithmOptions.find((o) => o.value === selectedAlgorithm.value);
    return opt ? opt.label : selectedAlgorithm.value;
});

onMounted(async () => {
    await loadPage();
});

watch(
    () => authStore.isLoggedIn,
    async (loggedIn) => {
        if (loggedIn) {
            await loadPage();
            return;
        }
        selectedRecommendation.value = null;
        recommendationDrawerVisible.value = false;
    },
);

async function loadPage() {
    if (!authStore.isLoggedIn) {
        return;
    }
    await loadWithAlgorithm(selectedAlgorithm.value);
}

async function loadWithAlgorithm(algo) {
    try {
        await loadRecommendations({
            algorithm: algo,
            limit: 12,
        });
    } catch (err) {
        console.error("推荐页加载失败:", err);
    }
}

async function onAlgorithmChange(algo) {
    selectedAlgorithm.value = algo;
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
</script>

<template>
    <div class="insights-view">
        <div class="insights-shell">
            <header class="page-header">
                <h1 class="page-title">🎯 个性化推荐</h1>
                <p class="page-subtitle">基于知识图谱的可解释推荐实验系统</p>
            </header>

            <template v-if="authStore.isLoggedIn">
                <!-- 标签页切换 -->
                <div class="tab-bar">
                    <button
                        :class="['tab-btn', { active: activeTab === 'recommend' }]"
                        @click="activeTab = 'recommend'"
                    >
                        推荐结果
                    </button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'evaluate' }]"
                        @click="activeTab = 'evaluate'; loadEvaluation()"
                    >
                        算法评估对比
                    </button>
                </div>

                <!-- 推荐结果标签页 -->
                <template v-if="activeTab === 'recommend'">
                    <!-- 算法选择器 -->
                    <section class="algo-selector">
                        <span class="algo-label">推荐算法：</span>
                        <div class="algo-buttons">
                            <button
                                v-for="opt in algorithmOptions"
                                :key="opt.value"
                                :class="['algo-btn', { active: selectedAlgorithm === opt.value }]"
                                @click="onAlgorithmChange(opt.value)"
                            >
                                <span class="algo-type-badge" :class="opt.type === 'KG' ? 'kg' : 'baseline'">
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

                    <section class="evidence-panel" v-loading="recommendLoading">
                        <h2 class="panel-label">
                            {{ currentAlgoLabel }} 推荐结果
                            <span v-if="displayItems.length" class="result-count">
                                ({{ displayItems.length }} 部)
                            </span>
                        </h2>

                        <div class="movie-grid">
                            <article
                                v-for="item in displayItems"
                                :key="item.movie.mid"
                                class="movie-card"
                                @click="openRecommendationDetail(item)"
                            >
                                <div class="poster-frame">
                                    <img
                                        :src="proxyImage(item.movie.cover) || defaultCover"
                                        :alt="item.movie.title"
                                        @error="(e) => (e.target.src = defaultCover)"
                                    />
                                    <div class="score-badge" v-if="item.score">
                                        {{ (item.score * 100).toFixed(0) }}
                                    </div>
                                </div>
                                <div class="movie-info">
                                    <h3 class="movie-title">{{ item.movie.title }}</h3>
                                    <div class="movie-meta">
                                        <span v-if="item.movie.rating" class="rating">
                                            ⭐ {{ item.movie.rating.toFixed(1) }}
                                        </span>
                                        <span v-if="item.movie.year" class="year">
                                            {{ item.movie.year }}
                                        </span>
                                    </div>
                                    <p class="reason-text">{{ item.reasons?.[0] || "" }}</p>
                                </div>
                            </article>
                        </div>

                        <el-empty
                            v-if="!recommendLoading && !displayItems.length"
                            :image-size="72"
                            description="当前没有可展示的推荐结果"
                        />
                    </section>
                </template>

                <!-- 评估对比标签页 -->
                <template v-if="activeTab === 'evaluate'">
                    <section class="eval-panel" v-loading="evalLoading">
                        <h2 class="panel-label">离线评估报告</h2>

                        <template v-if="evalData?.results">
                            <p class="eval-summary">
                                评估方法: <strong>leave-one-out</strong> |
                                测试用户: <strong>{{ evalData.n_test_users }}</strong>
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
                                            v-for="(data, algoName) in evalData.results"
                                            :key="algoName"
                                            :class="{ 'kg-row': algoName.startsWith('kg_') }"
                                        >
                                            <td>{{ data.display_name }}</td>
                                            <td>
                                                <span
                                                    class="algo-type-badge"
                                                    :class="algoName.startsWith('kg_') ? 'kg' : 'baseline'"
                                                >
                                                    {{ algoName.startsWith("kg_") ? "KG" : "基线" }}
                                                </span>
                                            </td>
                                            <td>{{ data.metrics[k]?.precision?.toFixed(4) || "-" }}</td>
                                            <td>{{ data.metrics[k]?.recall?.toFixed(4) || "-" }}</td>
                                            <td>{{ data.metrics[k]?.ndcg?.toFixed(4) || "-" }}</td>
                                            <td>{{ data.metrics[k]?.hit_rate?.toFixed(4) || "-" }}</td>
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
                <h2>登录后查看可解释推荐</h2>
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

.page-header {
    padding-bottom: var(--space-lg);
    border-bottom: 1px solid var(--border-color);
    margin-bottom: var(--space-xl);
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
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
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
}
</style>
