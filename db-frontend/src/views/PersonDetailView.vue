<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import PersonCard from "@/components/person/PersonCard.vue";
import { personsApi } from "@/api/persons";

const route = useRoute();
const router = useRouter();

const person = ref(null);
const personMovies = ref(null);
const collaborators = ref([]);
const loading = ref(true);
const activeTab = ref("all");

// 作品列表折叠
const showAllMovies = ref(false);
const defaultShowCount = 20;

// 回到顶部
const showBackTop = ref(false);

const pid = () => route.params.pid;

// 加载数据
const fetchData = async () => {
    loading.value = true;
    showAllMovies.value = false;
    try {
        const [detailRes, moviesRes, collabRes] = await Promise.all([
            personsApi.getDetail(pid()),
            personsApi.getMovies(pid()),
            personsApi.getCollaborators(pid(), 10),
        ]);
        person.value = detailRes.data;
        personMovies.value = moviesRes.data;
        collaborators.value = collabRes.data;
    } catch (err) {
        console.error("加载影人详情失败:", err);
    } finally {
        loading.value = false;
    }
};

// 按 Tab 筛选电影
const filteredMovies = computed(() => {
    if (!personMovies.value?.movies) return [];
    const all = personMovies.value.movies;
    if (activeTab.value === "director")
        return all.filter((m) => m.role === "director");
    if (activeTab.value === "actor")
        return all.filter((m) => m.role === "actor");
    return all;
});

// 排序：按年份倒序
const sortedMovies = computed(() => {
    return [...filteredMovies.value].sort(
        (a, b) => (b.year || 0) - (a.year || 0),
    );
});

// 截断显示
const displayedMovies = computed(() => {
    if (showAllMovies.value) return sortedMovies.value;
    return sortedMovies.value.slice(0, defaultShowCount);
});

const hasMore = computed(() => sortedMovies.value.length > defaultShowCount);
const hiddenCount = computed(
    () => sortedMovies.value.length - defaultShowCount,
);

// 切换 Tab 时重置折叠
watch(activeTab, () => {
    showAllMovies.value = false;
});

// 滚动监听
const handleScroll = () => {
    showBackTop.value = window.scrollY > 600;
};

const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
};

onMounted(() => {
    fetchData();
    window.addEventListener("scroll", handleScroll);
});

onUnmounted(() => {
    window.removeEventListener("scroll", handleScroll);
});

watch(() => route.params.pid, fetchData);
</script>

