<script setup>
import { ref, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import PersonCard from "@/components/person/PersonCard.vue";
import { moviesApi } from "@/api/movies";
import { usersApi } from "@/api/users";
import { useAuthStore } from "@/stores/auth";
import { ElMessage } from "element-plus";
import { proxyImage } from "@/utils/image";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const movie = ref(null);
const credits = ref(null);
const loading = ref(true);
const prefStatus = ref(null); // { like: bool, want_to_watch: bool }
const userRating = ref(null); // number or null
const ratingDialog = ref(false);
const ratingInput = ref(0);

const mid = () => route.params.mid;

// 加载电影数据
const fetchMovie = async () => {
    loading.value = true;
    try {
        const [detailRes, creditsRes] = await Promise.all([
            moviesApi.getDetail(mid()),
            moviesApi.getCredits(mid()),
        ]);
        movie.value = detailRes.data;
        credits.value = creditsRes.data;

        // 登录用户：检查偏好和评分
        if (authStore.isLoggedIn) {
            await fetchUserData();
        }
    } catch (err) {
        console.error("加载电影详情失败:", err);
        if (err.response?.status === 404) {
            ElMessage.error("电影不存在");
        }
    } finally {
        loading.value = false;
    }
};

const fetchUserData = async () => {
    try {
        const [prefRes, ratingRes] = await Promise.allSettled([
            usersApi.checkPreference(mid()),
            usersApi.getRating(mid()),
        ]);
        if (prefRes.status === "fulfilled") {
            prefStatus.value = prefRes.value.data;
        }
        if (ratingRes.status === "fulfilled") {
            userRating.value = ratingRes.value.data?.rating ?? null;
        }
    } catch {
        // 忽略
    }
};

// 切换偏好
const togglePref = async (type) => {
    if (!authStore.isLoggedIn) {
        router.push({ name: "login", query: { redirect: route.fullPath } });
        return;
    }
    try {
        const isActive = prefStatus.value?.[type];
        if (isActive) {
            await usersApi.removePreference(mid());
            if (prefStatus.value) prefStatus.value[type] = false;
            ElMessage.success("已取消");
        } else {
            await usersApi.addPreference({ mid: mid(), pref_type: type });
            if (!prefStatus.value) prefStatus.value = {};
            prefStatus.value[type] = true;
            ElMessage.success(type === "like" ? "已喜欢" : "已标记");
        }
    } catch (err) {
        console.error("操作失败:", err);
    }
};

// 提交评分
const submitRating = async () => {
    if (!authStore.isLoggedIn) {
        router.push({ name: "login", query: { redirect: route.fullPath } });
        return;
    }
    try {
        await usersApi.addRating({ mid: mid(), rating: ratingInput.value });
        userRating.value = ratingInput.value;
        ratingDialog.value = false;
        ElMessage.success("评分成功");
    } catch (err) {
        console.error("评分失败:", err);
    }
};

const openRatingDialog = () => {
    ratingInput.value = userRating.value || 7;
    ratingDialog.value = true;
};

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzAwIiBoZWlnaHQ9IjQ1MCIgZmlsbD0iIzFhMWEyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjYwIiBmaWxsPSIjNDA0MDYwIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

onMounted(fetchMovie);

watch(() => route.params.mid, fetchMovie);
</script>

<template>
    <div class="movie-detail container" v-loading="loading">
        <template v-if="movie">
            <!-- 顶部信息区 -->
            <div class="detail-header">
                <div class="poster-wrap">
                    <img
                        :src="proxyImage(movie.cover) || defaultCover"
                        :alt="movie.title"
                        class="poster"
                        @error="(e) => (e.target.src = defaultCover)"
                    />
                </div>

                <div class="info-wrap">
                    <h1 class="movie-title">{{ movie.title }}</h1>

                    <div class="movie-meta">
                        <el-tag v-if="movie.year" type="info" size="small">{{
                            movie.year
                        }}</el-tag>
                        <el-tag
                            v-for="genre in movie.genres || []"
                            :key="genre"
                            size="small"
                            effect="plain"
                        >
                            {{ genre }}
                        </el-tag>
                        <span v-if="movie.regions" class="meta-text">{{
                            movie.regions
                        }}</span>
                    </div>

                    <!-- 评分 -->
                    <div class="rating-section" v-if="movie.rating">
                        <span class="rating-score">{{
                            movie.rating.toFixed(1)
                        }}</span>
                        <el-rate
                            :model-value="movie.rating / 2"
                            disabled
                            show-score
                            score-template=""
                            :colors="['#ffc107', '#ffc107', '#ffc107']"
                        />
                    </div>

                    <!-- 剧情简介 -->
                    <div class="storyline" v-if="movie.storyline">
                        <h3>剧情简介</h3>
                        <p>{{ movie.storyline }}</p>
                    </div>

                    <!-- 操作栏 -->
                    <div class="action-bar">
                        <el-button
                            :type="prefStatus?.like ? 'danger' : 'default'"
                            @click="togglePref('like')"
                        >
                            ❤️ {{ prefStatus?.like ? "已喜欢" : "喜欢" }}
                        </el-button>
                        <el-button
                            :type="
                                prefStatus?.want_to_watch
                                    ? 'warning'
                                    : 'default'
                            "
                            @click="togglePref('want_to_watch')"
                        >
                            📌
                            {{ prefStatus?.want_to_watch ? "已想看" : "想看" }}
                        </el-button>
                        <el-button @click="openRatingDialog">
                            ⭐
                            {{ userRating ? `我的评分 ${userRating}` : "评分" }}
                        </el-button>
                        <el-button
                            type="primary"
                            @click="router.push(`/graph/movie/${movie.mid}`)"
                        >
                            🕸️ 知识图谱
                        </el-button>
                        <el-button
                            v-if="movie.url"
                            tag="a"
                            :href="movie.url"
                            target="_blank"
                            plain
                        >
                            🔗 豆瓣
                        </el-button>
                    </div>
                </div>
            </div>

            <!-- 导演 -->
            <section class="credits-section" v-if="credits?.directors?.length">
                <h2 class="section-title">🎬 导演</h2>
                <div class="person-grid">
                    <PersonCard
                        v-for="person in credits.directors"
                        :key="person.pid"
                        :person="person"
                    />
                </div>
            </section>

            <!-- 演员 -->
            <section class="credits-section" v-if="credits?.actors?.length">
                <h2 class="section-title">🎭 演员</h2>
                <div class="person-grid">
                    <PersonCard
                        v-for="person in credits.actors"
                        :key="person.pid"
                        :person="person"
                    />
                </div>
            </section>
        </template>

        <!-- 评分弹窗 -->
        <el-dialog
            v-model="ratingDialog"
            title="评分"
            width="360px"
            align-center
        >
            <div class="rating-dialog-body">
                <el-slider
                    v-model="ratingInput"
                    :min="1"
                    :max="10"
                    :step="0.5"
                    show-input
                    :show-input-controls="false"
                />
            </div>
            <template #footer>
                <el-button @click="ratingDialog = false">取消</el-button>
                <el-button type="primary" @click="submitRating">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<style scoped lang="scss">
.detail-header {
    display: flex;
    gap: var(--space-xl);
    margin-bottom: var(--space-2xl);
}

.poster-wrap {
    flex-shrink: 0;
}

.poster {
    width: 260px;
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg);
    aspect-ratio: 2 / 3;
    object-fit: cover;
}

