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

    /** 黄金搭档网络图 */
    getCollaborations() {
        return api.get("/stats/collaborations");
    },

    /** 类型关联和弦图 */
    getGenreCoOccurrence() {
        return api.get("/stats/genre-co-occurrence");
    },

    /** 主要流派年代演变 */
    getGenreYearTrends() {
        return api.get("/stats/genre-year-trends");
    },

    /** 评分年代变化 */
    getRatingYearTrends() {
        return api.get("/stats/rating-year-trends");
    },

    /** 参演高分电影最多的演员 */
    getTopRatedActors(limit = 20) {
        return api.get("/stats/top-rated-actors", { params: { limit } });
    },

    /** 执导高分电影最多的导演 */
    getTopRatedDirectors(limit = 20) {
        return api.get("/stats/top-rated-directors", { params: { limit } });
    },

    /** Top演员参演质量分布 */
    getActorRatingDistribution() {
        return api.get("/stats/actor-rating-distribution");
    },

    /** 评分与评论人数散点图 */
    getRatingVoteScatter(limit = 240) {
        return api.get("/stats/rating-vote-scatter", { params: { limit } });
    },
};
