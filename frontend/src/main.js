import './index.css'
import { createApp } from 'vue'
import router from './router'
import App from './App.vue'
import { createPinia } from 'pinia'
import dayjs from '@/utils/dayjs'
import { createDialog } from '@/utils/dialogs'
import translationPlugin from './translation'
import { usersStore } from './stores/user'
import { initSocket } from './socket'
import { FrappeUI, setConfig, frappeRequest, pageMetaPlugin } from 'frappe-ui'

let pinia = createPinia()
let app = createApp(App)
setConfig('resourceFetcher', frappeRequest)

app.use(FrappeUI)
app.use(pinia)
app.use(router)
app.use(translationPlugin)
app.use(pageMetaPlugin)
app.provide('$dayjs', dayjs)
app.provide('$socket', initSocket())
app.mount('#app')

const { userResource, allUsers } = usersStore()
app.provide('$user', userResource)
app.provide('$allUsers', allUsers)

app.config.globalProperties.$user = userResource
app.config.globalProperties.$dialog = createDialog

// Replace "Built on Frappe" with "Built by Zensbot.com" branding
const replaceBuiltOnFrappe = () => {
	if (!document.body) return
	const walker = document.createTreeWalker(
		document.body,
		NodeFilter.SHOW_TEXT,
		null,
		false
	)
	let node
	while ((node = walker.nextNode())) {
		if (node.nodeValue && node.nodeValue.includes('Built on Frappe')) {
			node.nodeValue = node.nodeValue.replace('Built on Frappe', 'Built by Zensbot.com')
		}
	}
	// Also check for links with href to frappe.io and update them
	document.querySelectorAll('a[href*="frappe.io"]').forEach((link) => {
		if (link.textContent.includes('Frappe')) {
			link.href = 'https://zensbot.com'
			link.textContent = link.textContent.replace('Frappe', 'Zensbot.com')
		}
	})
}

// Use MutationObserver to catch dynamically rendered content
if (document.body) {
	const observer = new MutationObserver(() => {
		replaceBuiltOnFrappe()
	})
	observer.observe(document.body, {
		childList: true,
		subtree: true
	})
	replaceBuiltOnFrappe()
}
