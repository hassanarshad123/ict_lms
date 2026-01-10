<template>
	<div v-if="canViewRecordings" class="mt-20 mb-10">
		<div class="flex items-center justify-between">
			<div class="flex items-center font-semibold text-2xl text-ink-gray-9">
				{{ __('Live Class Recordings') }}
			</div>
			<Button
				v-if="canTriggerUpload && hasPendingLiveClasses"
				@click="openUploadModal"
				variant="subtle"
			>
				<template #prefix>
					<Upload class="h-4 w-4" />
				</template>
				{{ __('Upload Recording') }}
			</Button>
		</div>

		<div v-if="!membership && !isInstructor && !user.data?.is_moderator"
			class="mt-4 p-4 bg-surface-gray-1 rounded-md text-ink-gray-6 text-sm">
			{{ __('Enroll in this course to view recordings') }}
		</div>

		<div v-else-if="recordings.loading" class="mt-5">
			<div class="flex items-center justify-center py-10">
				<LoadingIndicator class="h-6 w-6" />
			</div>
		</div>

		<div v-else-if="recordings.data?.length"
			class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-5">
			<RecordingCard
				v-for="recording in recordings.data"
				:key="recording.name"
				:recording="recording"
				@play="openPlayerModal"
			/>
		</div>

		<div v-else class="text-sm italic text-ink-gray-5 mt-4">
			{{ __('No recordings available for this course yet') }}
		</div>

		<RecordingPlayerModal
			v-model="showPlayerModal"
			:recording="selectedRecording"
		/>

		<Dialog
			v-model="showUploadModal"
			:options="{
				title: __('Upload Recording'),
				size: 'md',
			}"
		>
			<template #body-content>
				<div class="flex flex-col gap-4">
					<FormControl
						:label="__('Select Live Class')"
						type="select"
						v-model="selectedLiveClass"
						:options="pendingLiveClasses"
					/>
					<div class="text-sm text-ink-gray-5">
						{{ __('This will fetch the recording from Zoom and upload it to Vimeo.') }}
					</div>
				</div>
			</template>
			<template #actions>
				<Button
					variant="solid"
					:loading="uploadTrigger.loading"
					@click="triggerUpload"
				>
					{{ __('Start Upload') }}
				</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { createResource, Button, Dialog, FormControl, LoadingIndicator } from 'frappe-ui'
import { computed, ref, inject } from 'vue'
import { Upload } from 'lucide-vue-next'
import RecordingCard from '@/components/RecordingCard.vue'
import RecordingPlayerModal from '@/components/Modals/RecordingPlayerModal.vue'

const user = inject('$user')

const props = defineProps({
	courseName: {
		type: String,
		required: true,
	},
	membership: {
		type: Object,
		required: false,
	},
	instructors: {
		type: Array,
		default: () => [],
	},
})

const showPlayerModal = ref(false)
const showUploadModal = ref(false)
const selectedRecording = ref(null)
const selectedLiveClass = ref('')

const recordings = createResource({
	url: 'lms.lms.api.get_course_recordings',
	cache: ['course_recordings', props.courseName],
	makeParams() {
		return {
			course: props.courseName,
		}
	},
	auto: true,
})

const liveClasses = createResource({
	url: 'frappe.client.get_list',
	makeParams() {
		return {
			doctype: 'LMS Live Class',
			filters: {
				batch_name: ['in', getBatchNames()],
			},
			fields: ['name', 'title', 'date', 'batch_name'],
			order_by: 'date desc',
		}
	},
})

const uploadTrigger = createResource({
	url: 'lms.lms.api.trigger_recording_upload',
})

const isInstructor = computed(() => {
	return props.instructors.some(instructor => instructor.name === user.data?.name)
})

const canViewRecordings = computed(() => {
	// Show section if user is enrolled, instructor, or moderator
	return props.membership || isInstructor.value || user.data?.is_moderator
})

const canTriggerUpload = computed(() => {
	// Only moderators and course creators can manually trigger uploads
	return user.data?.is_moderator
})

const hasPendingLiveClasses = computed(() => {
	return pendingLiveClasses.value.length > 0
})

const pendingLiveClasses = computed(() => {
	if (!liveClasses.data) return []
	return liveClasses.data.map(cls => ({
		label: `${cls.title} (${cls.date})`,
		value: cls.name,
	}))
})

function getBatchNames() {
	// This would need to be fetched from the course batches
	// For now, return empty array which will be handled by the backend
	return []
}

function openPlayerModal(recording) {
	selectedRecording.value = recording
	showPlayerModal.value = true
}

function openUploadModal() {
	liveClasses.fetch()
	showUploadModal.value = true
}

async function triggerUpload() {
	if (!selectedLiveClass.value) return

	await uploadTrigger.submit({
		live_class: selectedLiveClass.value,
	})

	showUploadModal.value = false
	recordings.reload()
}
</script>
