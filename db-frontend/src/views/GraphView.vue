<template>
    <div class="graph-view container">
        <div class="page-placeholder">
            <h1 class="page-title">🕸️ 知识图谱</h1>
            <p class="placeholder-text">
                {{ type === "movie" ? "电影" : "影人" }} 关联图谱 — ID: {{ id }}
            </p>
            <p class="placeholder-note">Phase 3 实现</p>
        </div>
    </div>
</template>

<script setup>
defineProps({
    type: { type: String, required: true },
    id: { type: String, required: true },
});
</script>

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
