<script setup>
import { ref, reactive } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ElMessage } from "element-plus";
import { User, Lock } from "@element-plus/icons-vue";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const formRef = ref(null);
const loading = ref(false);

const form = reactive({
    username: "",
    password: "",
});

const rules = {
    username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
    password: [
        { required: true, message: "请输入密码", trigger: "blur" },
        { min: 6, message: "密码至少 6 个字符", trigger: "blur" },
    ],
};

const handleLogin = async () => {
    const valid = await formRef.value.validate().catch(() => false);
    if (!valid) return;

    loading.value = true;
    try {
        await authStore.login({
            username: form.username,
            password: form.password,
        });
        ElMessage.success("登录成功");
        const redirect = route.query.redirect || "/";
        router.push(redirect);
    } catch (err) {
        // 全局拦截器已处理 ElMessage.error
        console.error("登录失败:", err);
    } finally {
        loading.value = false;
    }
};
</script>

<template>
    <div class="login-view">
        <div class="auth-card">
            <div class="auth-header">
                <h1 class="auth-title">登录</h1>
            </div>

            <el-form
                ref="formRef"
                :model="form"
                :rules="rules"
                label-position="top"
                @keyup.enter="handleLogin"
            >
                <el-form-item label="用户名" prop="username">
                    <el-input
                        v-model="form.username"
                        :prefix-icon="User"
                        placeholder="请输入用户名"
                        size="large"
                    />
                </el-form-item>

                <el-form-item label="密码" prop="password">
                    <el-input
                        v-model="form.password"
                        :prefix-icon="Lock"
                        type="password"
                        placeholder="请输入密码"
                        show-password
                        size="large"
                    />
                </el-form-item>

                <el-form-item>
                    <el-button
                        type="primary"
                        size="large"
                        :loading="loading"
                        class="login-btn"
                        @click="handleLogin"
                    >
                        登录
                    </el-button>
                </el-form-item>
            </el-form>

            <div class="auth-footer">
                还没有账号？
                <router-link to="/register" class="auth-link"
                    >立即注册</router-link
                >
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.login-view {
    min-height: calc(100vh - var(--header-height) - 80px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-xl) var(--space-lg);
}

.auth-card {
    width: 100%;
    max-width: 420px;
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--space-2xl) var(--space-xl);
    box-shadow: var(--shadow-lg);
    backdrop-filter: blur(20px);
}

.auth-header {
    text-align: center;
}

.auth-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-xs);
}

.login-btn {
    width: 100%;
    font-size: 1rem;
    font-weight: 600;
    height: 44px;
    border-radius: var(--radius-md);
}

.auth-footer {
    text-align: center;
    margin-top: var(--space-lg);
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.auth-link {
    color: var(--color-accent) !important;
    font-weight: 600;

    &:hover {
        text-decoration: underline;
    }
}

@media (max-width: 480px) {
    .auth-card {
        padding: var(--space-xl) var(--space-md);
    }
}
</style>
