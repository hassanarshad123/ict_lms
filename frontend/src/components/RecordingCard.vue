<template>
	<div
		class="flex flex-col border rounded-md h-full text-ink-gray-7 hover:border-outline-gray-3 overflow-hidden"
	>
		<!-- Thumbnail -->
		<div class="relative aspect-video bg-surface-gray-2">
			<img
				v-if="recording.thumbnail"
				:src="recording.thumbnail"
				:alt="recording.title"
				class="w-full h-full object-cover"
			/>
			<div
				v-else
				class="w-full h-full flex items-center justify-center"
			>
				<Video class="h-12 w-12 text-ink-gray-4" />
			</div>

			<!-- Play overlay -->
			<div
				v-if="isReady"
				@click="$emit('play', recording)"
				class="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 hover:opacity-100 transition-opacity cursor-pointer"
			>
				<div class="rounded-full bg-white/90 p-3">
					<Play class="h-8 w-8 text-ink-gray-9 fill-current" />
				</div>
			</div>

			<!-- Status badge -->
			<div class="absolute top-2 right-2">
				<Badge
					v-if="recording.status === 'Processing'"
					theme="orange"
					size="sm"
				>
					<template #prefix>
						<LoadingIndicator class="h-3 w-3" />
					</template>
					{{ __('Processing') }}
				</Badge>
				<Badge
					v-else-if="recording.status === 'Failed'"
					theme="red"
					size="sm"
				>
					{{ __('Failed') }}
				</Badge>
				<Badge
					v-else-if="recording.status === 'Pending'"
					theme="gray"
					size="sm"
				>
					{{ __('Pending') }}
				</Badge>
			</div>

			<!-- Duration -->
			<div
				v-if="recording.duration && isReady"
				class="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded"
			>
				{{ formatDuration(recording.duration) }}
			</div>
		</div>

		<!-- Content -->
		<div class="p-3 flex flex-col flex-1">
			<div class="font-semibold text-ink-gray-9 text-base mb-1 line-clamp-2">
				{{ recording.title }}
			</div>

			<div class="text-sm text-ink-gray-5 mt-auto space-y-2">
				<div class="flex items-center space-x-2">
					<Calendar class="w-4 h-4 stroke-1.5" />
					<span>
						{{ formatDate(recording.recorded_on) }}
					</span>
				</div>
			</div>

			<Button
				v-if="isReady"
				@click="$emit('play', recording)"
				class="mt-3 w-full"
				variant="subtle"
			>
				<template #prefix>
					<Play class="h-4 w-4" />
				</template>
				{{ __('Watch') }}
			</Button>

			<div
				v-else-if="recording.status === 'Processing'"
				class="mt-3 text-sm text-ink-gray-5 text-center"
			>
				{{ __('Recording is being processed...') }}
			</div>

			<div
				v-else-if="recording.status === 'Failed'"
				class="mt-3 text-sm text-ink-red-3 text-center"
			>
				{{ __('Upload failed') }}
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Video, Play, Calendar } from 'lucide-vue-next'
import { Button, Badge, LoadingIndicator } from 'frappe-ui'

const dayjs = inject('$dayjs')

const props = defineProps({
	recording: {
		type: Object,
		required: true,
	},
})

defineEmits(['play'])

const isReady = computed(() => {
	return props.recording.status === 'Uploaded' && props.recording.vimeo_player_embed_url
})

function formatDuration(seconds) {
	if (!seconds) return ''
	const hours = Math.floor(seconds / 3600)
	const minutes = Math.floor((seconds % 3600) / 60)
	const secs = seconds % 60

	if (hours > 0) {
		return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
	}
	return `${minutes}:${String(secs).padStart(2, '0')}`
}

function formatDate(date) {
	if (!date) return ''
	return dayjs(date).format('DD MMM YYYY')
}
</script>

<style scoped>
.line-clamp-2 {
	display: -webkit-box;
	-webkit-line-clamp: 2;
	-webkit-box-orient: vertical;
	overflow: hidden;
}
</style>
