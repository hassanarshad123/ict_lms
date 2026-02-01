<template>
	<div class="mt-7">
		<h2 class="mb-3 text-lg font-semibold text-ink-gray-9">
			{{ __('Active Devices') }}
		</h2>
		<div
			v-if="devices.loading"
			class="flex items-center justify-center py-8"
		>
			<Spinner class="w-5 h-5" />
		</div>
		<div v-else-if="!devices.data?.devices?.length" class="text-sm text-ink-gray-5">
			{{ __('No active devices found.') }}
		</div>
		<div v-else class="space-y-3">
			<div
				v-if="devices.data?.device_limit_enabled"
				class="text-xs text-ink-gray-5 mb-2"
			>
				{{ __('Using') }} {{ devices.data.current_count }} {{ __('of') }} {{ devices.data.max_devices }} {{ __('allowed devices') }}
			</div>
			<div
				v-for="device in devices.data.devices"
				:key="device.device_id"
				class="p-4 border rounded-lg flex items-center justify-between"
			>
				<div class="flex items-center space-x-3">
					<Monitor class="w-5 h-5 text-ink-gray-5" />
					<div>
						<div class="text-sm font-medium text-ink-gray-9">
							{{ device.device_name || __('Unknown Device') }}
						</div>
						<div class="text-xs text-ink-gray-5 mt-0.5">
							{{ __('Last active') }}: {{ formatDate(device.last_active) }}
						</div>
						<div v-if="device.ip_address" class="text-xs text-ink-gray-4 mt-0.5">
							IP: {{ device.ip_address }}
						</div>
					</div>
				</div>
				<Badge
					v-if="device.is_current"
					variant="subtle"
					theme="green"
					size="sm"
				>
					{{ __('Current') }}
				</Badge>
			</div>
		</div>
		<p class="text-xs text-ink-gray-5 mt-4">
			{{ __('Contact an administrator if you need to remove a device.') }}
		</p>
	</div>
</template>

<script setup>
import { createResource, Spinner, Badge } from 'frappe-ui'
import { watch } from 'vue'
import { Monitor } from 'lucide-vue-next'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(relativeTime)

const props = defineProps({
	profile: {
		type: Object,
		required: true,
	},
})

const devices = createResource({
	url: 'lms.lms.api.get_my_devices',
	auto: false,
})

watch(
	() => props.profile,
	(newValue) => {
		if (newValue?.data?.name) {
			devices.reload()
		}
	},
	{ immediate: true }
)

const formatDate = (date) => {
	if (!date) return __('Never')
	return dayjs(date).fromNow()
}
</script>
