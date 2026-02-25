import api from "./index";

export const usersApi = {
    // ========== 偏好 ==========

    /** 添加偏好（喜欢/想看） */
    addPreference(data) {
        return api.post("/users/preferences", data);
    },

    /** 获取偏好列表 */
    getPreferences(params) {
        return api.get("/users/preferences", { params });
    },

    /** 检查某电影的偏好状态 */
    checkPreference(mid) {
        return api.get(`/users/preferences/check/${mid}`);
    },

    /** 删除偏好 */
    removePreference(mid) {
        return api.delete(`/users/preferences/${mid}`);
    },

    // ========== 评分 ==========

    /** 添加评分 */
    addRating(data) {
        return api.post("/users/ratings", data);
    },

    /** 获取评分列表 */
    getRatings(params) {
        return api.get("/users/ratings", { params });
    },

    /** 获取某电影的用户评分 */
    getRating(mid) {
        return api.get(`/users/ratings/${mid}`);
    },

    /** 删除评分 */
    removeRating(mid) {
        return api.delete(`/users/ratings/${mid}`);
    },
};
