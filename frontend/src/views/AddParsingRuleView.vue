<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const step = ref(1)
const saving = ref(false)
const error = ref(null)

const form = reactive({
    rule_name: '',
    description: '',
    // selected mailbox name (source_name) or id
    source_name: '',
    source_id: null,
    conditions: [
        { not: false, field: 'from', operator: 'equals', value: '' , timeframe: null }
    ],
    // default connector used when adding a new condition
    condition_mode: 'AND',
    regex: '',
    sample_text: '',
    mappings: [
        // start with only Amount mapping required; other mappings can be added by user
    ],
    transaction_type: 'withdrawal',
    card_last4: '',
    destination_account: '',
    sample_meta: {},
})

const mailboxes = ref([])

onMounted(async () => {
    try {
        const res = await fetch('/api/v1/mailboxes')
        if (res.ok) {
            const data = await res.json()
            mailboxes.value = (data && data.mailboxes) || []
            if (mailboxes.value.length) {
                // default to first mailbox
                form.source_id = mailboxes.value[0].id
                form.source_name = mailboxes.value[0].name
            }
        }
    } catch (e) {
        console.warn('Failed to load mailboxes', e)
    }
    // if editing existing rule, load it
    const qid = route.query.id
    if (qid) await loadExistingRule(Number(qid))
})

import { computed, watch, nextTick } from 'vue'

// reload custom keys when user navigates to Destination step
watch(step, (s) => { if (s === 4) loadFireflyKeys() })

const serverPreview = ref([])
const serverNamed = ref({})
const serverGroupIndex = ref({})
let previewTimer = null

// Debounced call to server preview
async function fetchServerPreview() {
    if (!form.regex || !form.sample_text) {
        serverPreview.value = []
        return
    }
    try {
        const res = await fetch('/api/v1/regex_preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ regex: form.regex, sample_text: form.sample_text }),
        })
        if (!res.ok) {
            serverPreview.value = []
            return
        }
        const data = await res.json()
        if (data && data.groups) {
            serverPreview.value = data.groups
            serverNamed.value = data.named || {}
            serverGroupIndex.value = data.groupindex || {}
        } else {
            serverPreview.value = []
            serverNamed.value = {}
            serverGroupIndex.value = {}
        }
    } catch (e) {
        serverPreview.value = []
    }
}

watch(() => [form.regex, form.sample_text], () => {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(() => {
        fetchServerPreview()
    }, 300)
})

const previewGroups = computed(() => {
    // Prefer server result if available, otherwise fall back to quick client-side parse
    if (serverPreview.value && serverPreview.value.length) return serverPreview.value
    const out = []
    if (!form.regex || !form.sample_text) return out
    try {
        const regexSource = String(form.regex).replace(/\(\?P<([a-zA-Z_][0-9a-zA-Z_]*)>/g, '(?<$1>')
        const re = new RegExp(regexSource)
        const m = re.exec(form.sample_text)
        if (!m) return out
        for (let i = 0; i < Math.min(10, m.length); i++) out[i] = m[i]
        return out
    } catch (e) {
        return out
    }
})

const previewNames = computed(() => {
    // Build an index->name mapping from serverGroupIndex (name->index)
    const out = {}
    const idxMap = serverGroupIndex.value || {}
    for (const [name, idx] of Object.entries(idxMap)) {
        out[Number(idx)] = name
    }
    return out
})

const groupCount = computed(() => {
    // compute highest captured group index from previewGroups
    if (!form.regex || !form.sample_text) return 0
    try {
        const re = new RegExp(form.regex)
        const m = re.exec(form.sample_text)
        if (!m) return 0
        return Math.max(0, m.length - 1)
    } catch (e) {
        return 0
    }
})

function availableGroups() {
    // Prefer server-side preview groups when available (returned from regex_preview)
    const serverCnt = (serverPreview.value && serverPreview.value.length) ? serverPreview.value.length - 1 : 0
    const cnt = serverCnt || groupCount.value || 0
    if (cnt <= 0) return []
    const out = []
    for (let i = 1; i <= cnt && i <= 12; i++) out.push(String(i))
    return out
}

function loadSample() {
    // If a mailbox is selected (form.source_id), request a sample from the server
    if (form.source_id) {
        // send conditions and mode so server can fetch a matching message
        fetch(`/api/v1/mailboxes/${form.source_id}/sample`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conditions: form.conditions, condition_mode: form.condition_mode })
        })
            .then(r => r.json())
            .then(data => {
                if (data && data.sample_text) form.sample_text = data.sample_text
                else if (data && data.error) form.sample_text = `Error: ${data.error}`
                else form.sample_text = ''
                // capture optional metadata (subject, from, sent_date, etc.) for IMAP field preview
                if (data && data.sample_meta) form.sample_meta = data.sample_meta
                else form.sample_meta = {}
            })
            .catch(() => {
                form.sample_text = ''
            })
        return
    }

    // fallback placeholder sample
    form.sample_text = "Total: Rs. 1,234.56 spent on your SBI Credit Card ending with 1234 at Amazon on 02-07-2026"
}

