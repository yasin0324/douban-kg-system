import api from "./index";

export const moviesApi = {
    /** 搜索电影 */
    search(params) {
        return api.get("/movies/search", { params });
    },

    /** 获取类型列表 */
    getGenres() {
        return api.get("/movies/genres");
    },

    /** 获取高分电影 */
    getTop(limit = 12) {
        return api.get("/movies/top", { params: { limit } });
    },

    /** 筛选电影 */
    filter(params) {
        return api.get("/movies/filter", { params });
    },

    /** 获取电影详情 */
    getDetail(mid) {
        return api.get(`/movies/${mid}`);
    },

    /** 获取电影演职人员 */
    getCredits(mid) {
        return api.get(`/movies/${mid}/credits`);
    },
};
