import api from "./index";

const serializeParams = (params = {}) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === "") {
            return;
        }
        if (Array.isArray(value)) {
            value.forEach((item) => {
                if (item !== undefined && item !== null && item !== "") {
                    searchParams.append(key, item);
                }
            });
            return;
        }
        searchParams.append(key, value);
    });
    return searchParams.toString();
};

export const recommendApi = {
    /** 获取个性化推荐结果 */
    getPersonal(params = {}, config = {}) {
        return api.get("/recommend/personal", {
            ...config,
            params,
            paramsSerializer: { serialize: serializeParams },
        });
    },

    /** 获取推荐解释图 */
    explain(params = {}, config = {}) {
        return api.get("/recommend/explain", {
            ...config,
            params,
            paramsSerializer: { serialize: serializeParams },
        });
    },
};
