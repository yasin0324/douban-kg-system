import { ref } from "vue";
import { defineStore } from "pinia";

export const useThemeStore = defineStore("theme", () => {
    const isDark = ref(true);

    /** 初始化主题：读取 localStorage → 跟随系统 → 默认深色 */
    const init = () => {
        const saved = localStorage.getItem("theme");
        if (saved) {
            isDark.value = saved === "dark";
        } else {
            isDark.value = window.matchMedia(
                "(prefers-color-scheme: dark)",
            ).matches;
        }
        applyTheme();
    };

    /** 切换深浅模式 */
    const toggle = () => {
        isDark.value = !isDark.value;
        localStorage.setItem("theme", isDark.value ? "dark" : "light");
        applyTheme();
    };

    /** 应用主题到 DOM */
    const applyTheme = () => {
        const html = document.documentElement;
        if (isDark.value) {
            html.classList.add("dark");
        } else {
            html.classList.remove("dark");
        }
    };

    return { isDark, init, toggle };
});
