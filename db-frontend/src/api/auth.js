import api from "./index";

export const authApi = {
    /** 用户注册 */
    register(data) {
        return api.post("/auth/register", data);
    },

    /** 用户登录 */
    login(data) {
        return api.post("/auth/login", data);
    },

    /** 登出 */
    logout() {
        return api.post("/auth/logout");
    },

    /** 刷新 Token */
    refresh(refreshToken) {
        return api.post("/auth/refresh", { refresh_token: refreshToken });
    },

    /** 获取当前用户信息 */
    getMe() {
        return api.get("/auth/me");
    },
};
