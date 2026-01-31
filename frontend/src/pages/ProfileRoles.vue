<template>
	<div class="mt-7">
		<h2 class="mb-3 text-lg font-semibold text-ink-gray-9">
			{{ __('Roles') }}
		</h2>
		<div
			v-if="readOnlyMode"
			class="flex items-center space-x-2 text-sm text-ink-gray-7 bg-surface-gray-1 px-3 py-2 rounded-md w-full text-center"
		>
			<CircleAlert class="size-4 stroke-1.5" />
			<span>
				{{ __('You cannot change the roles in read-only mode.') }}
			</span>
		</div>
		<div v-else class="space-y-4 mt-5">
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<div class="p-4 border rounded-lg">
					<FormControl
						:label="__('Admin')"
						v-model="admin"
						type="checkbox"
						@change.stop="changeRole('admin')"
					/>
					<p class="text-xs text-ink-gray-5 mt-1">
						{{ __('Full access to all LMS capabilities') }}
					</p>
				</div>
				<div class="p-4 border rounded-lg">
					<FormControl
						:label="__('Course Creator')"
						v-model="course_creator"
						type="checkbox"
						@change.stop="changeRole('course_creator')"
					/>
					<p class="text-xs text-ink-gray-5 mt-1">
						{{ __('Can create/edit courses, batches, and manage students') }}
					</p>
				</div>
				<div class="p-4 border rounded-lg">
					<FormControl
						:label="__('Teacher')"
						v-model="teacher"
						type="checkbox"
						@change.stop="changeRole('teacher')"
					/>
					<p class="text-xs text-ink-gray-5 mt-1">
						{{ __('Can view and teach assigned courses (read-only)') }}
					</p>
				</div>
				<div class="p-4 border rounded-lg">
					<FormControl
						:label="__('Student')"
						v-model="student"
						type="checkbox"
						@change.stop="changeRole('student')"
					/>
					<p class="text-xs text-ink-gray-5 mt-1">
						{{ __('Can view and consume enrolled course content') }}
					</p>
				</div>
			</div>
		</div>

		<!-- Device Management Section -->
		<div class="mt-8">
			<h2 class="mb-3 text-lg font-semibold text-ink-gray-9">
				{{ __('Device Management') }}
			</h2>
			<div class="p-4 border rounded-lg">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-medium text-ink-gray-9">
							{{ __('Logged In Devices') }}
						</p>
						<p class="text-xs text-ink-gray-5 mt-1">
							{{ __('View and manage devices this user is logged in from') }}
						</p>
					</div>
					<Button
						variant="outline"
						size="sm"
						@click="showDevicesModal = true"
					>
						<template #prefix>
							<Monitor class="w-4 h-4" />
						</template>
						{{ __('Manage Devices') }}
					</Button>
				</div>
			</div>
		</div>
	</div>

	<UserDevicesModal
		v-model="showDevicesModal"
		:user="props.profile.data?.name"
	/>
</template>
<script setup>
import { FormControl, createResource, toast, Button } from 'frappe-ui'
import { ref, watch } from 'vue'
import { CircleAlert, Monitor } from 'lucide-vue-next'
import UserDevicesModal from '@/components/Modals/UserDevicesModal.vue'

const admin = ref(false)
const course_creator = ref(false)
const teacher = ref(false)
const student = ref(false)
const showDevicesModal = ref(false)
const readOnlyMode = window.read_only_mode

const props = defineProps({
	profile: {
		type: Object,
		required: true,
	},
})

const roles = createResource({
	url: 'lms.lms.utils.get_roles',
	makeParams(values) {
		return {
			name: values.member,
		}
	},
	onSuccess(data) {
		// Map from API response to local state
		admin.value = !!data.admin
		course_creator.value = !!data.course_creator
		teacher.value = !!data.teacher
		student.value = !!data.student
	},
})

watch(
	() => props.profile,
	(newValue) => {
		if (newValue?.data?.name) {
			roles.reload({
				member: newValue.data.name,
			})
		}
	},
	{ immediate: true }
)

const updateRole = createResource({
	url: 'lms.lms.api.save_role',
	makeParams(values) {
		return {
			user: props.profile.data?.name,
			role: values.role,
			value: values.value,
		}
	},
})

// Map local variable names to API role names
const roleNameMapping = {
	admin: 'Admin',
	course_creator: 'Course Creator',
	teacher: 'Teacher',
	student: 'Student',
}

const changeRole = (role) => {
	const roleValues = { admin, course_creator, teacher, student }
	updateRole.submit(
		{
			role: roleNameMapping[role],
			value: roleValues[role].value,
		},
		{
			onSuccess() {
				toast.success(__('Role updated successfully'))
			},
			onError(err) {
				toast.error(err.messages?.[0] || __('Error updating role'))
			},
		}
	)
}
</script>
