import api from "./index";

export const graphApi = {
    /** 获取电影关联图谱 */
    getMovieGraph(mid, params = {}) {
        return api.get(`/graph/movie/${mid}`, {
            params: {
                depth: params.depth || 1,
                node_limit: params.nodeLimit || 150,
                edge_limit: params.edgeLimit || 300,
            },
        });
    },

    /** 获取影人关联图谱 */
    getPersonGraph(pid, params = {}) {
        return api.get(`/graph/person/${pid}`, {
            params: {
                depth: params.depth || 1,
                node_limit: params.nodeLimit || 150,
                edge_limit: params.edgeLimit || 300,
            },
        });
    },

    /** 最短路径查询 */
    getPath(from, to, maxHops = 6) {
        return api.get("/graph/path", {
            params: { from, to, max_hops: maxHops },
        });
    },

    /** 共同电影查询 */
    getCommon(person1, person2, limit = 50) {
        return api.get("/graph/common", {
            params: { person1, person2, limit },
        });
    },
};
