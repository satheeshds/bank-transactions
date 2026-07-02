<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import store from '../store.js'

const loading = ref(true)
const mailbox = reactive({ host: '-', username: '-', connected: false, error: null })
const sources = ref([])
let interval = null

async function loadSources() {
    loading.value = true
    try {
        const [statusRes, rulesRes] = await Promise.all([fetch('/api/status'), fetch('/api/rules')])
        if (statusRes.ok) {
            const { imap } = await statusRes.json()
            mailbox.host = imap.host || 'Not configured'
            mailbox.username = imap.username || '-'
            mailbox.connected = imap.connected
            mailbox.error = imap.error
        }
        if (rulesRes.ok) {
            const counts = {}
            for (const rule of (await rulesRes.json()).rules) {
                const n = rule.source_name || 'Unnamed'
                counts[n] = (counts[n] || 0) + 1
            }
            sources.value = Object.entries(counts).map(([name, ruleCount]) => ({ name, ruleCount }))
        }
    } catch (e) { console.error('loadSources', e) }
    finally { loading.value = false }
}

watch(() => store.refreshTrigger, loadSources)
onMounted(() => { loadSources(); interval = setInterval(loadSources, 15000) })
onUnmounted(() => { if (interval) clearInterval(interval) })
</script>

<template>
    <div class="flex flex-col gap-lg">
        <div>
            <h2 class="font-headline-md text-headline-md text-primary">Email Sources</h2>
            <p class="font-body-md text-on-surface-variant mt-xs">Configured IMAP mailbox and bank email source definitions.</p>
        </div>

        <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
            <h3 class="font-headline-sm text-headline-sm mb-md flex items-center gap-sm">
                <span class="material-symbols-outlined text-secondary">mail</span>
                Mailbox Connection
            </h3>
            <div class="flex items-start justify-between mb-md">
                <div class="flex items-center gap-md">
                    <div :class="['w-10 h-10 rounded-lg flex items-center justify-center', mailbox.connected ? 'bg-surface-container-low text-on-tertiary-container' : 'bg-error-container/20 text-error']">
                        <span class="material-symbols-outlined">dns</span>
                    </div>
                    <div>
                        <p class="font-headline-sm text-headline-sm">IMAP Mailbox</p>
                        <p class="font-caption text-caption text-on-surface-variant">{{ mailbox.host }}</p>
                    </div>
                </div>
                <span :class="['px-sm py-1 rounded-full text-[10px] font-bold uppercase tracking-wider', mailbox.connected ? 'bg-on-tertiary-container/10 text-on-tertiary-container' : 'bg-error-container text-on-error-container']">
                    {{ mailbox.connected ? 'Connected' : 'Offline' }}
                </span>
            </div>
            <div class="grid grid-cols-2 gap-md mt-md pt-md border-t border-outline-variant">
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Host</p>
                    <p class="font-label-mono text-label-mono text-primary truncate">{{ mailbox.host }}</p>
                </div>
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Port</p>
                    <p class="font-label-mono text-label-mono text-primary">993 (IMAPS)</p>
                </div>
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Username</p>
                    <p class="font-label-mono text-label-mono text-primary truncate">{{ mailbox.username }}</p>
                </div>
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Status</p>
                    <p :class="['font-label-mono text-label-mono', mailbox.connected ? 'text-on-tertiary-container' : 'text-error']">
                        {{ mailbox.connected ? 'Reachable' : (mailbox.error || 'Unreachable') }}
                    </p>
                </div>
            </div>
        </div>

        <div>
            <h3 class="font-headline-sm text-headline-sm mb-md">Source Definitions</h3>
            <p v-if="loading && sources.length === 0" class="text-on-surface-variant text-sm py-lg text-center">Loading...</p>
            <div v-else-if="sources.length === 0" class="flex flex-col items-center justify-center py-xl text-on-surface-variant gap-sm">
                <span class="material-symbols-outlined text-[48px]">inbox</span>
                <p class="font-body-lg">No email sources configured in config.toml</p>
            </div>
            <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-lg">
                <div v-for="src in sources" :key="src.name" class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex flex-col gap-md hover:border-secondary transition-colors">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-md">
                            <div class="w-10 h-10 bg-secondary-fixed rounded-lg flex items-center justify-center text-on-secondary-fixed">
                                <span class="material-symbols-outlined">mark_email_read</span>
                            </div>
                            <div>
                                <p class="font-headline-sm text-headline-sm">{{ src.name }}</p>
                                <p class="font-caption text-caption text-on-surface-variant">Email source definition</p>
                            </div>
                        </div>
                        <span class="px-sm py-1 bg-on-tertiary-container/10 text-on-tertiary-container rounded-full text-[10px] font-bold uppercase tracking-wider">Active</span>
                    </div>
                    <div class="flex items-center gap-sm pt-sm border-t border-outline-variant text-on-surface-variant">
                        <span class="material-symbols-outlined text-sm">rule</span>
                        <span class="font-caption text-caption">{{ src.ruleCount }} parsing rule{{ src.ruleCount !== 1 ? 's' : '' }}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
