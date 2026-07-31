<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import store from '../store.js'
import { formatRelativeTime, getMerchantIcon } from '../utils.js'

const hero = reactive({
    title: 'Loading...',
    desc: 'Loading dashboard data...',
    lastSyncTime: '-',
    latency: '-',
    latencyError: false,
    dotClass: 'w-2.5 h-2.5 rounded-full bg-on-tertiary-container animate-pulse',
    statusText: 'System Status: Active',
})
const stats = reactive({ runs: '-', parsed: '-', errors: '-' })
const imap = reactive({ badge: 'Checking...', ok: null, detail: '-' })
const ff = reactive({ badge: 'Checking...', ok: null, detail: '-' })
const syncBtn = reactive({ disabled: false, label: 'Sync Now', spinning: false })

const transactions = ref([])
const router = useRouter()

function onRowClick(tx) {
    if (!tx) return
    if (tx.status === 'error') {
        router.push(`/failed-parses/${tx.id || tx.timestamp}`)
    }
}
const rules = ref([])
const logs = ref('System console initialized. Click "Sync Now" to trigger a run.')

let intervals = []
let syncPollInterval = null

const latencyClass = computed(() =>
    hero.latencyError
        ? 'font-headline-sm text-headline-sm text-error'
        : 'font-headline-sm text-headline-sm text-on-tertiary-container'
)
const badgeOf = (ok) =>
    ok === true
        ? 'px-sm py-0.5 rounded text-[10px] font-bold uppercase bg-on-tertiary-container/10 text-on-tertiary-container'
        : ok === false
            ? 'px-sm py-0.5 rounded text-[10px] font-bold uppercase bg-error-container text-on-error-container'
            : 'px-sm py-0.5 rounded text-[10px] font-bold uppercase bg-surface-container text-on-surface-variant'
const imapBadgeClass = computed(() => badgeOf(imap.ok))
const ffBadgeClass = computed(() => badgeOf(ff.ok))

async function loadLogs() {
    try {
        const res = await fetch('/api/logs')
        if (!res.ok) return
        const data = await res.json()
        if (data.logs.length === 0) { logs.value = 'No logs in database yet.'; return }
        logs.value = data.logs.map(l => {
            const t = new Date(l.timestamp).toLocaleTimeString()
            return `[${t}] [${l.level}] ${l.message}`
        }).join('\n')
    } catch (e) { console.error('loadLogs', e) }
}

async function loadTransactions() {
    try {
        const res = await fetch('/api/transactions')
        if (!res.ok) return
        const data = await res.json()
        transactions.value = data.transactions.map(tx => ({
            ...tx,
            icon: getMerchantIcon(tx.merchant, tx.status),
            formattedAmount: tx.amount ? `${tx.currency || '\u20b9'} ${tx.amount.toFixed(2)}` : '-',
            formattedTime: formatRelativeTime(tx.timestamp),
            description: tx.reference_no ? `Ref: ${tx.reference_no}` : (tx.email_subject || 'Transaction Email'),
            rowIconClass: tx.status === 'error' ? 'bg-error-container/20 text-error' : 'bg-surface-container text-on-surface-variant',
            badgeClass: tx.status === 'synced'
                ? 'bg-on-tertiary-container/10 text-on-tertiary-container'
                : tx.status === 'error'
                    ? 'bg-error-container text-on-error-container'
                    : 'bg-secondary-fixed text-on-secondary-fixed',
        }))
    } catch (e) { console.error('loadTransactions', e) }
}

async function loadRules() {
    try {
        const res = await fetch('/api/rules')
        if (!res.ok) return
        rules.value = (await res.json()).rules
    } catch (e) { console.error('loadRules', e) }
}

