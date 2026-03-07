import api from "./index";

export const personsApi = {
    /** 搜索影人 */
    search(params) {
        return api.get("/persons/search", { params });
    },

    /** 获取影人详情 */
    getDetail(pid) {
        return api.get(`/persons/${pid}`);
    },

    /** 获取影人参演/执导电影 */
    getMovies(pid, params) {
        return api.get(`/persons/${pid}/movies`, { params });
    },

    /** 获取影人合作者 */
    getCollaborators(pid, limit = 10) {
        return api.get(`/persons/${pid}/collaborators`, { params: { limit } });
    },
};