const fireflyFields = [
    { key: 'type', label: 'Type' },
    { key: 'date', label: 'Date' },
    { key: 'amount', label: 'Amount' },
    { key: 'description', label: 'Description' },
    { key: 'order', label: 'Order' },
    { key: 'currency_id', label: 'Currency ID' },
    { key: 'currency_code', label: 'Currency Code' },
    { key: 'foreign_amount', label: 'Foreign Amount' },
    { key: 'foreign_currency_id', label: 'Foreign Currency ID' },
    { key: 'foreign_currency_code', label: 'Foreign Currency Code' },
    { key: 'budget_id', label: 'Budget ID' },
    { key: 'budget_name', label: 'Budget Name' },
    { key: 'category_id', label: 'Category ID' },
    { key: 'category_name', label: 'Category Name' },
    { key: 'source_id', label: 'Source Account ID' },
    { key: 'source_name', label: 'Source Account Name' },
    { key: 'destination_id', label: 'Destination Account ID' },
    { key: 'destination_name', label: 'Destination Account Name' },
    { key: 'reconciled', label: 'Reconciled' },
    { key: 'piggy_bank_id', label: 'Piggy Bank ID' },
    { key: 'piggy_bank_name', label: 'Piggy Bank Name' },
    { key: 'bill_id', label: 'Bill ID' },
    { key: 'bill_name', label: 'Bill Name' },
    { key: 'tags', label: 'Tags' },
    { key: 'notes', label: 'Notes' },
    { key: 'internal_reference', label: 'Internal Reference' },
    { key: 'external_id', label: 'External ID' },
    { key: 'external_url', label: 'External URL' },
    { key: 'sepa_cc', label: 'SEPA CC' },
    { key: 'sepa_ct_op', label: 'SEPA CT OP' },
    { key: 'sepa_ct_id', label: 'SEPA CT ID' },
    { key: 'sepa_db', label: 'SEPA DB' },
    { key: 'sepa_country', label: 'SEPA Country' },
    { key: 'sepa_ep', label: 'SEPA EP' },
    { key: 'sepa_ci', label: 'SEPA CI' },
    { key: 'sepa_batch_id', label: 'SEPA Batch ID' },
    { key: 'interest_date', label: 'Interest Date' },
    { key: 'book_date', label: 'Book Date' },
    { key: 'process_date', label: 'Process Date' },
    { key: 'due_date', label: 'Due Date' },
    { key: 'payment_date', label: 'Payment Date' },
    { key: 'invoice_date', label: 'Invoice Date' },
]

const imapFields = [
    { key: 'sent_date', label: 'Sent Date' },
    { key: 'subject', label: 'Subject' },
    { key: 'from', label: 'From' },
    { key: 'to', label: 'To' },
    { key: 'cc', label: 'CC' },
    { key: 'bcc', label: 'BCC' },
    { key: 'message_id', label: 'Message ID' },
]

// custom keys from Firefly connection (loaded on mount)
const customKeys = ref({})

async function loadFireflyKeys() {
    try {
        const res = await fetch('/api/v1/firefly')
        if (!res.ok) return
        const j = await res.json()
        customKeys.value = j.custom_keys || {}
    } catch (e) { /* ignore */ }
}
onMounted(() => { loadFireflyKeys() })

async function loadExistingRule(id) {
    try {
        const res = await fetch(`/api/v1/rules/${id}`)
        if (!res.ok) return
        const j = await res.json()
        form.rule_name = j.rule_name || ''
        form.description = ''
        form.source_name = j.source_name || ''
        form.regex = j.regex || ''
        form.transaction_type = j.transaction_type || 'withdrawal'
        form.card_last4 = j.card_last4 || ''
        form.conditions = j.conditions || []
        form.condition_mode = j.condition_mode || 'AND'
        form.mappings = j.mappings || []
        // ensure amount mapping exists
        if (!form.mappings.find(m=>m.fieldKey==='amount')) ensureMapping('amount')
    } catch (e) { console.error('loadExistingRule', e) }

}