async function refreshStatus() {
    try {
        const res = await fetch('/api/status')
        if (!res.ok) return
        const data = await res.json()

        store.isRunning = data.is_running

        if (data.is_running) {
            hero.dotClass = 'w-2.5 h-2.5 rounded-full bg-secondary animate-pulse'
            hero.statusText = 'System Status: Syncing...'
            hero.title = 'Syncing Inbox...'
            hero.desc = 'Fetching new bank statements from IMAP and uploading transactions to Firefly III.'
            syncBtn.disabled = true; syncBtn.label = 'Syncing...'; syncBtn.spinning = true
            if (!syncPollInterval) {
                syncPollInterval = setInterval(() => { loadLogs(); loadTransactions() }, 1000)
            }
        } else {
            hero.dotClass = 'w-2.5 h-2.5 rounded-full bg-on-tertiary-container'
            hero.statusText = 'System Status: Active'
            syncBtn.disabled = false; syncBtn.label = 'Sync Now'; syncBtn.spinning = false
            if (syncPollInterval) { clearInterval(syncPollInterval); syncPollInterval = null; loadLogs(); loadTransactions() }

            if (data.latest_run) {
                const r = data.latest_run
                const d = formatRelativeTime(r.end_time || r.start_time)
                if (r.status === 'success') {
                    hero.title = 'Everything is Synced'
                    hero.desc = `Last sync was successful (${d}). Synced ${r.parsed_count} transactions with ${r.error_count} warnings.`
                } else if (r.status === 'failed') {
                    hero.title = 'Last Sync Failed'
                    hero.desc = `An error occurred during the last run (${d}). Review the console logs below.`
                }
            } else {
                hero.title = 'Welcome to Mail2Firefly'
                hero.desc = 'Connect your IMAP mailbox and Firefly III. Trigger a manual sync to parse transactions.'
            }
        }

        hero.lastSyncTime = data.latest_run ? formatRelativeTime(data.latest_run.end_time || data.latest_run.start_time) : 'Never'
        hero.latency = data.firefly.connected ? `${data.firefly.latency_ms}ms` : 'Offline'
        hero.latencyError = !data.firefly.connected
        stats.runs = String(data.stats.total_runs_today).padStart(2, '0')
        stats.parsed = String(data.stats.parsed_today).padStart(2, '0')
        stats.errors = String(data.stats.errors_today).padStart(2, '0')
        imap.badge = data.imap.connected ? 'Connected' : 'Offline'
        imap.ok = data.imap.connected
        // Build a human-friendly detail string from DB mailboxes
        const mboxes = Array.isArray(data.imap.mailboxes) ? data.imap.mailboxes : []
        let detail = data.imap.error || 'Configuration error'
        if (mboxes.length > 0) {
            // prefer a connected mailbox
            const preferred = mboxes.find(m => m.connected) || mboxes[0]
            const name = preferred.name || 'Mailbox'
            const user = preferred.username || '-'
            const host = preferred.host || '-'
            detail = `${name}: ${user}@${host}`
        }
        imap.detail = detail
        ff.badge = data.firefly.connected ? 'Active' : 'Offline'
        ff.ok = data.firefly.connected
        ff.detail = data.firefly.connected ? data.firefly.base_url : (data.firefly.error || 'Configuration error')
    } catch (e) { console.error('refreshStatus', e) }
}

async function triggerSync() {
    if (store.isRunning) return
    syncBtn.disabled = true; syncBtn.label = 'Starting...'
    try {
        const res = await fetch('/api/sync', { method: 'POST' })
        const data = await res.json()
        if (res.ok) {
            logs.value += `\n>> Sync triggered manually. Run ID: ${data.run_id}\n`
            refreshStatus()
        } else {
            alert(`Failed to start sync: ${data.message || data.error}`)
            refreshStatus()
        }
    } catch (e) { alert('Connection error starting sync process.'); refreshStatus() }
}

function clearLogs() { logs.value = 'Console buffer cleared.' }
function refreshData() { refreshStatus(); loadTransactions(); loadRules(); loadLogs() }

watch(() => store.refreshTrigger, refreshData)

onMounted(() => {
    refreshData()
    intervals.push(setInterval(refreshStatus, 5000))
    intervals.push(setInterval(loadTransactions, 10000))
})
onUnmounted(() => {
    intervals.forEach(clearInterval); intervals = []
    if (syncPollInterval) { clearInterval(syncPollInterval); syncPollInterval = null }
    store.isRunning = false
})
</script>

