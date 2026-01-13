<template>
	<Dialog
		v-model="show"
		:options="{
			size: '4xl',
			title: recording?.title || __('Recording'),
		}"
	>
		<template #body-content>
			<div class="relative">
				<!-- Video Player -->
				<div v-if="embedUrl" class="aspect-video w-full bg-black rounded-md overflow-hidden">
					<iframe
						:src="embedUrl"
						class="w-full h-full"
						frameborder="0"
						allow="autoplay; fullscreen; picture-in-picture"
						allowfullscreen
					></iframe>
				</div>

				<div v-else class="aspect-video w-full bg-surface-gray-2 rounded-md flex items-center justify-center">
					<div class="text-center text-ink-gray-5">
						<Video class="h-12 w-12 mx-auto mb-2" />
						<p>{{ __('Video not available') }}</p>
					</div>
				</div>

				<!-- Recording Info -->
				<div class="mt-4 flex items-center justify-between text-sm text-ink-gray-6">
					<div class="flex items-center space-x-4">
						<div v-if="recording?.recorded_on" class="flex items-center space-x-1">
							<Calendar class="h-4 w-4" />
							<span>{{ formatDate(recording.recorded_on) }}</span>
						</div>
						<div v-if="recording?.duration" class="flex items-center space-x-1">
							<Clock class="h-4 w-4" />
							<span>{{ formatDuration(recording.duration) }}</span>
						</div>
						<div v-if="recording?.instructor_name" class="flex items-center space-x-1">
							<User class="h-4 w-4" />
							<span>{{ recording.instructor_name }}</span>
						</div>
					</div>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { Dialog } from 'frappe-ui'
import { computed, inject } from 'vue'
import { Video, Calendar, Clock, User } from 'lucide-vue-next'

const dayjs = inject('$dayjs')
const show = defineModel()

const props = defineProps({
	recording: {
		type: Object,
		default: null,
	},
})

const embedUrl = computed(() => {
	if (!props.recording?.vimeo_player_embed_url) return null

	// Add parameters to disable download and sharing
	const url = new URL(props.recording.vimeo_player_embed_url)
	url.searchParams.set('title', '0')
	url.searchParams.set('byline', '0')
	url.searchParams.set('portrait', '0')
	url.searchParams.set('badge', '0')
	url.searchParams.set('dnt', '1')  // Do not track
	url.searchParams.set('transparent', '0')

	return url.toString()
})

function formatDuration(seconds) {
	if (!seconds) return ''
	const hours = Math.floor(seconds / 3600)
	const minutes = Math.floor((seconds % 3600) / 60)
	const secs = seconds % 60

	if (hours > 0) {
		return `${hours}h ${minutes}m`
	}
	if (minutes > 0) {
		return `${minutes}m ${secs}s`
	}
	return `${secs}s`
}

function formatDate(date) {
	if (!date) return ''
	return dayjs(date).format('DD MMM YYYY')
}
</script>
