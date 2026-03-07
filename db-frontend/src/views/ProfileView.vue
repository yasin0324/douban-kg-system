<script setup>
import { ref, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { usersApi } from "@/api/users";
import { moviesApi } from "@/api/movies";
import { ElMessage, ElMessageBox } from "element-plus";
import { proxyImage } from "@/utils/image";

const router = useRouter();
const authStore = useAuthStore();

const activeTab = ref("like");
const loading = ref(false);
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 12;

// 电影信息缓存 { mid: movieData }
const movieCache = ref({});

const defaultCover =
    "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIwIiBoZWlnaHQ9IjE4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTIwIiBoZWlnaHQ9IjE4MCIgZmlsbD0iIzFhMWEyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjMwIiBmaWxsPSIjNDA0MDYwIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7wn46sPC90ZXh0Pjwvc3ZnPg==";

// 加载列表数据
const fetchData = async () => {
    loading.value = true;
    items.value = [];
    try {
        let res;
        if (activeTab.value === "rating") {
            res = await usersApi.getRatings({
                page: page.value,
                size: pageSize,
            });
        } else {
            res = await usersApi.getPreferences({
                pref_type: activeTab.value,
                page: page.value,
                size: pageSize,
            });
        }
        items.value = res.data.items || [];
        total.value = res.data.total || 0;

        // 批量加载电影信息
        await fetchMovieInfoBatch(items.value);
    } catch (err) {
        console.error("加载数据失败:", err);
    } finally {
        loading.value = false;
    }
};

// 批量获取电影信息
const fetchMovieInfoBatch = async (list) => {
    const mids = list
        .map((item) => item.mid)
        .filter((mid) => !movieCache.value[mid]);
    const promises = mids.map((mid) =>
        moviesApi
            .getDetail(mid)
            .then((res) => {
                movieCache.value[mid] = res.data;
            })
            .catch(() => {
                movieCache.value[mid] = { mid, title: mid, cover: null };
            }),
    );
    await Promise.allSettled(promises);
};

const getMovie = (mid) => movieCache.value[mid] || { mid, title: mid };

// 删除偏好
const handleRemovePref = async (item) => {
    try {
        await ElMessageBox.confirm("确定要取消该标记吗？", "提示", {
            type: "warning",
        });
        await usersApi.removePreference(item.mid);
        ElMessage.success("已取消");
        await fetchData();
    } catch (err) {
        if (err !== "cancel") console.error(err);
    }
};

// 删除评分
const handleRemoveRating = async (item) => {
    try {
        await ElMessageBox.confirm("确定要删除该评分吗？", "提示", {
            type: "warning",
        });
        await usersApi.removeRating(item.mid);
        ElMessage.success("已删除");
        await fetchData();
    } catch (err) {
        if (err !== "cancel") console.error(err);
    }
};

const handlePageChange = (p) => {
    page.value = p;
    fetchData();
};

const formatDate = (dateStr) => {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return d.toLocaleDateString("zh-CN");
};

// Tab 切换时重置分页
watch(activeTab, () => {
    page.value = 1;
    fetchData();
});

onMounted(fetchData);
</script>

<template>
    <div class="profile-view container">
        <!-- 用户信息卡片 -->
        <div class="user-card" v-if="authStore.user">
            <div class="user-avatar-large">
                <el-avatar :size="72">{{
                    authStore.user.username?.[0]?.toUpperCase() || "U"
                }}</el-avatar>
            </div>
            <div class="user-info">
                <h1 class="user-name">
                    {{ authStore.user.nickname || authStore.user.username }}
                </h1>
                <p class="user-detail" v-if="authStore.user.nickname">
                    @{{ authStore.user.username }}
                </p>
                <p class="user-detail" v-if="authStore.user.email">
                    📧 {{ authStore.user.email }}
                </p>
                <p class="user-detail" v-if="authStore.user.created_at">
                    📅 注册于 {{ formatDate(authStore.user.created_at) }}
                </p>
            </div>
        </div>

        <!-- Tab 切换 -->
        <div class="tabs-section">
            <el-tabs v-model="activeTab" class="profile-tabs">
                <el-tab-pane label="❤️ 喜欢" name="like" />
                <el-tab-pane label="📌 想看" name="want_to_watch" />
                <el-tab-pane label="⭐ 评分" name="rating" />
            </el-tabs>
        </div>

        <!-- 列表 -->
        <div class="items-list" v-loading="loading">
            <div v-if="items.length === 0 && !loading" class="empty-state">
                <p>暂无数据</p>
            </div>

            <div v-else class="item-grid">
                <div v-for="item in items" :key="item.id" class="item-card">
                    <div
                        class="item-poster"
                        @click="router.push(`/movies/${item.mid}`)"
                    >
                        <img
                            :src="
                                proxyImage(getMovie(item.mid).cover) ||
                                defaultCover
                            "
                            :alt="getMovie(item.mid).title"
                            @error="(e) => (e.target.src = defaultCover)"
                        />
                    </div>
                    <div class="item-info">
                        <h3
                            class="item-title"
                            @click="router.push(`/movies/${item.mid}`)"
                        >
                            {{ getMovie(item.mid).title || item.mid }}
                        </h3>
                        <p class="item-meta">
                            <span
                                v-if="getMovie(item.mid).rating"
                                class="item-rating"
                            >
                                ⭐
                                {{ getMovie(item.mid).rating?.toFixed(1) }}
                            </span>
                            <span v-if="getMovie(item.mid).year">
                                {{ getMovie(item.mid).year }}
                            </span>
                        </p>

                        <!-- 评分专属信息 -->
                        <p v-if="activeTab === 'rating'" class="item-my-rating">
                            我的评分：<strong>{{ item.rating }}</strong>
                        </p>

                        <p class="item-date">
                            {{
                                formatDate(
                                    activeTab === "rating"
                                        ? item.rated_at
                                        : item.created_at,
                                )
                            }}
                        </p>

                        <el-button
                            size="small"
                            type="danger"
                            plain
                            @click="
                                activeTab === 'rating'
                                    ? handleRemoveRating(item)
                                    : handleRemovePref(item)
                            "
                        >
                            {{
                                activeTab === "rating" ? "删除评分" : "取消标记"
                            }}
                        </el-button>
                    </div>
                </div>
            </div>

            <!-- 分页 -->
            <div class="pagination-wrap" v-if="total > pageSize">
                <el-pagination
                    :current-page="page"
                    :page-size="pageSize"
                    :total="total"
                    layout="prev, pager, next"
                    @current-change="handlePageChange"
                />
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.profile-view {
    padding-top: var(--space-xl);
    padding-bottom: var(--space-2xl);
}

.user-card {
    display: flex;
    align-items: center;
    gap: var(--space-lg);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--space-xl);
    margin-bottom: var(--space-xl);
    box-shadow: var(--shadow-sm);
}

