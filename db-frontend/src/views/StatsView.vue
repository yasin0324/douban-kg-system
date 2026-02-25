<template>
    <div class="stats-view container">
        <div class="page-placeholder">
            <h1 class="page-title">📊 统计看板</h1>
            <p class="placeholder-text">
                类型分布 / 年代分布 / 评分分布 / Top 演员 / Top 导演
            </p>
            <p class="placeholder-note">Phase 4 实现</p>
        </div>
    </div>
</template>

<style scoped lang="scss">
.page-placeholder {
    text-align: center;
    padding: var(--space-2xl) 0;
}
.placeholder-text {
    color: var(--text-secondary);
    font-size: 1.1rem;
    margin-bottom: var(--space-sm);
}
.placeholder-note {
    color: var(--text-muted);
    font-size: 0.85rem;
}
</style>
