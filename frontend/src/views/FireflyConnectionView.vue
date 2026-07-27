<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import store from '../store.js'

const conn = reactive({ connected: false, latency: null, baseUrl: '-', error: null })
const loading = ref(true)
const testing = ref(false)
const editing = ref(false)
const form = reactive({ base_url: '', token: '', timeout: '', custom_keys: {} })
const _newKey = ref('')
const _newVal = ref('')

function addCustomKey() {
    if (!_newKey.value) return
    const copy = { ...(form.custom_keys || {}) }
    copy[_newKey.value] = _newVal.value || ''
    form.custom_keys = copy
    _newKey.value = ''
    _newVal.value = ''
}
function removeCustomKey(key) {
    const copy = { ...(form.custom_keys || {}) }
    delete copy[key]
    form.custom_keys = copy
}
let interval = null

async function loadStatus() {
    loading.value = true
    try {
        const res = await fetch('/api/status')
        if (!res.ok) throw new Error('Status API unavailable')
        const { firefly } = await res.json()
        conn.connected = firefly.connected
        conn.latency = firefly.latency_ms
        conn.baseUrl = firefly.base_url || 'Not configured'
        conn.error = firefly.error
    } catch (e) { console.error('loadStatus', e) }
    finally { loading.value = false }
}

async function testConnection() {
    testing.value = true
    await loadStatus()
    testing.value = false
}

async function loadFireflyConfig() {
    try {
        const res = await fetch('/api/v1/firefly')
        if (!res.ok) throw new Error('Failed to load')
        const j = await res.json()
        form.base_url = j.base_url || ''
        form.token = j.token || ''
        form.timeout = j.timeout || ''
        form.custom_keys = j.custom_keys || {}
    } catch (e) { console.error('loadFireflyConfig', e) }
}

