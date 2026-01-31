<template>
	<div class="mt-7 mb-10">
		<div class="flex items-center justify-between mb-3">
			<h2 class="text-lg font-semibold text-ink-gray-9">
				{{ __('Logged In Devices') }}
			</h2>
			<div
				v-if="devices.data?.device_limit_enabled"
				class="text-sm text-ink-gray-7"
			>
				{{ devices.data?.current_count }} / {{ devices.data?.max_devices }}
				{{ __('devices') }}
			</div>
		</div>

		<div v-if="devices.loading" class="flex justify-center py-8">
			<Spinner class="w-6 h-6 text-ink-gray-5" />
		</div>

		<div v-else-if="!devices.data?.device_limit_enabled" class="text-ink-gray-7 text-sm italic">
			{{ __('Device tracking is not enabled.') }}
		</div>

		<div v-else-if="devices.data?.devices?.length === 0" class="text-ink-gray-7 text-sm italic">
			{{ __('No devices registered.') }}
		</div>

		<div v-else class="space-y-3">
			<div
				v-for="device in devices.data?.devices"
				:key="device.device_id"
				class="flex items-center justify-between p-4 bg-surface-gray-1 rounded-lg border"
				:class="device.is_current ? 'border-blue-300 bg-blue-50' : 'border-outline-gray-2'"
			>
				<div class="flex items-center space-x-4">
					<div class="p-2 bg-surface-white rounded-lg">
						<Monitor v-if="isDesktop(device.device_name)" class="w-6 h-6 text-ink-gray-7" />
						<Smartphone v-else-if="isMobile(device.device_name)" class="w-6 h-6 text-ink-gray-7" />
						<Laptop v-else class="w-6 h-6 text-ink-gray-7" />
					</div>
					<div>
						<div class="flex items-center space-x-2">
							<span class="font-medium text-ink-gray-9">
								{{ device.device_name || __('Unknown Device') }}
							</span>
							<Badge
								v-if="device.is_current"
								variant="success"
								size="sm"
								:label="__('Current')"
							/>
						</div>
						<div class="text-sm text-ink-gray-7 mt-1">
							<span v-if="device.ip_address">
								{{ __('IP') }}: {{ device.ip_address }}
							</span>
							<span v-if="device.ip_address && device.last_active" class="mx-2">|</span>
							<span v-if="device.last_active">
								{{ __('Last active') }}: {{ timeAgo(device.last_active) }}
							</span>
						</div>
					</div>
				</div>
			</div>
		</div>

		<div v-if="devices.data?.device_limit_enabled" class="mt-6 p-4 bg-surface-gray-1 rounded-lg">
			<h3 class="text-sm font-medium text-ink-gray-9 mb-2">
				{{ __('About Device Limits') }}
			</h3>
			<p class="text-sm text-ink-gray-7">
				{{ __('You can be logged in from up to {0} devices simultaneously. If you reach this limit, please contact your administrator to reset your device access.').format(devices.data?.max_devices) }}
			</p>
		</div>
	</div>
</template>

<script setup>
import { createResource, Badge, Spinner } from 'frappe-ui'
import { Monitor, Smartphone, Laptop } from 'lucide-vue-next'
import { timeAgo } from '@/utils'

const props = defineProps({
	profile: {
		type: Object,
		required: true,
	},
})

const devices = createResource({
	url: 'lms.lms.api.get_my_devices',
	auto: true,
})

const isDesktop = (deviceName) => {
	if (!deviceName) return false
	return deviceName.includes('Windows') || deviceName.includes('Linux') || deviceName.includes('macOS')
}

const isMobile = (deviceName) => {
	if (!deviceName) return false
	return deviceName.includes('Android') || deviceName.includes('iOS')
}
</script>
