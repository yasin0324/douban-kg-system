import { ref } from "vue";
import { recommendApi } from "@/api/recommend";

export function useRecommendationFeed(defaultOptions = {}) {
    const data = ref(null);
    const loading = ref(false);
    const error = ref("");
    const options = ref({
        algorithm: "kg_path",
        limit: 12,
        ...defaultOptions,
    });

    const loadRecommendations = async (overrides = {}) => {
        loading.value = true;
        error.value = "";

        const mergedOptions = {
            ...options.value,
            ...overrides,
        };
        ["exclude_movie_ids"].forEach((key) => {
            if (!mergedOptions[key]?.length) {
                delete mergedOptions[key];
            }
        });
        if (!mergedOptions.reroll_token) {
            delete mergedOptions.reroll_token;
        }
        options.value = mergedOptions;

        try {
            const response = await recommendApi.getPersonal(mergedOptions);
            data.value = response.data;
            return response.data;
        } catch (err) {
            if (err.response?.status === 503) {
                error.value = "推荐服务繁忙，请稍后重试或切换其他算法";
            } else if (
                err.response?.status === 504 ||
                err.code === "ECONNABORTED"
            ) {
                error.value = "推荐计算超时，请稍后重试或切换其他算法";
            } else {
                error.value =
                    err.response?.data?.detail || "推荐加载失败，请稍后重试";
            }
            data.value = null;
            throw err;
        } finally {
            loading.value = false;
        }
    };

    return {
        data,
        loading,
        error,
        options,
        loadRecommendations,
    };
}

export async function fetchRecommendationExplanation(params) {
    const response = await recommendApi.explain(params, { silentError: true });
    return response.data;
}
