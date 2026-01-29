<template>
	<Dialog
		v-model="show"
		:options="{
			title: __('Add a Student'),
			size: 'sm',
			actions: [
				{
					label: 'Submit',
					variant: 'solid',
					onClick: (close) => addStudent(close),
				},
			],
		}"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<div class="space-y-1.5">
					<label class="block text-xs text-ink-gray-5">
						{{ __('Select User') }}
					</label>
					<Autocomplete
						ref="autocomplete"
						:options="userOptions"
						v-model="selectedUser"
						size="sm"
						:placeholder="__('Search by name or email...')"
						:filterable="false"
					>
						<template #footer="{ close }">
							<div>
								<Button
									variant="ghost"
									class="w-full !justify-start"
									:label="__('Create New User')"
									@click="() => { openSettings('Members', close); show = false }"
								>
									<template #prefix>
										<Plus class="h-4 w-4 stroke-1.5" />
									</template>
								</Button>
							</div>
						</template>
					</Autocomplete>
				</div>
			</div>
		</template>
	</Dialog>
</template>
<script setup>
import { Dialog, createResource, toast, Autocomplete, Button } from 'frappe-ui'
import { ref, inject, computed, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import { watchDebounced } from '@vueuse/core'
import { useOnboarding } from 'frappe-ui/frappe'
import { openSettings } from '@/utils'

const students = defineModel('reloadStudents')
const batchModal = defineModel('batchModal')
const selectedUser = ref(null)
const student = computed(() => selectedUser.value?.value || null)
const user = inject('$user')
const { updateOnboardingStep } = useOnboarding('learning')
const show = defineModel()
const autocomplete = ref(null)
const searchText = ref('')

const props = defineProps({
	batch: {
		type: String,
		default: null,
	},
})

// Watch for autocomplete query changes
watchDebounced(
	() => autocomplete.value?.query,
	(val) => {
		val = val || ''
		if (searchText.value === val) return
		searchText.value = val
		searchUsers.reload()
	},
	{ debounce: 300, immediate: true }
)

// Search users API
const searchUsers = createResource({
	url: 'lms.lms.api.search_users_for_batch',
	params: {
		txt: searchText.value,
		page_length: 20,
	},
	auto: true,
	transform: (data) => {
		return data.map((user) => ({
			label: user.label,
			value: user.value,
			description: user.description,
		}))
	},
})

// Update params when search text changes
watch(searchText, (val) => {
	searchUsers.update({
		params: {
			txt: val,
			page_length: 20,
		},
	})
})

const userOptions = computed(() => searchUsers.data || [])

const studentResource = createResource({
	url: 'frappe.client.insert',
	makeParams(values) {
		return {
			doc: {
				doctype: 'LMS Batch Enrollment',
				batch: props.batch,
				member: student.value,
			},
		}
	},
})

const addStudent = (close) => {
	if (!student.value) {
		toast.error(__('Please select a user'))
		return
	}
	studentResource.submit(
		{},
		{
			onSuccess() {
				if (user.data?.is_system_manager)
					updateOnboardingStep('add_batch_student')

				students.value.reload()
				batchModal.value.reload()
				selectedUser.value = null
				close()
			},
			onError(err) {
				toast.error(err.messages?.[0] || err)
			},
		}
	)
}
</script>
