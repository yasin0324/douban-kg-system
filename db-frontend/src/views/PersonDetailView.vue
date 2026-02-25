<template>
    <div class="person-detail-view container">
        <div class="page-placeholder">
            <h1 class="page-title">🧑 影人详情</h1>
            <p class="placeholder-text">影人 ID: {{ pid }}</p>
            <p class="placeholder-note">Phase 2 实现</p>
        </div>
    </div>
</template>

<script setup>
defineProps({
    pid: { type: String, required: true },
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
