<template>
    <footer class="app-footer">
        <div class="footer-inner container">
            <p>豆瓣电影知识图谱系统 &copy; {{ new Date().getFullYear() }}</p>
        </div>
    </footer>
</template>

<style scoped lang="scss">
.app-footer {
    border-top: 1px solid var(--border-color);
    padding: var(--space-lg) 0;
    margin-top: auto;
}

.footer-inner {
    text-align: center;
    color: var(--text-muted);
    font-size: 0.85rem;
}
</style>
