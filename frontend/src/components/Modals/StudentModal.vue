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
						:options="filteredUsers"
						v-model="selectedUser"
						size="sm"
						:placeholder="__('Search by name or email...')"
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

const props = defineProps({
	batch: {
		type: String,
		default: null,
	},
})

// Load all users on mount
const allUsers = createResource({
	url: 'lms.lms.api.get_all_users_for_batch',
	auto: true,
})

// Reload users when dialog opens
watch(show, (isOpen) => {
	if (isOpen) {
		allUsers.reload()
	}
})

// Filter users based on autocomplete query (client-side filtering)
const filteredUsers = computed(() => {
	const users = allUsers.data || []
	const query = autocomplete.value?.query?.toLowerCase() || ''

	if (!query) return users

	return users.filter(u =>
		u.label?.toLowerCase().includes(query) ||
		u.value?.toLowerCase().includes(query) ||
		u.description?.toLowerCase().includes(query)
	)
})

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
