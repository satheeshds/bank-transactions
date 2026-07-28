<script setup>
import { ref, onMounted } from 'vue'
import MailboxesView from './MailboxesView.vue'
import FireflyConnectionView from './FireflyConnectionView.vue'

const apiKey = ref('')
const saved = ref(false)

// Don't fetch and display the stored API key in the browser.
// If needed, the backend can expose a boolean "configured" flag instead.

onMounted(() => {})

async function save() {
    try {
        const res = await fetch('/api/v1/settings', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ key: 'gemini_api_key', value: apiKey.value }) })
        if (!res.ok) throw new Error('save failed')
        saved.value = true
        setTimeout(()=>saved.value=false,2000)
    } catch (e) { console.error(e) }
}
</script>

<template>
    <div class="space-y-lg">
        <div>
            <h2 class="font-headline-md text-headline-md text-primary mb-md">Settings</h2>
            <div class="bg-white border rounded p-md">
                <label class="flex flex-col mb-md">
                    <span class="font-label-mono mb-xs">Gemini API Key</span>
                    <input v-model="apiKey" type="password" autocomplete="off" class="px-sm py-xs border rounded" placeholder="Enter Gemini API key" />
                    <div class="flex items-center gap-sm">
                        <button @click="save" class="px-sm py-xs bg-secondary text-white rounded">Save</button>
                        <span v-if="saved" class="text-on-tertiary-container">Saved</span
                    </div>
                </label>
            </div>
        </div>

        <!-- Embedded Mailboxes and Firefly sections -->
        <div>
            <MailboxesView />
        </div>

        <div>
            <FireflyConnectionView />
        </div>
    </div>
</template>
