<template>
	<div class="flex min-h-0 flex-col text-base">
		<div class="flex items-center justify-between">
			<div>
				<div class="text-xl font-semibold mb-1 text-ink-gray-9">
					{{ __(label) }}
				</div>
				<div class="text-ink-gray-6 leading-5">
					{{ __(description) }}
				</div>
			</div>
			<div class="flex items-center space-x-2">
				<Button @click="downloadTemplate">
					<template #prefix>
						<Download class="size-4 stroke-1.5" />
					</template>
					{{ __('Download Template') }}
				</Button>
			</div>
		</div>

		<div class="mt-8 pb-10">
			<div class="space-y-6">
				<!-- File Upload -->
				<div>
					<div class="text-sm font-medium text-ink-gray-7 mb-2">
						{{ __('Upload CSV File') }}
					</div>
					<FileUploader
						:fileTypes="['.csv']"
						@success="onFileUpload"
					>
						<template
							v-slot="{ file, progress, uploading, openFileSelector }"
						>
							<div
								v-if="!uploadedFile"
								class="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-ink-gray-4 transition-colors"
								@click="openFileSelector"
							>
								<Upload
									class="size-8 stroke-1 text-ink-gray-5 mx-auto mb-2"
								/>
								<div class="text-sm text-ink-gray-7">
									{{ __('Click to upload a CSV file') }}
								</div>
								<div class="text-xs text-ink-gray-5 mt-1">
									{{
										__(
											'CSV must have columns: email, password'
										)
									}}
								</div>
							</div>
							<div v-else>
								<div
									class="flex items-center justify-between border rounded-lg p-3"
								>
									<div class="flex items-center space-x-3">
										<FileText
											class="size-5 stroke-1.5 text-ink-gray-7"
										/>
										<div>
											<div
												class="text-sm text-ink-gray-9"
											>
												{{ uploadedFile.file_name }}
											</div>
										</div>
									</div>
									<Button
										variant="ghost"
										@click.stop="clearFile"
									>
										<template #icon>
											<X
												class="size-4 stroke-1.5 text-ink-gray-5"
											/>
										</template>
									</Button>
								</div>
							</div>
							<div v-if="uploading" class="mt-2">
								<div
									class="h-1.5 bg-surface-gray-3 rounded-full overflow-hidden"
								>
									<div
										class="h-full bg-blue-500 rounded-full transition-all"
										:style="{ width: `${progress}%` }"
									></div>
								</div>
							</div>
						</template>
					</FileUploader>
				</div>

				<!-- Submit button -->
				<Button
					variant="solid"
					:disabled="!uploadedFile || submitting"
					:loading="submitting"
					@click="submitPasswords"
				>
					{{ __('Update Passwords') }}
				</Button>

				<!-- Results -->
				<div v-if="result" class="mt-4 space-y-4">
					<div class="flex items-center space-x-4">
						<div
							class="flex items-center space-x-2 bg-green-50 text-green-700 px-3 py-2 rounded-md"
						>
							<CheckCircle2 class="size-4 stroke-1.5" />
							<span class="text-sm font-medium">
								{{
									__("{0} passwords updated successfully", [
										result.passwords_set,
									])
								}}
							</span>
						</div>
						<div
							v-if="result.failed > 0"
							class="flex items-center space-x-2 bg-red-50 text-red-700 px-3 py-2 rounded-md"
						>
							<AlertCircle class="size-4 stroke-1.5" />
							<span class="text-sm font-medium">
								{{ __("{0} failed", [result.failed]) }}
							</span>
						</div>
					</div>

					<!-- Failed rows table -->
					<div
						v-if="
							result.details?.failed &&
							result.details.failed.length > 0
						"
					>
						<div
							class="text-sm font-medium text-ink-gray-7 mb-2"
						>
							{{ __('Failed Rows') }}
						</div>
						<div class="border rounded-lg overflow-hidden">
							<table class="w-full text-sm">
								<thead class="bg-surface-gray-2">
									<tr>
										<th
											class="px-3 py-2 text-left text-ink-gray-7 font-medium"
										>
											{{ __('Row') }}
										</th>
										<th
											class="px-3 py-2 text-left text-ink-gray-7 font-medium"
										>
											{{ __('Email') }}
										</th>
										<th
											class="px-3 py-2 text-left text-ink-gray-7 font-medium"
										>
											{{ __('Reason') }}
										</th>
									</tr>
								</thead>
								<tbody class="divide-y">
									<tr
										v-for="fail in result.details.failed"
										:key="fail.row"
									>
										<td
											class="px-3 py-2 text-ink-gray-9"
										>
											{{ fail.row }}
										</td>
										<td
											class="px-3 py-2 text-ink-gray-9"
										>
											{{ fail.email || '—' }}
										</td>
										<td
											class="px-3 py-2 text-ink-red-3"
										>
											{{ fail.reason }}
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>
<script setup lang="ts">
import { Button, FileUploader, createResource } from 'frappe-ui'
import { ref } from 'vue'
import {
	Download,
	Upload,
	FileText,
	X,
	CheckCircle2,
	AlertCircle,
} from 'lucide-vue-next'

defineProps({
	label: {
		type: String,
		required: true,
	},
	description: {
		type: String,
		default: '',
	},
})

const uploadedFile = ref<{ file_url: string; file_name: string } | null>(null)
const submitting = ref(false)
const result = ref<{
	total: number
	passwords_set: number
	failed: number
	details: {
		success: { email: string }[]
		failed: { row: number; email: string; reason: string }[]
	}
} | null>(null)

const onFileUpload = (file: any) => {
	uploadedFile.value = {
		file_url: file.file_url,
		file_name: file.file_name,
	}
}

const clearFile = () => {
	uploadedFile.value = null
	result.value = null
}

const downloadTemplate = () => {
	window.open(
		'/api/method/lms.lms.api.download_bulk_password_template',
		'_blank'
	)
}

const bulkUpdate = createResource({
	url: 'lms.lms.api.admin_bulk_set_passwords_from_csv',
	onSuccess(data: any) {
		result.value = data
		submitting.value = false
	},
	onError() {
		submitting.value = false
	},
})

const submitPasswords = () => {
	if (!uploadedFile.value) return
	submitting.value = true
	result.value = null
	bulkUpdate.submit({
		file_url: uploadedFile.value.file_url,
	})
}
</script>
