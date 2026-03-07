import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "@/api/auth";

export const useAuthStore = defineStore("auth", () => {
    // ========== State ==========
    const token = ref(localStorage.getItem("access_token") || "");
    const refreshToken = ref(localStorage.getItem("refresh_token") || "");
    const user = ref(JSON.parse(localStorage.getItem("user") || "null"));

    // ========== Getters ==========
    const isLoggedIn = computed(() => !!token.value);
    const username = computed(() => user.value?.username || "");

    // ========== Actions ==========

    /** 登录 */
    async function login(credentials) {
        const { data } = await authApi.login(credentials);
        setTokens(data.access_token, data.refresh_token);
        await fetchMe();
        return data;
    }

    /** 注册 */
    async function register(userData) {
        const { data } = await authApi.register(userData);
        return data;
    }

    /** 登出 */
    async function logout() {
        try {
            await authApi.logout();
        } catch {
            // 忽略登出 API 错误
        } finally {
            clearAuth();
        }
    }

    /** 刷新 Access Token */
    async function refreshAccessToken() {
        if (!refreshToken.value) {
            clearAuth();
            throw new Error("No refresh token");
        }
        const { data } = await authApi.refresh(refreshToken.value);
        setTokens(data.access_token, data.refresh_token || refreshToken.value);
        return data.access_token;
    }

    /** 获取当前用户信息 */
    async function fetchMe() {
        try {
            const { data } = await authApi.getMe();
            user.value = data;
            localStorage.setItem("user", JSON.stringify(data));
        } catch {
            clearAuth();
        }
    }

    /** 初始化：页面加载时检查认证状态 */
    async function init() {
        if (token.value) {
            await fetchMe();
        }
    }

    // ========== Internal ==========

    function setTokens(accessToken, refresh) {
        token.value = accessToken;
        refreshToken.value = refresh;
        localStorage.setItem("access_token", accessToken);
        localStorage.setItem("refresh_token", refresh);
    }

    function clearAuth() {
        token.value = "";
        refreshToken.value = "";
        user.value = null;
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user");
    }

    return {
        // State
        token,
        refreshToken,
        user,
        // Getters
        isLoggedIn,
        username,
        // Actions
        login,
        register,
        logout,
        refreshAccessToken,
        fetchMe,
        init,
    };
});