.user-info {
    flex: 1;
}

.user-name {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-xs);
}

.user-detail {
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin-bottom: 2px;
}

.tabs-section {
    margin-bottom: var(--space-md);
}

.empty-state {
    text-align: center;
    padding: var(--space-2xl) 0;
    color: var(--text-muted);
    font-size: 1rem;
}

.item-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: var(--space-md);
}

.item-card {
    display: flex;
    gap: var(--space-md);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-md);
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--border-color-light);
        box-shadow: var(--shadow-sm);
    }
}

.item-poster {
    flex-shrink: 0;
    cursor: pointer;

    img {
        width: 80px;
        height: 120px;
        object-fit: cover;
        border-radius: var(--radius-sm);
        transition: transform var(--transition-fast);
    }

    &:hover img {
        transform: scale(1.05);
    }
}

.item-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.item-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-primary);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &:hover {
        color: var(--color-accent);
    }
}

.item-meta {
    display: flex;
    gap: var(--space-sm);
    color: var(--text-muted);
    font-size: 0.8rem;
}

.item-rating {
    color: var(--color-rating);
}

.item-my-rating {
    font-size: 0.85rem;
    color: var(--text-secondary);

    strong {
        color: var(--color-rating);
        font-size: 1rem;
    }
}

.item-date {
    color: var(--text-muted);
    font-size: 0.75rem;
}

.pagination-wrap {
    display: flex;
    justify-content: center;
    margin-top: var(--space-xl);
}

@media (max-width: 768px) {
    .user-card {
        flex-direction: column;
        text-align: center;
    }

    .item-grid {
        grid-template-columns: 1fr;
    }
}
</style>
