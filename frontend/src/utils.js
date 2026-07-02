export function formatRelativeTime(isoString) {
    if (!isoString) return '-'
    const date = new Date(isoString)
    const now = new Date()
    const diffMins = Math.floor((now - date) / 60000)
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function getMerchantIcon(merchant, status) {
    if (status === 'error') return 'help'
    const m = (merchant || '').toLowerCase()
    if (m.includes('coffee') || m.includes('restaurant') || m.includes('food')) return 'restaurant'
    if (m.includes('transport') || m.includes('metro') || m.includes('uber') || m.includes('taxi')) return 'subway'
    if (m.includes('gas') || m.includes('fuel')) return 'local_gas_station'
    return 'shopping_bag'
}
