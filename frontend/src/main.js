import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import './style.css'
import AppLayout from './components/AppLayout.vue'
import DashboardView from './views/DashboardView.vue'
import MailboxesView from './views/MailboxesView.vue'
import ParsingRulesView from './views/ParsingRulesView.vue'
import FailedParsesView from './views/FailedParsesView.vue'
import FireflyConnectionView from './views/FireflyConnectionView.vue'

const router = createRouter({
    history: createWebHashHistory(),
    routes: [
        { path: '/', redirect: '/dashboard' },
        { path: '/dashboard',          component: DashboardView,        meta: { title: 'Dashboard' } },
        { path: '/mailboxes',           component: MailboxesView,     meta: { title: 'Mailboxes' } },
        { path: '/parsing-rules',      component: ParsingRulesView,     meta: { title: 'Parsing Rules' } },
        { path: '/failed-parses',      component: FailedParsesView,     meta: { title: 'Failed Parses' } },
        { path: '/firefly-connection', component: FireflyConnectionView, meta: { title: 'Firefly Connection' } },
    ],
})

createApp(AppLayout).use(router).mount('#app')