.info-wrap {
    flex: 1;
    min-width: 0;
}

.movie-title {
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: var(--space-md);
}

.movie-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
    align-items: center;
    margin-bottom: var(--space-md);
}

.meta-text {
    color: var(--text-muted);
    font-size: 0.85rem;
}

.rating-section {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    margin-bottom: var(--space-lg);
}

.rating-score {
    font-size: 2.5rem;
    font-weight: 800;
    color: var(--color-rating);
    line-height: 1;
}

.storyline {
    margin-bottom: var(--space-lg);

    h3 {
        font-size: 1rem;
        font-weight: 600;
        color: var(--text-secondary);
        margin-bottom: var(--space-sm);
    }

    p {
        color: var(--text-secondary);
        font-size: 0.95rem;
        line-height: 1.8;
    }
}

.action-bar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-sm);
}

.credits-section {
    margin-bottom: var(--space-xl);
}

.person-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-xs);
}

.rating-dialog-body {
    padding: var(--space-md) var(--space-lg);
}

@media (max-width: 768px) {
    .detail-header {
        flex-direction: column;
        align-items: center;
    }

    .poster {
        width: 200px;
    }

    .movie-title {
        font-size: 1.5rem;
        text-align: center;
    }

    .action-bar {
        justify-content: center;
    }
}
</style>
