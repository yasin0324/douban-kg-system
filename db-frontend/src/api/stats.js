import api from "./index";

export const statsApi = {
    /** 总体统计 */
    getOverview() {
        return api.get("/stats/overview");
    },

    /** 类型分布 */
    getGenreDistribution() {
        return api.get("/stats/genre-distribution");
    },

    /** 年代分布 */
    getYearDistribution() {
        return api.get("/stats/year-distribution");
    },

    /** 参演最多的演员 */
    getTopActors(limit = 20) {
        return api.get("/stats/top-actors", { params: { limit } });
    },

    /** 执导最多的导演 */
    getTopDirectors(limit = 20) {
        return api.get("/stats/top-directors", { params: { limit } });
    },

    /** 评分分布 */
    getRatingDistribution() {
        return api.get("/stats/rating-distribution");
    },
};
