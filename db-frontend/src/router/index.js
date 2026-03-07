import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: "/",
            name: "home",
            component: () => import("@/views/HomeView.vue"),
        },
        {
            path: "/search",
            name: "search",
            component: () => import("@/views/SearchView.vue"),
        },
        {
            path: "/movies/filter",
            name: "movie-filter",
            component: () => import("@/views/MovieFilterView.vue"),
        },
        {
            path: "/recommend",
            name: "recommend",
            component: () => import("@/views/RecommendView.vue"),
        },
        {
            path: "/movies/:mid",
            name: "movie-detail",
            component: () => import("@/views/MovieDetailView.vue"),
            props: true,
        },
        {
            path: "/persons/:pid",
            name: "person-detail",
            component: () => import("@/views/PersonDetailView.vue"),
            props: true,
        },
        {
            path: "/graph/movie/:mid",
            name: "graph-movie",
            component: () => import("@/views/GraphView.vue"),
            props: (route) => ({ type: "movie", id: route.params.mid }),
        },
        {
            path: "/graph/person/:pid",
            name: "graph-person",
            component: () => import("@/views/GraphView.vue"),
            props: (route) => ({ type: "person", id: route.params.pid }),
        },
        {
            path: "/graph/path",
            name: "graph-path",
            component: () => import("@/views/PathView.vue"),
        },
        {
            path: "/stats",
            name: "stats",
            component: () => import("@/views/StatsView.vue"),
        },
        {
            path: "/login",
            name: "login",
            component: () => import("@/views/LoginView.vue"),
            meta: { hideLayout: false },
        },
        {
            path: "/register",
            name: "register",
            component: () => import("@/views/RegisterView.vue"),
        },
        {
            path: "/profile",
            name: "profile",
            component: () => import("@/views/ProfileView.vue"),
            meta: { requiresAuth: true },
        },
    ],
    scrollBehavior(to, from, savedPosition) {
        if (savedPosition) {
            return savedPosition;
        }
        return { top: 0 };
    },
});

// 路由守卫：需要登录的页面
router.beforeEach((to, from, next) => {
    if (to.meta.requiresAuth) {
        const token = localStorage.getItem("access_token");
        if (!token) {
            next({ name: "login", query: { redirect: to.fullPath } });
            return;
        }
    }
    next();
});

export default router;
