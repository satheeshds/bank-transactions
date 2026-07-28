<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import store from '../store.js'

const rules = ref([])
const loading = ref(true)
const count = computed(() => rules.value.length ? `${rules.value.length} rule${rules.value.length !== 1 ? 's' : ''}` : 'Loading...')
let interval = null

async function loadRules() {
    loading.value = true
    try {
        const res = await fetch('/api/rules')
        if (!res.ok) throw new Error('Rules API unavailable')
        rules.value = (await res.json()).rules
    } catch (e) { console.error('loadRules', e) }
    finally { loading.value = false }
}

async function confirmDelete(id) {
    if (!confirm('Delete this rule? This action cannot be undone.')) return
    try {
        const res = await fetch(`/api/v1/rules/${id}`, { method: 'DELETE' })
        if (!res.ok) throw new Error('Delete failed')
        await loadRules()
    } catch (e) {
        console.error('Failed to delete rule', e)
        alert('Failed to delete rule')
    }
}

watch(() => store.refreshTrigger, loadRules)
onMounted(() => { loadRules(); interval = setInterval(loadRules, 30000) })
onUnmounted(() => { if (interval) clearInterval(interval) })
</script>

<template>
    <div class="flex flex-col gap-lg">
        <div class="flex items-center justify-between">
            <div>
                <h2 class="font-headline-md text-headline-md text-primary">Parsing Rules</h2>
                <p class="font-body-md text-on-surface-variant mt-xs">Regex-based rules used to extract transaction data from bank alert emails.</p>
            </div>
            <div class="flex items-center gap-sm">
                <a href="#/parsing-rules/add" class="px-md py-sm bg-secondary text-white rounded">Add Rule</a>
                <span class="px-md py-sm bg-surface-container border border-outline-variant rounded-xl font-label-mono text-label-mono text-on-surface-variant">{{ count }}</span>
            </div>
        </div>

        <div class="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
            <table class="w-full text-left">
                <thead class="bg-surface-container-low border-b border-outline-variant">
                    <tr>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Rule Name</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Source</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Regex Pattern</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Type</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Card</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase text-right">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-if="loading && rules.length === 0">
                        <td colspan="6" class="px-lg py-md text-center text-on-surface-variant">Loading rules...</td>
                    </tr>
                    <tr v-else-if="rules.length === 0">
                        <td colspan="6" class="px-lg py-xl text-center text-on-surface-variant">
                            <div class="flex flex-col items-center gap-sm">
                                <span class="material-symbols-outlined text-[40px]">rule</span>
                                <p>No parsing rules found in the database. Use the 'Add Rule' button to create parsing rules via the UI.</p>
                            </div>
                        </td>
                    </tr>
                    <tr v-for="(rule, i) in rules" :key="rule.rule_name + i" class="hover:bg-surface-container-low transition-colors border-b border-outline-variant">
                        <td class="px-lg py-md">
                            <div class="flex items-center gap-sm">
                                <div class="w-7 h-7 bg-secondary-fixed rounded flex items-center justify-center text-on-secondary-fixed shrink-0">
                                    <span class="text-[11px] font-bold font-label-mono">{{ i + 1 }}</span>
                                </div>
                                <span class="font-body-md text-body-md font-bold">{{ rule.rule_name }}</span>
                            </div>
                        </td>
                        <td class="px-lg py-md">
                            <span class="font-caption text-caption text-on-surface-variant bg-surface-container px-sm py-xs rounded">{{ rule.source_name }}</span>
                        </td>
                        <td class="px-lg py-md">
                            <code class="font-label-mono text-[11px] text-on-surface-variant bg-surface-container px-sm py-xs rounded max-w-xs truncate block" :title="rule.regex || '-'">{{ rule.regex || '-' }}</code>
                        </td>
                        <td class="px-lg py-md">
                            <span :class="['px-sm py-1 rounded-full text-[10px] font-bold uppercase tracking-wider', rule.transaction_type === 'withdrawal' ? 'bg-error-container/30 text-on-error-container' : 'bg-on-tertiary-container/10 text-on-tertiary-container']">{{ rule.transaction_type || 'withdrawal' }}</span>
                        </td>
                        <td class="px-lg py-md font-label-mono text-label-mono text-on-surface-variant">{{ rule.card_last4 ? '···· ' + rule.card_last4 : '-' }}</td>
                        <td class="px-lg py-md text-right">
                            <div class="flex items-center gap-sm justify-end">
                                <a v-if="rule.id" :href="`#/parsing-rules/add?id=${rule.id}`" class="px-sm py-xs border rounded">Edit</a>
                                <button v-if="rule.id" @click="() => confirmDelete(rule.id)" class="px-sm py-xs bg-error-container/20 rounded">Delete</button>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="flex items-start gap-sm p-md bg-surface-container border border-outline-variant rounded-xl text-on-surface-variant">
            <span class="material-symbols-outlined text-sm shrink-0 mt-xs">info</span>
            <p class="font-body-md text-body-md">Parsing rules are stored in the application's database and can be added, edited, or deleted using the UI. Use the Add Rule button to create new rules; changes apply immediately.</p>
        </div>
    </div>
</template>
