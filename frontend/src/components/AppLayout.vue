<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import store from '../store.js'

const route = useRoute()
const refreshKey = ref(0)

const NAV_ITEMS = [
    { to: '/dashboard',          icon: 'dashboard',       label: 'Dashboard' },
    { to: '/mailboxes',          icon: 'mail',            label: 'Mailboxes' },
    { to: '/parsing-rules',      icon: 'rule',            label: 'Parsing Rules' },
    { to: '/failed-parses',      icon: 'error',           label: 'Failed Parses' },
    { to: '/firefly-connection', icon: 'account_balance', label: 'Firefly Connection' },
    { to: '/settings',           icon: 'settings',        label: 'Settings' },
]

const pageTitle = computed(() => route.meta?.title || '')
const syncBadgeText = computed(() => store.isRunning ? 'Syncing' : 'Idle')
const syncBadgeClass = computed(() =>
    store.isRunning
        ? 'px-sm py-1 bg-secondary-fixed text-on-secondary-fixed rounded-full text-[10px] font-bold uppercase tracking-wider'
        : 'px-sm py-1 bg-on-tertiary-container/10 text-on-tertiary-container rounded-full text-[10px] font-bold uppercase tracking-wider'
)

function refresh() { store.refreshTrigger++ }
</script>

<template>
    <aside class="h-screen w-64 fixed left-0 top-0 bg-surface-container-lowest border-r border-outline-variant flex flex-col py-lg px-md z-50">
        <div class="mb-xl px-sm">
            <h1 class="font-headline-md text-headline-md text-primary tracking-tight">Mail2Firefly</h1>
            <p class="font-caption text-caption text-on-surface-variant">Firefly III Connector</p>
        </div>
        <nav class="flex-1 space-y-xs">
            <RouterLink
                v-for="item in NAV_ITEMS" :key="item.to" :to="item.to"
                class="flex items-center gap-md px-md py-sm transition-colors hover:bg-surface-container-high cursor-pointer"
                :class="route.path === item.to ? 'text-secondary font-bold border-r-2 border-secondary' : 'text-on-surface-variant'"
            >
                <span class="material-symbols-outlined">{{ item.icon }}</span>
                <span class="font-body-md text-body-md">{{ item.label }}</span>
            </RouterLink>
        </nav>
        <div class="mt-auto px-sm pt-md border-t border-outline-variant">
            <p class="text-[11px] font-label-mono text-on-surface-variant uppercase">Local Server</p>
            <p class="text-xs font-semibold text-primary">127.0.0.1:8000</p>
        </div>
    </aside>

    <header class="flex justify-between items-center w-full px-lg py-sm ml-64 max-w-[calc(100%-16rem)] bg-surface border-b border-outline-variant top-0 sticky z-40">
        <span class="font-headline-md text-headline-md font-bold text-primary">{{ pageTitle }}</span>
        <div class="flex items-center gap-sm text-on-surface-variant">
            <button class="p-xs hover:bg-surface-container-low rounded-lg transition-all" @click="refresh">
                <span class="material-symbols-outlined">refresh</span>
            </button>
            <div class="h-6 w-[1px] bg-outline-variant mx-xs"></div>
            <span :class="syncBadgeClass">{{ syncBadgeText }}</span>
        </div>
    </header>

    <main class="ml-64 p-lg max-w-container-max mx-auto">
        <RouterView :key="refreshKey" />
    </main>
</template>
