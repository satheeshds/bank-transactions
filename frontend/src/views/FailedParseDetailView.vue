<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { formatRelativeTime } from '../utils.js'

const route = useRoute()
const tx = ref(null)
const loading = ref(true)

async function load() {
    loading.value = true
    try {
        const id = route.params.id
        const res = await fetch(`/api/transactions/${id}`)
        const data = await res.json()
        tx.value = data.transaction
        if (tx.value) {
            tx.value.formattedTime = formatRelativeTime(tx.value.timestamp)
            tx.value.formattedAmount = tx.value.amount ? `${tx.value.currency || '\u20b9'} ${tx.value.amount.toFixed(2)}` : '-'
        }
    } catch (e) { console.error('load tx', e) }
    finally { loading.value = false }
}

onMounted(load)
</script>

<template>
    <div class="p-lg">
        <div v-if="loading">Loading...</div>
        <div v-else-if="!tx">Transaction not found.</div>
        <div v-else class="space-y-md">
            <h2 class="font-headline-md">Failed Parse — Details</h2>
            <div class="grid grid-cols-2 gap-lg bg-surface-container-lowest p-md rounded-xl">
                <div>
                    <p class="font-label-mono text-label-mono">Merchant</p>
                    <p class="font-body-md font-bold">{{ tx.merchant || 'Unknown' }}</p>

                    <p class="mt-sm font-label-mono text-label-mono">Reference</p>
                    <p class="font-body-md">{{ tx.reference_no || tx.email_subject || '—' }}</p>

                    <p class="mt-sm font-label-mono text-label-mono">Amount</p>
                    <p class="font-body-md">{{ tx.formattedAmount }}</p>
                </div>
                <div>
                    <p class="font-label-mono text-label-mono">Time</p>
                    <p class="font-body-md">{{ tx.formattedTime }}</p>

                    <p class="mt-sm font-label-mono text-label-mono">Status</p>
                    <p class="font-body-md">{{ tx.status }}</p>

                    <p class="mt-sm font-label-mono text-label-mono">Matched Rule</p>
                    <p class="font-body-md">{{ tx.rule_name || 'Unknown / Not recorded' }}</p>
                </div>
            </div>

            <div class="bg-surface-container p-md rounded-xl">
                <h3 class="font-body-md">Error</h3>
                <pre class="whitespace-pre-wrap">{{ tx.error_message || 'No error message recorded' }}</pre>
            </div>

            <div class="bg-surface-container p-md rounded-xl">
                <h3 class="font-body-md">Raw Email</h3>
                <p class="font-label-mono text-label-mono">Subject</p>
                <p>{{ tx.email_subject || '—' }}</p>
                <p class="font-label-mono text-label-mono mt-sm">Source</p>
                <p>{{ tx.source_name || '—' }}</p>
            </div>
        </div>
    </div>
</template>
