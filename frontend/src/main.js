import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import './style.css'
import AppLayout from './components/AppLayout.vue'
import DashboardView from './views/DashboardView.vue'
import ParsingRulesView from './views/ParsingRulesView.vue'
import AddParsingRuleView from './views/AddParsingRuleView.vue'
import FailedParsesView from './views/FailedParsesView.vue'
import SettingsView from './views/SettingsView.vue'
import FailedParseDetailView from './views/FailedParseDetailView.vue'

const router = createRouter({
    history: createWebHashHistory(),
    routes: [
        { path: '/', redirect: '/dashboard' },
        { path: '/dashboard',          component: DashboardView,        meta: { title: 'Dashboard' } },
        { path: '/mailboxes',           redirect: '/settings' },
        { path: '/parsing-rules',      component: ParsingRulesView,     meta: { title: 'Parsing Rules' } },
        { path: '/parsing-rules/add',  component: AddParsingRuleView,   meta: { title: 'Add Parsing Rule' } },
        { path: '/failed-parses',      component: FailedParsesView,     meta: { title: 'Failed Parses' } },
        { path: '/failed-parses/:id',  component: FailedParseDetailView, meta: { title: 'Failed Parse' } },
        { path: '/firefly-connection', redirect: '/settings' },
        { path: '/settings', component: SettingsView, meta: { title: 'Settings' } },
    ],
})

createApp(AppLayout).use(router).mount('#app')