<template>
    <div class="grid grid-cols-12 gap-lg">
        <!-- Hero Status Card -->
        <section class="col-span-12 lg:col-span-8 bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex flex-col justify-between relative overflow-hidden group">
            <div class="z-10">
                <div class="flex items-center gap-sm mb-xs">
                    <span :class="hero.dotClass"></span>
                    <span class="font-label-mono text-label-mono text-on-tertiary-container uppercase tracking-widest">{{ hero.statusText }}</span>
                </div>
                <h2 class="font-display-lg text-display-lg text-primary mt-sm">{{ hero.title }}</h2>
                <p class="font-body-lg text-body-lg text-on-surface-variant max-w-md mt-md">{{ hero.desc }}</p>
            </div>
            <div class="mt-xl flex items-center gap-lg z-10">
                <div class="flex flex-col">
                    <span class="font-caption text-caption text-on-surface-variant uppercase">Last Sync Run</span>
                    <span class="font-headline-sm text-headline-sm text-primary">{{ hero.lastSyncTime }}</span>
                </div>
                <div class="w-[1px] h-10 bg-outline-variant"></div>
                <div class="flex flex-col">
                    <span class="font-caption text-caption text-on-surface-variant uppercase">Firefly III Latency</span>
                    <span :class="latencyClass">{{ hero.latency }}</span>
                </div>
            </div>
            <div class="absolute -right-12 -top-12 w-64 h-64 bg-secondary-fixed opacity-10 rounded-full blur-3xl pointer-events-none group-hover:scale-110 transition-transform duration-700"></div>
        </section>

        <!-- Sync Now CTA -->
        <section class="col-span-12 lg:col-span-4 bg-primary text-on-primary rounded-xl p-lg flex flex-col items-center justify-center text-center border border-primary relative overflow-hidden">
            <div class="relative z-10 w-full">
                <span class="material-symbols-outlined text-[48px] mb-md text-secondary-fixed" :class="{ 'animate-spin': syncBtn.spinning }" style="font-variation-settings: 'FILL' 1;">cloud_sync</span>
                <h3 class="font-headline-md text-headline-md mb-sm">Manual Trigger</h3>
                <p class="font-body-md text-on-primary-container mb-lg">Bypass the scheduler and force a direct fetch from all IMAP sources.</p>
                <button :disabled="syncBtn.disabled" @click="triggerSync" class="w-full bg-on-primary text-primary py-md px-xl rounded-xl font-body-lg font-bold hover:bg-secondary-fixed transition-colors flex items-center justify-center gap-md disabled:opacity-60 disabled:cursor-not-allowed">
                    <span>{{ syncBtn.label }}</span>
                    <span class="material-symbols-outlined">arrow_forward</span>
                </button>
            </div>
            <div class="absolute inset-0 opacity-20 pointer-events-none" style="background-image: radial-gradient(circle at 2px 2px, white 1px, transparent 0); background-size: 24px 24px;"></div>
        </section>

        <!-- Stats Row -->
        <div class="col-span-12 grid grid-cols-1 md:grid-cols-3 gap-lg">
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex items-center justify-between">
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Sync Runs Today</p>
                    <p class="font-display-lg text-display-lg text-primary">{{ stats.runs }}</p>
                </div>
                <div class="w-12 h-12 bg-surface-container-low rounded-lg flex items-center justify-center text-secondary">
                    <span class="material-symbols-outlined">sync</span>
                </div>
            </div>
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex items-center justify-between">
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Parsed Today</p>
                    <p class="font-display-lg text-display-lg text-primary">{{ stats.parsed }}</p>
                </div>
                <div class="w-12 h-12 bg-surface-container-low rounded-lg flex items-center justify-center text-on-tertiary-container">
                    <span class="material-symbols-outlined">check_circle</span>
                </div>
            </div>
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex items-center justify-between border-l-4 border-l-error">
                <div>
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Errors Today</p>
                    <p class="font-display-lg text-display-lg text-error">{{ stats.errors }}</p>
                </div>
                <div class="w-12 h-12 bg-error-container rounded-lg flex items-center justify-center text-error">
                    <span class="material-symbols-outlined">error</span>
                </div>
            </div>
        </div>

        <!-- Recent Activity Table -->
        <section class="col-span-12 lg:col-span-8 bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden flex flex-col">
            <div class="p-lg border-b border-outline-variant">
                <h3 class="font-headline-sm text-headline-sm">Recent Activity</h3>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left">
                    <thead class="bg-surface-container-low">
                        <tr>
                            <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Transaction</th>
                            <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Amount</th>
                            <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Status</th>
                            <th class="px-lg py-sm font-label-mono text-label-mono text-on-surface-variant uppercase">Time</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-outline-variant">
                        <tr v-if="transactions.length === 0">
                            <td colspan="4" class="px-lg py-md text-center text-on-surface-variant">No recent transactions recorded.</td>
                        </tr>
                        <tr v-for="tx in transactions" :key="tx.id || tx.timestamp" :class="['hover:bg-surface-container-low transition-colors', tx.status === 'error' ? 'cursor-pointer' : '']" :role="tx.status === 'error' ? 'link' : null" :tabindex="tx.status === 'error' ? 0 : -1" @click="tx.status === 'error' && onRowClick(tx)" @keydown.enter.prevent="tx.status === 'error' && onRowClick(tx)" @keydown.space.prevent="tx.status === 'error' && onRowClick(tx)">
                            <td class="px-lg py-md">
                                <div class="flex items-center gap-md">
                                    <div :class="['w-8 h-8 rounded flex items-center justify-center', tx.rowIconClass]">
                                        <span class="material-symbols-outlined text-[18px]">{{ tx.icon }}</span>
                                    </div>
                                    <div>
                                        <p class="font-body-md text-body-md font-bold truncate max-w-[200px]" :title="tx.merchant">{{ tx.merchant || 'Unknown Merchant' }}</p>
                                        <p class="font-caption text-caption text-on-surface-variant truncate max-w-[200px]">{{ tx.description }}</p>
                                    </div>
                                </div>
                            </td>
                            <td class="px-lg py-md font-label-mono text-primary">{{ tx.formattedAmount }}</td>
                            <td class="px-lg py-md">
                                <span :class="['px-sm py-1 rounded-full text-[10px] font-bold uppercase tracking-wider', tx.badgeClass]">{{ tx.status }}</span>
                            </td>
                            <td class="px-lg py-md font-caption text-caption text-on-surface-variant">{{ tx.formattedTime }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Rules & Connectivity -->
        <section class="col-span-12 lg:col-span-4 flex flex-col gap-lg">
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex flex-col">
                <h3 class="font-headline-sm text-headline-sm mb-md">Parsing Rules</h3>
                <div class="space-y-md flex-1">
                    <p v-if="rules.length === 0" class="text-on-surface-variant text-sm">Loading rules...</p>
                    <div v-for="rule in rules" :key="rule.rule_name" class="flex items-center justify-between p-sm hover:bg-surface-container-low rounded border border-transparent hover:border-outline-variant transition-all">
                        <div class="flex items-center gap-sm overflow-hidden">
                            <span class="material-symbols-outlined text-secondary shrink-0">rule</span>
                            <div class="truncate">
                                <p class="font-body-md text-body-md font-bold truncate">{{ rule.rule_name }}</p>
                                <p class="text-[11px] font-label-mono text-on-surface-variant truncate">{{ rule.source_name }}</p>
                            </div>
                        </div>
                        <span class="material-symbols-outlined text-on-surface-variant shrink-0">chevron_right</span>
                    </div>
                </div>
            </div>
            <div class="bg-surface-container-high rounded-xl p-lg border border-outline-variant">
                <h4 class="font-label-mono text-label-mono text-on-surface-variant uppercase mb-md">System Connections</h4>
                <div class="space-y-sm">
                    <div class="flex items-center justify-between text-body-md">
                        <span class="flex items-center gap-sm">
                            <span class="material-symbols-outlined text-sm">mail</span>
                            <span>Mailbox Connection</span>
                        </span>
                        <span :class="imapBadgeClass">{{ imap.badge }}</span>
                    </div>
                    <div class="text-[11px] font-label-mono text-on-surface-variant truncate">{{ imap.detail }}</div>
                    <div class="h-[1px] bg-outline-variant my-md"></div>
                    <div class="flex items-center justify-between text-body-md">
                        <span class="flex items-center gap-sm">
                            <span class="material-symbols-outlined text-sm">account_balance</span>
                            <span>Firefly III API</span>
                        </span>
                        <span :class="ffBadgeClass">{{ ff.badge }}</span>
                    </div>
                    <div class="text-[11px] font-label-mono text-on-surface-variant truncate">{{ ff.detail }}</div>
                </div>
            </div>
        </section>

        <!-- Sync Console -->
        <section class="col-span-12 bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex flex-col">
            <div class="flex items-center justify-between mb-md border-b border-outline-variant pb-xs">
                <h3 class="font-headline-sm text-headline-sm flex items-center gap-sm">
                    <span class="material-symbols-outlined">terminal</span>
                    Sync Console Logs
                </h3>
                <button @click="clearLogs" class="text-on-surface-variant hover:text-primary font-body-md font-bold transition-colors">Clear view</button>
            </div>
            <pre class="bg-primary text-[#56da7c] font-label-mono text-[12px] p-md rounded-lg h-56 overflow-y-auto custom-scrollbar whitespace-pre-wrap leading-relaxed shadow-inner">{{ logs }}</pre>
        </section>
    </div>
</template>
