<script setup>
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ElMessage } from "element-plus";
import { User, Lock, Message, UserFilled } from "@element-plus/icons-vue";

const router = useRouter();
const authStore = useAuthStore();

const formRef = ref(null);
const loading = ref(false);

const form = reactive({
    username: "",
    password: "",
    confirmPassword: "",
    nickname: "",
    email: "",
});

const validateConfirmPassword = (rule, value, callback) => {
    if (value !== form.password) {
        callback(new Error("两次输入的密码不一致"));
    } else {
        callback();
    }
};

const rules = {
    username: [
        { required: true, message: "请输入用户名", trigger: "blur" },
        { min: 3, max: 50, message: "用户名 3-50 个字符", trigger: "blur" },
    ],
    password: [
        { required: true, message: "请输入密码", trigger: "blur" },
        { min: 6, max: 128, message: "密码 6-128 个字符", trigger: "blur" },
    ],
    confirmPassword: [
        { required: true, message: "请确认密码", trigger: "blur" },
        { validator: validateConfirmPassword, trigger: "blur" },
    ],
    nickname: [{ max: 50, message: "昵称最多 50 个字符", trigger: "blur" }],
    email: [
        { type: "email", message: "请输入有效的邮箱地址", trigger: "blur" },
        { max: 100, message: "邮箱最多 100 个字符", trigger: "blur" },
    ],
};

const handleRegister = async () => {
    const valid = await formRef.value.validate().catch(() => false);
    if (!valid) return;

    loading.value = true;
    try {
        await authStore.register({
            username: form.username,
            password: form.password,
            nickname: form.nickname || undefined,
            email: form.email || undefined,
        });
        ElMessage.success("注册成功，请登录");
        router.push("/login");
    } catch (err) {
        console.error("注册失败:", err);
    } finally {
        loading.value = false;
    }
};
</script>

<template>
    <div class="register-view">
        <div class="auth-card">
            <div class="auth-header">
                <h1 class="auth-title">注册</h1>
            </div>

            <el-form
                ref="formRef"
                :model="form"
                :rules="rules"
                label-position="top"
                @keyup.enter="handleRegister"
            >
                <el-form-item label="用户名" prop="username">
                    <el-input
                        v-model="form.username"
                        :prefix-icon="User"
                        placeholder="3-50 个字符"
                        size="large"
                    />
                </el-form-item>

                <el-form-item label="密码" prop="password">
                    <el-input
                        v-model="form.password"
                        :prefix-icon="Lock"
                        type="password"
                        placeholder="至少 6 个字符"
                        show-password
                        size="large"
                    />
                </el-form-item>

                <el-form-item label="确认密码" prop="confirmPassword">
                    <el-input
                        v-model="form.confirmPassword"
                        :prefix-icon="Lock"
                        type="password"
                        placeholder="再次输入密码"
                        show-password
                        size="large"
                    />
                </el-form-item>

                <el-form-item label="昵称（可选）" prop="nickname">
                    <el-input
                        v-model="form.nickname"
                        :prefix-icon="UserFilled"
                        placeholder="显示名称"
                        size="large"
                    />
                </el-form-item>

                <el-form-item label="邮箱（可选）" prop="email">
                    <el-input
                        v-model="form.email"
                        :prefix-icon="Message"
                        placeholder="example@email.com"
                        size="large"
                    />
                </el-form-item>

                <el-form-item>
                    <el-button
                        type="primary"
                        size="large"
                        :loading="loading"
                        class="register-btn"
                        @click="handleRegister"
                    >
                        注册
                    </el-button>
                </el-form-item>
            </el-form>

            <div class="auth-footer">
                已有账号？
                <router-link to="/login" class="auth-link"
                    >立即登录</router-link
                >
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.register-view {
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

.register-btn {
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
