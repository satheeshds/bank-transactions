<script setup>
import { ref, reactive, onMounted, onUnmounted, watch } from 'vue'
import store from '../store.js'

const loading = ref(true)
const mailbox = reactive({ host: '-', username: '-', connected: false, error: null })
const sources = ref([])
let interval = null

const showForm = ref(false)
const form = reactive({
    id: null,
    name: '', host: '', port: 993, username: '', password: '', encryption: 'ssl/tls', smtp_host: '', smtp_port: 587
})
const adding = ref(false)
const testing = ref(false)
const testResult = ref(null)

async function loadSources() {
    loading.value = true
    try {
        const [statusRes, mailboxesRes] = await Promise.all([fetch('/api/status'), fetch('/api/v1/mailboxes')])
        if (statusRes.ok) {
            const { imap } = await statusRes.json()
            mailbox.host = imap.host || 'Not configured'
            mailbox.username = imap.username || '-'
            mailbox.connected = imap.connected
            mailbox.error = imap.error
        }
        if (mailboxesRes.ok) {
            const data = await mailboxesRes.json()
            sources.value = (data.mailboxes || []).map(m => ({
                id: m.id,
                name: m.name,
                host: m.host,
                username: m.username,
                smtp_host: m.smtp_host,
            }))
        }
    } catch (e) { console.error('loadSources', e) }
    finally { loading.value = false }
}

watch(() => store.refreshTrigger, loadSources)
onMounted(() => { loadSources(); interval = setInterval(loadSources, 15000) })
onUnmounted(() => { if (interval) clearInterval(interval) })

