import { ref } from "vue";
import { ElMessage } from "element-plus";
import { usersApi } from "@/api/users";
import { RECOMMENDATION_EMPTY_FEEDBACK } from "@/utils/recommendation";

const createEmptyFeedback = () => ({ ...RECOMMENDATION_EMPTY_FEEDBACK });

export function useRecommendationFeedback() {
    const preferenceStateMap = ref({});
    const preferenceLoadingMap = ref({});

    const hydratePreferenceState = async (movieIds = []) => {
        const uniqueIds = [...new Set(movieIds)].filter(Boolean);
        if (!uniqueIds.length) {
            preferenceStateMap.value = {};
            return;
        }

        const nextState = {};
        const results = await Promise.allSettled(
            uniqueIds.map((mid) => usersApi.checkPreference(mid)),
        );
        uniqueIds.forEach((mid, index) => {
            const result = results[index];
            if (result.status === "fulfilled") {
                nextState[mid] = result.value.data;
                return;
            }
            nextState[mid] = createEmptyFeedback();
        });
        preferenceStateMap.value = nextState;
    };

    const togglePreference = async (mid, prefType) => {
        const currentState =
            preferenceStateMap.value[mid] || createEmptyFeedback();
        const isActive =
            prefType === "like"
                ? currentState.is_liked
                : currentState.is_want_to_watch;
        preferenceLoadingMap.value = {
            ...preferenceLoadingMap.value,
            [mid]: true,
        };

        try {
            if (isActive) {
                await usersApi.removePreference(mid);
                preferenceStateMap.value = {
                    ...preferenceStateMap.value,
                    [mid]: createEmptyFeedback(),
                };
                ElMessage.success("已取消标记");
            } else {
                await usersApi.addPreference({ mid, pref_type: prefType });
                preferenceStateMap.value = {
                    ...preferenceStateMap.value,
                    [mid]: {
                        is_liked: prefType === "like",
                        is_want_to_watch: prefType === "want_to_watch",
                    },
                };
                ElMessage.success(
                    prefType === "like" ? "已加入喜欢" : "已加入想看",
                );
            }
            return preferenceStateMap.value[mid];
        } finally {
            preferenceLoadingMap.value = {
                ...preferenceLoadingMap.value,
                [mid]: false,
            };
        }
    };

    return {
        preferenceStateMap,
        preferenceLoadingMap,
        hydratePreferenceState,
        togglePreference,
    };
}
