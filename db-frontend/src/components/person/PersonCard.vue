<script setup>
import { useRouter } from "vue-router";

const props = defineProps({
    person: {
        type: Object,
        required: true,
    },
    showRole: {
        type: Boolean,
        default: false,
    },
    clickable: {
        type: Boolean,
        default: true,
    },
});

const router = useRouter();

const goDetail = () => {
    if (props.clickable) {
        router.push(`/persons/${props.person.pid}`);
    }
};

const roleLabel = (role) => {
    const map = { director: "导演", actor: "演员" };
    return map[role] || role || "";
};
</script>

<template>
    <div class="person-card" :class="{ clickable }" @click="goDetail">
        <el-avatar :size="48" class="person-avatar">
            {{ person.name?.[0] || "?" }}
        </el-avatar>
        <div class="person-info">
            <span class="person-name">{{ person.name }}</span>
            <span v-if="showRole && person.role" class="person-role">{{
                roleLabel(person.role)
            }}</span>
            <span v-else-if="person.profession" class="person-role">{{
                person.profession
            }}</span>
            <span v-if="person.collaboration_count" class="person-collab">
                合作 {{ person.collaboration_count }} 次
            </span>
        </div>
    </div>
</template>

<style scoped lang="scss">
.person-card {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-md);
    transition: all var(--transition-fast);

    &.clickable {
        cursor: pointer;

        &:hover {
            background: var(--bg-card-hover);

            .person-name {
                color: var(--color-accent);
            }
        }
    }
}

.person-avatar {
    flex-shrink: 0;
    background: var(--bg-card);
    color: var(--color-accent);
    font-weight: 600;
    border: 1px solid var(--border-color);
}

.person-info {
    display: flex;
    flex-direction: column;
    min-width: 0;
}

.person-name {
    font-size: 0.95rem;
    font-weight: 500;
    color: var(--text-primary);
    transition: color var(--transition-fast);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.person-role {
    font-size: 0.8rem;
    color: var(--text-muted);
}

.person-collab {
    font-size: 0.75rem;
    color: var(--color-accent);
}
</style>
