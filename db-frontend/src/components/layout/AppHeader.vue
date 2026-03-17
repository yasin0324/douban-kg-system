<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { Search } from "@element-plus/icons-vue";

const router = useRouter();
const authStore = useAuthStore();
const themeStore = useThemeStore();
const searchQuery = ref("");

const handleSearch = () => {
    const q = searchQuery.value.trim();
    if (q) {
        router.push({ path: "/search", query: { q } });
    }
    searchQuery.value = ""
};

const handleLogout = async () => {
    await authStore.logout();
    router.push("/");
};
</script>

<template>
    <header class="app-header">
        <div class="header-inner container">
            <!-- Logo -->
            <router-link to="/" class="logo">
                <span class="logo-icon">🎬</span>
                <span class="logo-text">豆瓣知识图谱</span>
            </router-link>

            <!-- Navigation -->
            <nav class="nav-links">
                <router-link to="/">首页</router-link>
                <router-link to="/movies/filter">电影库</router-link>
                <router-link to="/recommend">推荐</router-link>
                <router-link to="/graph/explore">知识图谱</router-link>
                <router-link to="/stats">统计</router-link>
            </nav>

            <!-- Search -->
            <div class="search-box">
                <el-input
                    v-model="searchQuery"
                    placeholder="搜索电影或影人..."
                    :prefix-icon="Search"
                    clearable
                    @keyup.enter="handleSearch"
                    size="default"
                />
            </div>

            <!-- Theme Toggle -->
            <button
                class="theme-toggle"
                @click="themeStore.toggle()"
                :title="themeStore.isDark ? '切换到浅色模式' : '切换到深色模式'"
            >
                <transition name="theme-icon" mode="out-in">
                    <span v-if="themeStore.isDark" key="dark" class="theme-icon"
                        >🌙</span
                    >
                    <span v-else key="light" class="theme-icon">☀️</span>
                </transition>
            </button>

            <!-- User Area -->
            <div class="user-area">
                <template v-if="authStore.isLoggedIn">
                    <el-dropdown trigger="click">
                        <span class="user-avatar">
                            <el-avatar :size="32">{{
                                authStore.user?.username?.[0]?.toUpperCase() ||
                                "U"
                            }}</el-avatar>
                        </span>
                        <template #dropdown>
                            <el-dropdown-menu>
                                <el-dropdown-item
                                    @click="router.push('/profile')"
                                    >个人中心</el-dropdown-item
                                >
                                <el-dropdown-item divided @click="handleLogout"
                                    >退出登录</el-dropdown-item
                                >
                            </el-dropdown-menu>
                        </template>
                    </el-dropdown>
                </template>
                <template v-else>
                    <el-button
                        type="primary"
                        size="small"
                        @click="router.push('/login')"
                        >登录</el-button
                    >
                </template>
            </div>
        </div>
    </header>
</template>

<style scoped lang="scss">
.app-header {
    position: sticky;
    top: 0;
    z-index: 1000;
    height: var(--header-height);
    background: var(--header-bg);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border-color);
}

.header-inner {
    display: flex;
    align-items: center;
    height: 100%;
    gap: var(--space-lg);
}

.logo {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    color: var(--text-primary) !important;
    font-weight: 700;
    font-size: 1.1rem;
    white-space: nowrap;
    flex-shrink: 0;

    .logo-icon {
        font-size: 1.5rem;
    }

    &:hover {
        color: var(--color-accent) !important;
    }
}

.nav-links {
    display: flex;
    gap: var(--space-md);
    flex-shrink: 0;

    a {
        color: var(--text-secondary);
        font-size: 0.9rem;
        padding: var(--space-xs) var(--space-sm);
        border-radius: var(--radius-sm);
        transition: all var(--transition-fast);

        &:hover,
        &.router-link-active {
            color: var(--color-accent);
        }

        &.router-link-active {
            background: var(--color-accent-bg);
        }
    }
}

.search-box {
    flex: 1;
    max-width: 360px;
}

.theme-toggle {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border: 1px solid var(--border-color);
    border-radius: 50%;
    background: var(--bg-card);
    cursor: pointer;
    transition: all var(--transition-fast);

    &:hover {
        border-color: var(--color-accent);
        background: var(--color-accent-bg);
        transform: rotate(15deg);
    }
}

.theme-icon {
    font-size: 1.1rem;
    line-height: 1;
}

.theme-icon-enter-active,
.theme-icon-leave-active {
    transition: all 0.2s ease;
}

.theme-icon-enter-from {
    opacity: 0;
    transform: rotate(-90deg) scale(0.5);
}

.theme-icon-leave-to {
    opacity: 0;
    transform: rotate(90deg) scale(0.5);
}

.user-area {
    flex-shrink: 0;
}

.user-avatar {
    cursor: pointer;
    display: flex;
    align-items: center;
}

// 响应式
@media (max-width: 768px) {
    .nav-links {
        display: none;
    }

    .search-box {
        max-width: 200px;
    }
}
</style>
