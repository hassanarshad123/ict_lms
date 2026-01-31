<template>
	<Dialog
		v-model="show"
		:options="{
			title: __('User Devices'),
			size: 'lg',
		}"
	>
		<template #body-content>
			<div v-if="devices.loading" class="flex justify-center py-8">
				<Spinner class="w-6 h-6 text-ink-gray-5" />
			</div>

			<div v-else-if="!devices.data?.device_limit_enabled" class="text-ink-gray-7 text-sm">
				{{ __('Device tracking is not enabled in LMS Settings.') }}
			</div>

			<div v-else>
				<div class="flex items-center justify-between mb-4">
					<div class="text-sm text-ink-gray-7">
						{{ __('User') }}: <span class="font-medium text-ink-gray-9">{{ user }}</span>
					</div>
					<div class="text-sm text-ink-gray-7">
						{{ devices.data?.current_count }} / {{ devices.data?.max_devices }}
						{{ __('devices') }}
					</div>
				</div>

				<div v-if="devices.data?.devices?.length === 0" class="text-ink-gray-7 text-sm py-4">
					{{ __('No devices registered for this user.') }}
				</div>

				<div v-else class="space-y-3 max-h-[400px] overflow-y-auto">
					<div
						v-for="device in devices.data?.devices"
						:key="device.device_id"
						class="flex items-center justify-between p-3 bg-surface-gray-1 rounded-lg border border-outline-gray-2"
					>
						<div class="flex items-center space-x-3">
							<div class="p-2 bg-surface-white rounded-lg">
								<Monitor v-if="isDesktop(device.device_name)" class="w-5 h-5 text-ink-gray-7" />
								<Smartphone v-else-if="isMobile(device.device_name)" class="w-5 h-5 text-ink-gray-7" />
								<Laptop v-else class="w-5 h-5 text-ink-gray-7" />
							</div>
							<div>
								<div class="font-medium text-ink-gray-9 text-sm">
									{{ device.device_name || __('Unknown Device') }}
								</div>
								<div class="text-xs text-ink-gray-7 mt-0.5">
									<span v-if="device.ip_address">{{ device.ip_address }}</span>
									<span v-if="device.ip_address && device.last_active" class="mx-1">|</span>
									<span v-if="device.last_active">{{ formatDate(device.last_active) }}</span>
								</div>
							</div>
						</div>
						<Button
							variant="subtle"
							theme="red"
							size="sm"
							:loading="removingDevice === device.device_id"
							@click="removeDevice(device.device_id)"
						>
							<template #prefix>
								<Trash2 class="w-3 h-3" />
							</template>
							{{ __('Remove') }}
						</Button>
					</div>
				</div>

				<div class="flex justify-end gap-2 mt-4 pt-4 border-t border-outline-gray-2">
					<Button
						variant="subtle"
						theme="red"
						:loading="clearingAll"
						:disabled="!devices.data?.devices?.length"
						@click="clearAllDevices"
					>
						<template #prefix>
							<Trash2 class="w-4 h-4" />
						</template>
						{{ __('Clear All Devices') }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch, inject } from 'vue'
import { Dialog, createResource, Button, Spinner } from 'frappe-ui'
import { Monitor, Smartphone, Laptop, Trash2 } from 'lucide-vue-next'
import { showToast } from '@/utils'

const dayjs = inject('$dayjs')

const show = defineModel()
const removingDevice = ref(null)
const clearingAll = ref(false)

const props = defineProps({
	user: {
		type: String,
		required: true,
	},
})

const emit = defineEmits(['devices-cleared'])

const devices = createResource({
	url: 'lms.lms.api.admin_get_user_devices',
	makeParams() {
		return {
			user: props.user,
		}
	},
})

// Load devices when modal opens or user changes
watch(
	() => [show.value, props.user],
	([isOpen, user]) => {
		if (isOpen && user) {
			devices.submit({ user })
		}
	},
	{ immediate: true }
)

const removeDeviceResource = createResource({
	url: 'lms.lms.api.admin_remove_user_device',
	onSuccess() {
		showToast(__('Success'), __('Device removed successfully'), 'check')
		devices.submit({ user: props.user })
		removingDevice.value = null
	},
	onError(error) {
		showToast(__('Error'), error.messages?.[0] || __('Failed to remove device'), 'x')
		removingDevice.value = null
	},
})

const clearAllResource = createResource({
	url: 'lms.lms.api.admin_clear_user_devices',
	onSuccess(data) {
		showToast(__('Success'), data.message || __('All devices cleared'), 'check')
		devices.submit({ user: props.user })
		clearingAll.value = false
		emit('devices-cleared')
	},
	onError(error) {
		showToast(__('Error'), error.messages?.[0] || __('Failed to clear devices'), 'x')
		clearingAll.value = false
	},
})

const removeDevice = (deviceId) => {
	removingDevice.value = deviceId
	removeDeviceResource.submit({
		user: props.user,
		device_id: deviceId,
	})
}

const clearAllDevices = () => {
	clearingAll.value = true
	clearAllResource.submit({ user: props.user })
}

const formatDate = (dateString) => {
	if (!dateString) return ''
	const date = dayjs(dateString)
	const now = dayjs()
	const diffMinutes = now.diff(date, 'minute')
	const diffHours = now.diff(date, 'hour')
	const diffDays = now.diff(date, 'day')

	if (diffMinutes < 1) return __('Just now')
	if (diffMinutes < 60) return __('%s min ago', [diffMinutes])
	if (diffHours < 24) return __('%s hrs ago', [diffHours])
	if (diffDays < 7) return __('%s days ago', [diffDays])
	return date.format('DD MMM YYYY')
}

const isDesktop = (deviceName) => {
	if (!deviceName) return false
	return deviceName.includes('Windows') || deviceName.includes('Linux') || deviceName.includes('macOS')
}

const isMobile = (deviceName) => {
	if (!deviceName) return false
	return deviceName.includes('Android') || deviceName.includes('iOS')
}
</script>
