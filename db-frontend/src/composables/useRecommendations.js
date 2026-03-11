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
            error.value =
                err.response?.data?.detail || "推荐加载失败，请稍后重试";
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
    const response = await recommendApi.explain(params);
    return response.data;
}