async function saveFireflyConfig() {
    try {
        const payload = { base_url: form.base_url || null, token: form.token || null, timeout: form.timeout ? parseInt(form.timeout) : null, custom_keys: form.custom_keys || {} }
        const res = await fetch('/api/v1/firefly', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        if (!res.ok) throw new Error('Save failed')
        editing.value = false
        await loadStatus()
        await loadFireflyConfig()
    } catch (e) { console.error('saveFireflyConfig', e) }
}

watch(() => store.refreshTrigger, loadStatus)
onMounted(() => { loadStatus(); interval = setInterval(loadStatus, 30000) })
onUnmounted(() => { if (interval) clearInterval(interval) })
</script>

<template>
    <div class="flex flex-col gap-lg">
        <div class="flex items-center justify-between">
            <div>
                <h2 class="font-headline-md text-headline-md text-primary">Firefly Connection</h2>
                <p class="font-body-md text-on-surface-variant mt-xs">Firefly III API connectivity status and configuration details.</p>
            </div>
            <button @click="testConnection" :disabled="testing" class="flex items-center gap-sm px-md py-sm bg-secondary text-on-secondary rounded-xl font-body-md font-bold hover:bg-secondary-container transition-colors disabled:opacity-60">
                <span class="material-symbols-outlined text-sm" :class="{ 'animate-spin': testing }">network_check</span>
                {{ testing ? 'Testing...' : 'Test Connection' }}
            </button>
        </div>

        <div v-if="loading && conn.baseUrl === '-'" class="text-on-surface-variant text-sm py-lg text-center">Loading connection details...</div>
        <template v-else>
            <!-- Status Hero -->
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex items-start justify-between relative overflow-hidden">
                <div class="z-10">
                    <div class="flex items-center gap-sm mb-sm">
                        <span :class="['w-3 h-3 rounded-full', conn.connected ? 'bg-on-tertiary-container' : 'bg-error animate-pulse']"></span>
                        <span :class="['font-label-mono text-label-mono uppercase tracking-widest', conn.connected ? 'text-on-tertiary-container' : 'text-error']">
                            {{ conn.connected ? 'Connected' : 'Offline' }}
                        </span>
                    </div>
                    <h3 class="font-headline-md text-headline-md text-primary">Firefly III API</h3>
                    <p class="font-body-md text-on-surface-variant mt-xs max-w-md">
                        {{ conn.connected ? 'API is reachable and responding. Token authentication successful.' : ('Cannot reach the Firefly III API. ' + (conn.error || 'Check your configuration.')) }}
                    </p>
                </div>
                <span :class="['px-sm py-1 rounded-full text-[10px] font-bold uppercase tracking-wider shrink-0 mt-xs', conn.connected ? 'bg-on-tertiary-container/10 text-on-tertiary-container' : 'bg-error-container text-on-error-container']">
                    {{ conn.connected ? 'Active' : 'Offline' }}
                </span>
                <div class="absolute -right-12 -top-12 w-48 h-48 bg-secondary-fixed opacity-10 rounded-full blur-3xl pointer-events-none"></div>
            </div>

            <!-- Metrics -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-lg">
                <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Latency</p>
                    <p :class="['font-display-lg text-display-lg', conn.connected ? 'text-on-tertiary-container' : 'text-error']">{{ conn.connected ? conn.latency + 'ms' : 'N/A' }}</p>
                    <p class="font-caption text-caption text-on-surface-variant mt-xs">Round-trip to /api/v1/about</p>
                </div>
                <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg md:col-span-2">
                    <p class="font-caption text-caption text-on-surface-variant uppercase mb-xs">Base URL</p>
                    <p class="font-label-mono text-label-mono text-primary break-all">{{ conn.baseUrl }}</p>
                    <p class="font-caption text-caption text-on-surface-variant mt-xs">Configured in config.toml → [firefly] base_url</p>
                </div>
            </div>

            <!-- Config Reference -->
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
                <h4 class="font-headline-sm text-headline-sm mb-md">Configuration</h4>
                <div class="mb-md">
                    <button @click="() => { editing = !editing; if(editing) loadFireflyConfig() }" class="px-sm py-xs bg-secondary text-on-secondary rounded">{{ editing ? 'Cancel' : 'Edit' }}</button>
                </div>
                <div v-if="editing" class="mb-md">
                    <div class="space-y-sm">
                        <label class="font-body-sm">Base URL</label>
                        <input v-model="form.base_url" class="w-full p-sm border rounded" />
                        <label class="font-body-sm">API Token</label>
                        <input v-model="form.token" class="w-full p-sm border rounded" />
                        <label class="font-body-sm">Timeout (s)</label>
                        <input v-model="form.timeout" class="w-24 p-sm border rounded" />
                        <div class="mt-sm">
                            <button @click="saveFireflyConfig" class="px-md py-sm bg-primary text-on-primary rounded">Save</button>
                        </div>
                    </div>
                </div>
                <div v-if="editing" class="mb-md">
                    <h4 class="font-headline-sm">Custom Keys</h4>
                    <p class="text-sm text-on-surface-variant">Add key/value pairs which will be available in mappings as fixed variables.</p>
                    <div class="mt-sm space-y-sm">
                        <template v-for="(v,k) in form.custom_keys" :key="k">
                            <div class="flex items-center gap-sm">
                                <div class="px-sm py-xs border rounded w-48 font-label-mono">{{ k }}</div>
                                <input v-model="form.custom_keys[k]" class="px-sm py-xs border rounded flex-1" />
                                <button @click.prevent="removeCustomKey(k)" class="px-sm py-xs bg-error-container/20 rounded">Remove</button>
                            </div>
                        </template>
                        <div class="flex items-center gap-sm">
                            <input v-model="_newKey" placeholder="key" class="px-sm py-xs border rounded w-48" />
                            <input v-model="_newVal" placeholder="value" class="px-sm py-xs border rounded flex-1" />
                            <button @click.prevent="addCustomKey" class="px-sm py-xs bg-secondary text-white rounded">Add Key</button>
                        </div>
                    </div>
                </div>
                <div class="space-y-sm">
                    <div class="flex items-center justify-between py-sm border-b border-outline-variant">
                        <div class="flex items-center gap-sm">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">link</span>
                            <span class="font-body-md text-body-md">Base URL</span>
                        </div>
                        <span class="font-label-mono text-label-mono text-primary truncate max-w-xs">{{ conn.baseUrl }}</span>
                    </div>
                    <div class="flex items-center justify-between py-sm border-b border-outline-variant">
                        <div class="flex items-center gap-sm">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">key</span>
                            <span class="font-body-md text-body-md">API Token</span>
                        </div>
                        <span class="font-label-mono text-label-mono text-on-surface-variant">{{ conn.connected ? '✓ Verified' : 'Not validated' }}</span>
                    </div>
                    <div class="flex items-center justify-between py-sm">
                        <div class="flex items-center gap-sm">
                            <span class="material-symbols-outlined text-sm text-on-surface-variant">network_check</span>
                            <span class="font-body-md text-body-md">Connection</span>
                        </div>
                        <span :class="['font-label-mono text-label-mono', conn.connected ? 'text-on-tertiary-container' : 'text-error']">
                            {{ conn.connected ? 'OK — ' + conn.latency + 'ms' : (conn.error || 'Failed') }}
                        </span>
                    </div>
                </div>
            </div>

            <!-- Troubleshooting -->
            <div v-if="!conn.connected" class="flex items-start gap-sm p-md bg-error-container/20 border border-error/20 rounded-xl">
                <span class="material-symbols-outlined text-error shrink-0 mt-xs">warning</span>
                <div>
                    <p class="font-body-md text-body-md font-bold text-on-surface mb-xs">Connection Troubleshooting</p>
                    <ul class="font-body-md text-body-md text-on-surface-variant space-y-xs list-disc pl-md">
                        <li>Ensure Firefly III is running and accessible from this host.</li>
                        <li>Check <code class="font-label-mono bg-surface-container-high px-xs rounded">config.toml</code> for the correct <code class="font-label-mono bg-surface-container-high px-xs rounded">base_url</code> and <code class="font-label-mono bg-surface-container-high px-xs rounded">token</code>.</li>
                        <li>Verify the Personal Access Token has not expired in Firefly III.</li>
                        <li>Error: <code class="font-label-mono bg-surface-container-high px-xs rounded text-error">{{ conn.error || 'Unknown' }}</code></li>
                    </ul>
                </div>
            </div>
        </template>
    </div>
</template>