<template>
    <div class="person-detail container" v-loading="loading">
        <template v-if="person">
            <!-- 基本信息 -->
            <div class="person-header">
                <el-avatar :size="100" class="person-avatar-lg">
                    {{ person.name?.[0] || "?" }}
                </el-avatar>
                <div class="person-info">
                    <h1 class="person-name-lg">{{ person.name }}</h1>
                    <div class="person-meta-list">
                        <span v-if="person.sex" class="meta-item">
                            <strong>性别：</strong>{{ person.sex }}
                        </span>
                        <span v-if="person.birth" class="meta-item">
                            <strong>出生日期：</strong>{{ person.birth }}
                        </span>
                        <span v-if="person.birthplace" class="meta-item">
                            <strong>出生地：</strong>{{ person.birthplace }}
                        </span>
                        <span v-if="person.profession" class="meta-item">
                            <strong>职业：</strong>{{ person.profession }}
                        </span>
                    </div>
                    <div class="person-stats">
                        <span class="stat-badge" v-if="person.movie_count">
                            参演 {{ person.movie_count }} 部
                        </span>
                        <span class="stat-badge" v-if="person.directed_count">
                            执导 {{ person.directed_count }} 部
                        </span>
                    </div>
                    <el-button
                        type="primary"
                        size="small"
                        @click="router.push(`/graph/person/${person.pid}`)"
                        style="margin-top: 12px"
                    >
                        🕸️ 查看知识图谱
                    </el-button>
                </div>
            </div>

            <!-- 个人简介 -->
            <section class="bio-section" v-if="person.biography">
                <h2 class="section-title">📝 个人简介</h2>
                <p class="bio-text">{{ person.biography }}</p>
            </section>

            <!-- 作品列表 -->
            <section
                class="filmography-section"
                v-if="personMovies?.movies?.length"
            >
                <h2 class="section-title">🎬 参演 / 执导作品</h2>

                <el-radio-group
                    v-model="activeTab"
                    size="small"
                    class="film-tabs"
                >
                    <el-radio-button value="all"
                        >全部 ({{
                            personMovies.movies.length
                        }})</el-radio-button
                    >
                    <el-radio-button value="director">
                        导演 ({{
                            personMovies.movies.filter(
                                (m) => m.role === "director",
                            ).length
                        }})
                    </el-radio-button>
                    <el-radio-button value="actor">
                        演员 ({{
                            personMovies.movies.filter(
                                (m) => m.role === "actor",
                            ).length
                        }})
                    </el-radio-button>
                </el-radio-group>

                <div class="film-list">
                    <div
                        v-for="movie in displayedMovies"
                        :key="movie.mid"
                        class="film-item card"
                        @click="router.push(`/movies/${movie.mid}`)"
                    >
                        <span class="film-year">{{ movie.year || "—" }}</span>
                        <div class="film-info">
                            <span class="film-title">{{ movie.title }}</span>
                            <el-tag
                                v-if="movie.role"
                                size="small"
                                :type="
                                    movie.role === 'director'
                                        ? 'warning'
                                        : 'info'
                                "
                                effect="plain"
                            >
                                {{
                                    movie.role === "director" ? "导演" : "演员"
                                }}
                            </el-tag>
                        </div>
                        <span class="film-rating" v-if="movie.rating">
                            ★ {{ movie.rating.toFixed(1) }}
                        </span>
                    </div>
                </div>

                <!-- 展开/收起按钮 -->
                <div class="expand-area" v-if="hasMore">
                    <el-button
                        text
                        type="primary"
                        @click="showAllMovies = !showAllMovies"
                    >
                        {{
                            showAllMovies
                                ? "收起 ↑"
                                : `展开全部 ${hiddenCount} 部作品 ↓`
                        }}
                    </el-button>
                </div>
            </section>

            <!-- 合作者 -->
            <section class="collab-section" v-if="collaborators.length">
                <h2 class="section-title">🤝 常见合作者</h2>
                <div class="collab-grid">
                    <PersonCard
                        v-for="collab in collaborators"
                        :key="collab.pid"
                        :person="collab"
                    />
                </div>
            </section>
        </template>

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
.person-detail {
    padding-top: var(--space-xl);
}

.person-header {
    display: flex;
    gap: var(--space-xl);
    margin-bottom: var(--space-2xl);
    align-items: flex-start;
}

.person-avatar-lg {
    flex-shrink: 0;
    background: var(--bg-card);
    color: var(--color-accent);
    font-size: 2.5rem;
    font-weight: 700;
    border: 2px solid var(--border-color);
}

.person-info {
    flex: 1;
}

.person-name-lg {
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: var(--space-md);
}

.person-meta-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
}

.meta-item {
    font-size: 0.9rem;
    color: var(--text-secondary);

    strong {
        color: var(--text-muted);
        font-weight: 500;
    }
}

.person-stats {
    display: flex;
    gap: var(--space-sm);
}

.stat-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--radius-sm);
    background: var(--color-accent-bg);
    color: var(--color-accent);
    font-size: 0.8rem;
    font-weight: 600;
}

.bio-section {
    margin-bottom: var(--space-xl);
}

.bio-text {
    color: var(--text-secondary);
    line-height: 1.8;
    font-size: 0.95rem;
}

.filmography-section {
    margin-bottom: var(--space-xl);
}

.film-tabs {
    margin-bottom: var(--space-md);
}

.film-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
}

.film-item {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    padding: var(--space-sm) var(--space-md);
    cursor: pointer;

    &:hover {
        transform: none;
    }
}

.film-year {
    flex-shrink: 0;
    width: 48px;
    font-size: 0.85rem;
    color: var(--text-muted);
    font-weight: 600;
}

.film-info {
    flex: 1;
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    min-width: 0;
}

.film-title {
    font-size: 0.95rem;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.film-rating {
    flex-shrink: 0;
    color: var(--color-rating);
    font-weight: 600;
    font-size: 0.85rem;
}

.collab-section {
    margin-bottom: var(--space-xl);
}

.collab-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: var(--space-xs);
}

/* 展开/收起 */
.expand-area {
    text-align: center;
    padding: var(--space-md) 0;
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
    .person-header {
        flex-direction: column;
        align-items: center;
        text-align: center;
    }

    .person-meta-list {
        justify-content: center;
    }

    .person-stats {
        justify-content: center;
    }

    .back-top-btn {
        bottom: 24px;
        right: 24px;
    }
}
</style>
