import axios from "axios";
import { ElMessage } from "element-plus";

// 创建 Axios 实例
const api = axios.create({
    baseURL: "/api",
    timeout: 15000,
    headers: {
        "Content-Type": "application/json",
    },
});

// 请求拦截器：附带 Bearer Token
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem("access_token");
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error),
);

// 响应拦截器：处理 401 自动刷新、全局错误提示
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
    failedQueue.forEach((prom) => {
        if (error) {
            prom.reject(error);
        } else {
            prom.resolve(token);
        }
    });
    failedQueue = [];
};

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        // 401 且非刷新请求 → 尝试刷新 Token
        if (
            error.response?.status === 401 &&
            !originalRequest._retry &&
            !originalRequest.url.includes("/auth/refresh") &&
            !originalRequest.url.includes("/auth/login")
        ) {
            if (isRefreshing) {
                return new Promise((resolve, reject) => {
                    failedQueue.push({ resolve, reject });
                })
                    .then((token) => {
                        originalRequest.headers.Authorization = `Bearer ${token}`;
                        return api(originalRequest);
                    })
                    .catch((err) => Promise.reject(err));
            }

            originalRequest._retry = true;
            isRefreshing = true;

            try {
                const refreshToken = localStorage.getItem("refresh_token");
                if (!refreshToken) {
                    throw new Error("No refresh token");
                }

                const { data } = await axios.post("/api/auth/refresh", {
                    refresh_token: refreshToken,
                });

                const newToken = data.access_token;
                localStorage.setItem("access_token", newToken);
                if (data.refresh_token) {
                    localStorage.setItem("refresh_token", data.refresh_token);
                }

                processQueue(null, newToken);
                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                return api(originalRequest);
            } catch (refreshError) {
                processQueue(refreshError, null);
                localStorage.removeItem("access_token");
                localStorage.removeItem("refresh_token");
                localStorage.removeItem("user");
                window.location.href = "/login";
                return Promise.reject(refreshError);
            } finally {
                isRefreshing = false;
            }
        }

        // 全局错误提示（排除 401 Token 刷新、404 资源不存在）
        const status = error.response?.status;
        const message =
            error.response?.data?.detail ||
            error.response?.data?.message ||
            "请求失败，请稍后重试";
        if (status !== 401 && status !== 404) {
            ElMessage.error(message);
        }

        return Promise.reject(error);
    },
);

export default api;
