import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import "element-plus/theme-chalk/dark/css-vars.css";

import App from "./App.vue";
import router from "./router";
import "@/assets/styles/main.scss";
import { useThemeStore } from "@/stores/theme";
import { useAuthStore } from "@/stores/auth";

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);
app.use(ElementPlus);

// 初始化主题（必须在 pinia 注册后）
const themeStore = useThemeStore();
themeStore.init();
const authStore = useAuthStore();
authStore.init();

app.mount("#app");
