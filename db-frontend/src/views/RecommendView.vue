<script setup>
// 推荐页 — Phase 5 占位，功能待实现
</script>

<template>
    <div class="recommend-view">
        <div class="container page-padding">
            <div class="placeholder-card">
                <div class="placeholder-icon">🎯</div>
                <h1 class="placeholder-title">智能推荐</h1>
                <p class="placeholder-desc">
                    基于知识图谱的个性化电影推荐功能正在开发中，敬请期待...
                </p>
                <div class="placeholder-features">
                    <div class="feature-item">
                        <span class="feature-icon">🧠</span>
                        <span>基于协同过滤的推荐</span>
                    </div>
                    <div class="feature-item">
                        <span class="feature-icon">🔗</span>
                        <span>基于知识图谱的关联推荐</span>
                    </div>
                    <div class="feature-item">
                        <span class="feature-icon">⭐</span>
                        <span>基于用户偏好的个性化推荐</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped lang="scss">
.recommend-view {
    min-height: 60vh;
    display: flex;
    align-items: center;
    justify-content: center;
}

.placeholder-card {
    text-align: center;
    max-width: 520px;
    margin: 0 auto;
    padding: var(--space-2xl);
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
}

.placeholder-icon {
    font-size: 4rem;
    margin-bottom: var(--space-md);
}

.placeholder-title {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--space-sm);
}

.placeholder-desc {
    color: var(--text-muted);
    font-size: 0.95rem;
    margin-bottom: var(--space-xl);
}

.placeholder-features {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
    text-align: left;
}

.feature-item {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    color: var(--text-secondary);
    font-size: 0.9rem;
    padding: var(--space-sm) var(--space-md);
    background: var(--bg-main);
    border-radius: var(--radius-sm);
}

.feature-icon {
    font-size: 1.2rem;
}
</style>