// UI helper model for adding fields
const _fieldToAdd = ref('')

function ensureMapping(fieldKey) {
    let m = form.mappings.find(x => x.fieldKey === fieldKey)
    if (!m) {
        const groups = availableGroups()
        let label = fieldKey
        let initialKey = fieldKey
        // support custom keys encoded as 'custom:NAME'
        if (String(fieldKey).startsWith('custom:')) {
            const k = String(fieldKey).split(':')[1]
            label = `Custom: ${k}`
            initialKey = fieldKey
        } else {
            const ff = fireflyFields.find(f=>f.key===fieldKey)
            label = ff ? ff.label : fieldKey
        }
        // if it's a custom key, default to fixed with the configured value
        if (String(initialKey).startsWith('custom:')) {
            const k = String(initialKey).split(':')[1]
            m = { fieldKey: initialKey, field: label, source_type: 'fixed', value: (customKeys.value && customKeys.value[k]) || '', group: groups.length ? groups[0] : '1' }
        } else {
            m = { fieldKey: initialKey, field: label, source_type: 'regex_group', value: '', group: groups.length ? groups[0] : '1' }
        }
        form.mappings.push(m)
    }
    return m
}

// initialize mapping only for required field `amount`
ensureMapping('amount')

function availableFireflyFieldsToAdd() {
    return fireflyFields.filter(f => !form.mappings.find(m => m.fieldKey === f.key))
}

function addFieldMapping(fieldKey) {
    ensureMapping(fieldKey)
}

function next() { 
    // require rule_name on step 1
    if (step.value === 1 && !form.rule_name) {
        error.value = 'Rule name is required'
        return
    }
    error.value = null
    if (step.value < 4) step.value++ 
}

function addCondition() {
    // new condition connects to previous one using current default connector
    const conn = form.condition_mode || 'AND'
    form.conditions.push({ not: false, field: 'subject', operator: 'contains', value: '', timeframe: null, connector: conn })
}

function removeCondition(i) {
    form.conditions.splice(i,1)
}

function toggleAndOr() {
    form.condition_mode = form.condition_mode === 'OR' ? 'AND' : 'OR'
}
function setConditionMode(mode) {
    form.condition_mode = mode === 'OR' ? 'OR' : 'AND'
}
function toggleConnector(index) {
    if (!form.conditions[index]) return
    const current = form.conditions[index].connector || form.condition_mode
    form.conditions[index].connector = current === 'AND' ? 'OR' : 'AND'
}
function back() { if (step.value > 1) step.value-- }