async function saveMailbox() {
    if (!form.name) return
    adding.value = true
    try {
        const payload = {
            name: form.name,
            host: form.host,
            port: form.port,
            username: form.username,
            password: form.password,
            encryption: form.encryption,
            smtp_host: form.smtp_host,
            smtp_port: form.smtp_port,
        }
        let res
        if (form.id) {
            res = await fetch(`/api/v1/mailboxes/${form.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        } else {
            res = await fetch('/api/v1/mailboxes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        }
        if (res.ok) {
            form.id = null
            form.name = ''
            form.host = ''
            form.port = 993
            form.username = ''
            form.password = ''
            form.encryption = 'ssl/tls'
            form.smtp_host = ''
            form.smtp_port = 587
            showForm.value = false
            await loadSources()
        } else {
            console.error('saveMailbox failed', await res.text())
        }
    } catch (e) { console.error('saveMailbox', e) }
    finally { adding.value = false }
}

async function testConnection() {
    if (!form.host) return alert('Host is required')
    testing.value = true
    try {
        const payload = {
            host: form.host,
            port: form.port,
            username: form.username,
            password: form.password,
        }
        const res = await fetch('/api/v1/mailboxes/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        if (res.ok) {
            const data = await res.json()
            if (data.connected) testResult.value = { ok: true, msg: 'Connection successful' + (data.warning ? `: ${data.warning}` : '') }
            else testResult.value = { ok: false, msg: 'Connection failed: ' + (data.error || 'unknown') }
        } else {
            testResult.value = { ok: false, msg: 'Test request failed' }
        }
    } catch (e) { console.error('testConnection', e); alert('Test failed: ' + e) }
    finally { testing.value = false }
}

function editMailbox(m) {
    form.id = m.id
    form.name = m.name
    form.host = m.host
    form.username = m.username
    form.smtp_host = m.smtp_host
    showForm.value = true
}

async function deleteMailbox(id) {
    if (!confirm('Delete mailbox?')) return
    try {
        const res = await fetch(`/api/v1/mailboxes/${id}`, { method: 'DELETE' })
        if (res.ok) await loadSources()
        else console.error('delete failed', await res.text())
    } catch (e) { console.error('deleteMailbox', e) }
}
</script>

<template>
    <div class="flex flex-col gap-lg">
        <div>
            <h2 class="font-headline-md text-headline-md text-primary">Mailboxes</h2>
            <p class="font-body-md text-on-surface-variant mt-xs">Configured IMAP mailbox and mailbox definitions.</p>
        </div>

        <!-- Mailbox connection card (unchanged) -->
        <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
            <h3 class="font-headline-sm text-headline-sm mb-md flex items-center gap-sm">
                <span class="material-symbols-outlined text-secondary">mail</span>
                Mailbox Connection
            </h3>
            <div class="mb-md">
                <p class="font-caption text-caption text-on-surface-variant mb-sm">Configured connections</p>
                <div class="flex flex-col gap-sm">
                    <template v-if="sources.length === 0">
                        <div class="py-md text-on-surface-variant">No mailboxes configured. Use "Add Mailbox" to create one.</div>
                    </template>
                    <template v-else>
                        <div v-for="m in sources" :key="m.id" class="flex items-center justify-between p-2 rounded border border-outline-variant bg-surface-container">
                            <div class="flex items-center gap-sm">
                                <div class="w-8 h-8 rounded-md bg-surface-container-low flex items-center justify-center">
                                    <span class="material-symbols-outlined text-sm">dns</span>
                                </div>
                                <div>
                                    <p class="font-label-mono text-label-mono">{{ m.name }}</p>
                                    <p class="font-caption text-caption text-on-surface-variant">{{ m.host || '—' }}</p>
                                </div>
                            </div>
                            <div class="flex items-center gap-sm">
                                <button class="px-sm py-1 border rounded" @click="editMailbox(m)">Edit</button>
                                <button class="px-sm py-1 border rounded text-error" @click="deleteMailbox(m.id)">Delete</button>
                            </div>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <!-- Mailbox definitions + form -->
        <div>
            <h3 class="font-headline-sm text-headline-sm mb-md">Mailbox Definitions</h3>
            <div class="flex items-center gap-sm mb-md">
                <button class="px-md py-2 bg-secondary text-on-secondary rounded-md" @click="showForm = !showForm">{{ showForm ? 'Cancel' : 'Add Mailbox' }}</button>
            </div>
            <div v-if="showForm" class="bg-surface-container p-md rounded-md border border-outline-variant mb-md">
                <div class="grid grid-cols-2 gap-md">
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">Mailbox Name</label>
                        <input v-model="form.name" class="w-full border p-2 rounded" placeholder="e.g., Finance Team Outlook" />
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">IMAP Host</label>
                        <input v-model="form.host" class="w-full border p-2 rounded" placeholder="imap.provider.com" />
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">Port</label>
                        <input v-model.number="form.port" class="w-full border p-2 rounded" />
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">Username</label>
                        <input v-model="form.username" class="w-full border p-2 rounded" />
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">Password</label>
                        <input v-model="form.password" type="password" class="w-full border p-2 rounded" />
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">Encryption</label>
                        <select v-model="form.encryption" class="w-full border p-2 rounded">
                            <option>ssl/tls</option>
                            <option>starttls</option>
                            <option>none</option>
                        </select>
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">SMTP Host</label>
                        <input v-model="form.smtp_host" class="w-full border p-2 rounded" placeholder="smtp.provider.com" />
                    </div>
                    <div>
                        <label class="font-caption text-caption text-on-surface-variant uppercase">SMTP Port</label>
                        <input v-model.number="form.smtp_port" class="w-full border p-2 rounded" />
                    </div>
                </div>
                <div class="mt-md">
                    <button class="px-md py-2 bg-secondary text-on-secondary rounded-md mr-sm" @click="saveMailbox" :disabled="adding">{{ adding ? 'Saving...' : (form.id ? 'Save Changes' : 'Save Mailbox') }}</button>
                    <button class="px-md py-2 border rounded-md mr-sm" @click="testConnection" :disabled="testing">{{ testing ? 'Testing...' : 'Test Connection' }}</button>
                    <button class="px-md py-2 border rounded-md" @click="() => (showForm = false)" :disabled="adding">Cancel</button>
                </div>
                <div v-if="testResult" class="mt-sm">
                    <p :class="testResult.ok ? 'text-success' : 'text-error'">{{ testResult.msg }}</p>
                </div>
            </div>

            <p v-if="loading && sources.length === 0" class="text-on-surface-variant text-sm py-lg text-center">Loading...</p>
            <div v-else-if="sources.length === 0" class="flex flex-col items-center justify-center py-xl text-on-surface-variant gap-sm">
                <span class="material-symbols-outlined text-[48px]">inbox</span>
                <p class="font-body-lg">No mailboxes configured</p>
            </div>
            <!-- Mailbox definitions removed; connection card above shows configured mailboxes -->
        </div>
    </div>
</template>
