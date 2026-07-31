<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import store from '../store.js'
import { formatRelativeTime } from '../utils.js'

const failed = ref([])
const loading = ref(true)
const countText = computed(() => failed.value.length > 0 ? `${failed.value.length} failed` : 'None')
const countClass = computed(() =>
    failed.value.length > 0
        ? 'px-md py-sm bg-error-container text-on-error-container border border-error/20 rounded-xl font-label-mono text-label-mono'
        : 'px-md py-sm bg-surface-container border border-outline-variant rounded-xl font-label-mono text-label-mono text-on-surface-variant'
)
let interval = null
const router = useRouter()

async function loadFailed() {
    loading.value = true
    try {
        const res = await fetch('/api/transactions?status=error')
        if (!res.ok) throw new Error('Transactions API unavailable')
        const data = await res.json()
        failed.value = data.transactions
            .filter(tx => tx.status === 'error')
            .map(tx => ({
                ...tx,
                formattedTime: formatRelativeTime(tx.timestamp),
                formattedAmount: tx.amount ? `${tx.currency || '\u20b9'} ${tx.amount.toFixed(2)}` : '-',
                errorMsg: tx.error_message || 'Parse error — check logs for details',
                ref: tx.reference_no ? `Ref: ${tx.reference_no}` : (tx.email_subject || 'Unknown Email'),
            }))
    } catch (e) { console.error('loadFailed', e) }
    finally { loading.value = false }
}

watch(() => store.refreshTrigger, loadFailed)
onMounted(() => { loadFailed(); interval = setInterval(loadFailed, 15000) })
onUnmounted(() => { if (interval) clearInterval(interval) })
</script>

<template>
    <div class="flex flex-col gap-lg">
        <div class="flex items-center justify-between">
            <div>
                <h2 class="font-headline-md text-headline-md text-primary">Failed Parses</h2>
                <p class="font-body-md text-on-surface-variant mt-xs">Transactions that could not be parsed or submitted to Firefly III.</p>
            </div>
            <span :class="countClass">{{ countText }}</span>
        </div>

        <div class="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
            <table class="w-full text-left">
                <thead class="bg-surface-container-low border-b border-outline-variant">
                    <tr>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Transaction</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Error</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Amount</th>
                        <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Time</th>
                    </tr>
                </thead>
                <tbody>
                    <tr v-if="loading && failed.length === 0">
                        <td colspan="4" class="px-lg py-md text-center text-on-surface-variant">Loading...</td>
                    </tr>
                    <tr v-else-if="failed.length === 0">
                        <td colspan="4" class="px-lg py-xl text-center text-on-surface-variant">
                            <div class="flex flex-col items-center gap-sm">
                                <span class="material-symbols-outlined text-[40px] text-on-tertiary-container">check_circle</span>
                                <p class="font-body-lg">No failed parses — all transactions processed successfully.</p>
                            </div>
                        </td>
                    </tr>
                    <tr v-for="tx in failed" :key="tx.id || tx.timestamp" @click="router.push(`/failed-parses/${tx.id || tx.timestamp}`)" class="cursor-pointer hover:bg-surface-container-low transition-colors border-b border-outline-variant">
                        <td class="px-lg py-md">
                            <div class="flex items-center gap-md">
                                <div class="w-8 h-8 bg-error-container/30 text-error rounded flex items-center justify-center shrink-0">
                                    <span class="material-symbols-outlined text-[18px]">help</span>
                                </div>
                                <div class="min-w-0">
                                    <p class="font-body-md text-body-md font-bold truncate" :title="tx.merchant">{{ tx.merchant || 'Unknown Merchant' }}</p>
                                    <p class="font-caption text-caption text-on-surface-variant truncate">{{ tx.ref }}</p>
                                    <p class="font-caption text-caption text-on-surface-variant truncate">Matched rule: {{ (tx.rule_name && tx.rule_name.trim() && tx.rule_name.trim().toLowerCase() !== 'unnamed rule') ? tx.rule_name.trim() : (tx.rule_id ? 'Unnamed Rule' : 'Unknown') }}</p>
                                </div>
                            </div>
                        </td>
                        <td class="px-lg py-md">
                            <p class="font-body-md text-error truncate max-w-xs" :title="tx.errorMsg">{{ tx.errorMsg }}</p>
                        </td>
                        <td class="px-lg py-md font-label-mono text-label-mono text-on-surface-variant">{{ tx.formattedAmount }}</td>
                        <td class="px-lg py-md font-caption text-caption text-on-surface-variant whitespace-nowrap">{{ tx.formattedTime }}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="flex items-start gap-sm p-md bg-error-container/20 border border-error/20 rounded-xl">
            <span class="material-symbols-outlined text-error shrink-0 mt-xs">warning</span>
            <p class="font-body-md text-body-md text-on-surface-variant">Failed parses are usually caused by unmatched regex patterns or missing fields. Check the <strong>Dashboard</strong> console logs for full error traces.</p>
        </div>
    </div>
</template>