function isValidEmail(v) {
    if (!v) return false
    // simple RFC-like check
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

function isEmailField(f) {
    return f === 'from' || f === 'to'
}

async function submitRule() {
    saving.value = true
    error.value = null
    // Validate required mappings (Amount required)
    try {
        const amountMap = form.mappings.find(m => m.fieldKey === 'amount' || m.field === 'Amount')
        if (!amountMap) throw new Error('Amount mapping is required')
        if (amountMap.source_type === 'regex_group' && (!amountMap.group || Number(amountMap.group) <= 0)) {
            throw new Error('Amount mapping must select a regex group')
        }
        if (amountMap.source_type === 'fixed' && !amountMap.value) {
            throw new Error('Amount mapping fixed value cannot be empty')
        }
    } catch (e) {
        error.value = e.message || String(e)
        saving.value = false
        return
    }
    try {
        const body = {
            source_name: form.source_name || (form.source_id ? `mailbox:${form.source_id}` : 'Unnamed Source'),
            rule_name: form.rule_name || 'Unnamed Rule',
            regex: form.regex,
            conditions: form.conditions,
            condition_mode: form.condition_mode,
            mappings: form.mappings,
            transaction_type: form.transaction_type || 'withdrawal',
            card_last4: form.card_last4 || null,
        }
        let res
        if (route.query.id) {
            res = await fetch(`/api/v1/rules/${route.query.id}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            })
        } else {
            res = await fetch('/api/v1/rules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        }
        if (!res.ok) throw new Error((await res.json()).detail || 'Failed to save rule')
        router.push('/parsing-rules')
    } catch (e) {
        error.value = e.message || String(e)
    } finally { saving.value = false }
}
</script>

<template>
    <div class="flex gap-lg">
        <!-- Left nav -->
        <aside class="w-64">
            <div class="sticky top-20">
                <h2 class="font-headline-md text-headline-md text-primary mb-md">{{ route.query.id ? 'Edit Parsing Rule' : 'Create New Parsing Rule' }}</h2>
                <p class="font-body-md text-on-surface-variant mb-lg">Define how incoming emails are transformed into Firefly III transactions.</p>
                <nav class="bg-surface-container-lowest border border-outline-variant rounded-xl p-md">
                    <ul class="flex flex-col gap-sm">
                        <li :class="['flex items-center gap-sm p-sm rounded', step===1 ? 'bg-surface-container border-l-4 border-secondary' : '']">
                            <div class="w-6 h-6 rounded-full bg-surface-container flex items-center justify-center">1</div>
                            <div>
                                <div class="font-label-mono">Basic Info</div>
                                <div class="text-xs text-on-surface-variant">Identification</div>
                            </div>
                        </li>
                        <li :class="['flex items-center gap-sm p-sm rounded', step===2 ? 'bg-surface-container border-l-4 border-secondary' : '']">
                            <div class="w-6 h-6 rounded-full bg-surface-container flex items-center justify-center">2</div>
                            <div>
                                <div class="font-label-mono">Trigger</div>
                                <div class="text-xs text-on-surface-variant">Source & Filtering</div>
                            </div>
                        </li>
                        <li :class="['flex items-center gap-sm p-sm rounded', step===3 ? 'bg-surface-container border-l-4 border-secondary' : '']">
                            <div class="w-6 h-6 rounded-full bg-surface-container flex items-center justify-center">3</div>
                            <div>
                                <div class="font-label-mono">Patterns</div>
                                <div class="text-xs text-on-surface-variant">Regex & Extraction</div>
                            </div>
                        </li>
                        <li :class="['flex items-center gap-sm p-sm rounded', step===4 ? 'bg-surface-container border-l-4 border-secondary' : '']">
                            <div class="w-6 h-6 rounded-full bg-surface-container flex items-center justify-center">4</div>
                            <div>
                                <div class="font-label-mono">Destination</div>
                                <div class="text-xs text-on-surface-variant">Firefly III Mapping</div>
                            </div>
                        </li>
                    </ul>
                </nav>
            </div>
        </aside>

        <!-- Right content header only -->
        <div class="flex-1">
            <div class="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
                <div class="flex items-center justify-between mb-md">
                    <div>
                        <h3 class="font-headline-sm">Step {{ step }} — {{ step === 1 ? 'Basic Information' : step === 2 ? 'Trigger Conditions' : step === 3 ? 'Pattern Matching' : 'Destination' }}</h3>
                        <p class="text-on-surface-variant mt-xs">{{ step === 1 ? 'Identification' : step === 2 ? 'Source & Filtering' : step === 3 ? 'Regex & Extraction' : 'Firefly III Mapping' }}</p>
                    </div>
                    <div class="font-label-mono text-label-mono">Step {{ step }} / 4</div>
                </div>

                <!-- Step content -->
                <div class="py-md">
                    <div v-if="step === 1">
                        <div class="bg-white border rounded p-md">
                            <div class="grid grid-cols-2 gap-md mt-md">
                                <label class="flex flex-col"><span class="font-label-mono mb-xs">Rule Name <span class="text-error">*</span></span><input v-model="form.rule_name" class="px-sm py-xs border rounded" /></label>
                                <label class="flex flex-col"><span class="font-label-mono mb-xs">Mailbox</span>
                                    <select v-model="form.source_id" @change="form.source_name = (mailboxes.find(m=>m.id==form.source_id)||{}).name || ''" class="px-sm py-xs border rounded">
                                        <option v-for="m in mailboxes" :key="m.id" :value="m.id">{{ m.name }} — {{ m.username || m.host }}</option>
                                    </select>
                                </label>
                                <label class="col-span-2 flex flex-col"><span class="font-label-mono mb-xs">Description</span><input v-model="form.description" class="px-sm py-xs border rounded" /></label>
                            </div>
                        </div>
                    </div>

                    <div v-if="step === 2">
                        <div class="bg-white border rounded p-md">
                            <p class="mt-xs font-headline-sm">Define conditions that determine when this rule runs.</p>
                            <div class="mt-md">
                                <div class="flex items-center justify-between mb-sm">
                                    <div class="font-label-mono text-sm">Conditions</div>
                                    <div class="flex items-center gap-sm">
                                        <!-- Show both options; highlight selected -->
                                        <button @click="setConditionMode('AND')" :class="['px-sm py-xs rounded', form.condition_mode === 'AND' ? 'bg-secondary text-white' : 'border']">AND</button>
                                        <button @click="setConditionMode('OR')" :class="['px-sm py-xs rounded', form.condition_mode === 'OR' ? 'bg-secondary text-white' : 'border']">OR</button>
                                    </div>
                                </div>

                                <div v-for="(c,i) in form.conditions" :key="i">
                                    <div class="flex items-center gap-sm border-b py-sm">
                                    <label class="flex items-center gap-xs"><input type="checkbox" v-model="c.not" /> NOT</label>
                                    <select v-model="c.field" class="px-sm py-xs border rounded">
                                        <option value="from">From</option>
                                        <option value="to">To</option>
                                        <option value="subject">Subject</option>
                                        <option value="text">Text</option>
                                        <option value="sent_date">Sent Date</option>
                                    </select>

                                    <!-- Operators: fixed for certain fields -->
                                    <div v-if="isEmailField(c.field)" class="px-sm py-xs border rounded">Equals</div>
                                    <div v-else-if="['subject','text'].includes(c.field)" class="px-sm py-xs border rounded">Contains</div>
                                    <select v-else v-model="c.operator" class="px-sm py-xs border rounded">
                                        <option value="equals">Equals</option>
                                        <option value=">=">Greater than or equal</option>
                                        <option value="<=">Less than or equal</option>
                                    </select>

                                    <!-- Value input: date picker for sent_date, email validation for from/to, text input otherwise -->
                                    <input v-if="c.field !== 'sent_date' && c.operator !== 'within_last'" v-model="c.value" :class="['px-sm py-xs border rounded', isEmailField(c.field) && c.value && !isValidEmail(c.value) ? 'border-error' : '']" placeholder="Value" />

                                    <input v-else-if="c.field === 'sent_date'" type="date" v-model="c.value" class="px-sm py-xs border rounded" />

                                    <div v-if="isEmailField(c.field) && c.value" class="text-xs ml-xs" :class="isValidEmail(c.value) ? 'text-muted' : 'text-error'">{{ isValidEmail(c.value) ? 'Valid email' : 'Invalid email' }}</div>

                                    <button @click="removeCondition(i)" class="px-sm py-xs bg-error-container/20 rounded">delete</button>
                                    </div>

                                    <!-- Connector between conditions: toggles only this connection -->
                                    <div v-if="i < form.conditions.length - 1" class="flex items-center justify-center py-xs">
                                        <button @click="toggleConnector(i+1)" class="px-sm py-xs border rounded">{{ form.conditions[i+1].connector || form.condition_mode }}</button>
                                    </div>
                                </div>
                                <!-- Add Condition moved below the list -->
                                <div class="mt-md flex items-center justify-end gap-sm">
                                    <button @click="addCondition" class="px-sm py-xs bg-secondary text-white rounded">Add Condition</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                    <div v-if="step === 3">
                        <div class="bg-white border rounded p-md">
                            <p class="mt-xs font-headline-sm">Define a regular expression to extract fields from the email.</p>

                            <div class="grid grid-cols-1 gap-md mt-md">
                                <label class="flex flex-col"><span class="font-label-mono mb-xs">Regex Configuration</span>
                                    <textarea v-model="form.regex" rows="3" class="px-sm py-xs border rounded font-mono" placeholder="Enter regex here"></textarea>
                                </label>

                                <div class="flex items-center gap-sm">
                                    <button class="px-sm py-xs border rounded">AI Suggest</button>
                                    <button class="px-sm py-xs border rounded">Real-time validation</button>
                                    <div class="flex-1"></div>
                                    <button @click="loadSample" class="px-sm py-xs border rounded">Load Sample Email</button>
                                </div>

                                <label class="flex flex-col"><span class="font-label-mono mb-xs">Sample Text</span>
                                    <textarea v-model="form.sample_text" rows="6" class="px-sm py-xs border rounded" placeholder="Paste email content here to test your regex..."></textarea>
                                </label>

                                <div class="grid grid-cols-3 gap-md">
                                    <template v-for="i in Math.min(12, Math.max(3, previewGroups.length - 1))" :key="i">
                                        <div class="bg-surface-container-high p-sm rounded text-center">
                                            <div class="font-label-mono text-xs text-on-surface-variant">
                                                {{ previewNames[i] ? ('Group ' + i + ' (' + previewNames[i] + ')') : ('Group ' + i) }}
                                            </div>
                                            <div class="font-headline-sm mt-xs">{{ previewGroups[i] || '-' }}</div>
                                        </div>
                                    </template>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div v-if="step === 4">
                        <div class="bg-white border rounded p-md">
                            <p class="mt-xs font-headline-sm">Map extracted values to Firefly III fields.</p>

                            <div class="grid grid-cols-1 gap-md mt-md">
                                <div v-for="(m,mi) in form.mappings" :key="m.fieldKey || m.field" class="grid grid-cols-12 gap-sm items-center p-sm border rounded">
                                    <div class="col-span-3 font-label-mono">{{ m.field }}</div>
                                    <div class="col-span-5 flex items-center gap-sm">
                                        <select v-model="m.source_type" class="px-sm py-xs border rounded">
                                            <option value="regex_group">Regex Group</option>
                                            <option value="fixed">Fixed Value</option>
                                            <option value="custom_key">Custom Key</option>
                                            <option value="imap">IMAP Field</option>
                                        </select>
                                        <select v-if="m.source_type === 'regex_group'" v-model="m.group" class="px-sm py-xs border rounded">
                                            <option v-if="availableGroups().length===0" disabled>No groups</option>
                                            <option v-for="g in availableGroups()" :key="g" :value="g">{{ previewNames[g] ? ('Group ' + g + ' (' + previewNames[g] + ')') : ('Group ' + g) }}</option>
                                        </select>
                                        <input v-if="m.source_type === 'fixed'" v-model="m.value" class="px-sm py-xs border rounded" placeholder="Fixed value" />
                                        <select v-if="m.source_type === 'custom_key'" v-model="m.custom_key" class="px-sm py-xs border rounded">
                                            <option disabled value="">Select custom key...</option>
                                            <option v-for="(v,k) in customKeys" :key="k" :value="k">{{ k }}</option>
                                        </select>
                                        <select v-if="m.source_type === 'imap'" v-model="m.imap_field" class="px-sm py-xs border rounded">
                                            <option disabled value="">Select IMAP field...</option>
                                            <option v-for="f in imapFields" :key="f.key" :value="f.key">{{ f.label }}</option>
                                        </select>
                                    </div>
                                    <div class="col-span-3 text-right text-sm text-on-surface-variant">Preview: <span class="font-headline-sm">
                                        {{ m.source_type === 'regex_group' ? (previewGroups[Number(m.group)] || '-') : (m.source_type === 'custom_key' ? (customKeys[m.custom_key] || '-') : (m.source_type === 'imap' ? (form.sample_meta && form.sample_meta[m.imap_field] ? form.sample_meta[m.imap_field] : '-') : (m.value || '-'))) }}
                                    </span></div>
                                    <div class="col-span-1 text-right">
                                        <button @click.prevent="form.mappings.splice(mi,1)" class="px-sm py-xs bg-error-container/20 rounded">Remove</button>
                                    </div>
                                </div>
                                <div class="mt-md flex items-center gap-sm">
                                    <div class="flex-1 text-sm text-on-surface-variant">Add or adjust mappings; these will be saved with the rule.</div>
                                    <div>
                                        <select v-model="_fieldToAdd" class="px-sm py-xs border rounded mr-sm">
                                            <option disabled value="">Add field...</option>
                                            <option v-for="f in availableFireflyFieldsToAdd()" :key="f.key" :value="f.key">{{ f.label }}</option>
                                            <!-- custom keys are selectable as a source type inside a mapping row (Custom Key), not shown here -->
                                        </select>
                                        <button @click="addFieldMapping(_fieldToAdd)" class="px-sm py-xs bg-secondary text-white rounded" :disabled="!_fieldToAdd">Add Field Mapping</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                <div class="flex items-center gap-sm mt-md">
                    <button v-if="step > 1" @click="back" class="px-md py-sm bg-surface rounded border">← Back to List</button>
                    <div class="flex-1"></div>
                    <button @click="$router.push('/parsing-rules')" class="px-md py-sm bg-surface rounded border">Cancel</button>
                    <button v-if="step < 4" @click="next" class="px-md py-sm bg-secondary text-white rounded">Next</button>
                    <button v-else @click="submitRule" :disabled="saving" class="px-md py-sm bg-primary text-white rounded">{{ route.query.id ? 'Save Rule' : 'Create Rule' }}</button>
                    <span v-if="error" class="text-error ml-sm">{{ error }}</span>
                </div>

            </div>
        </div>
    </div>
</template>
