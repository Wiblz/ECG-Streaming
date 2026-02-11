<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import Header from '$lib/components/Header.svelte';
	import { formatDuration, formatTimestamp } from '$lib/utils/format';
	import { createDeviceNicknameMap, getDisplayNameFromMap } from '$lib/utils/device-names';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const deviceNicknameMap = $derived(createDeviceNicknameMap(data.devices));

	// Local reactive copy of sessions that we can update - use $state since we're mutating it
	let sessions = $state(data.sessions);

	let importing = $state(false);
	let importMessage = $state<string | null>(null);
	let fileInput: HTMLInputElement;
	let deletingId = $state<number | null>(null);

	function handleImportClick() {
		fileInput.click();
	}

	async function handleFileSelected(event: Event) {
		const target = event.target as HTMLInputElement;
		const file = target.files?.[0];

		if (!file) return;

		importing = true;
		importMessage = null;

		try {
			const result = await api.importSession(file);

			if (result.success && result.session_id) {
				importMessage = `Successfully imported session #${result.session_id}`;
				// Reload sessions list to show the new one
				const response = await api.getSessions();
				sessions = response.sessions;
				// Navigate to the new session after a brief delay
				setTimeout(() => {
					goto(`/sessions/${result.session_id}`);
				}, 1000);
			} else {
				importMessage = result.error || 'Failed to import session';
			}
		} catch (e) {
			importMessage = e instanceof Error ? e.message : 'Import failed';
		} finally {
			importing = false;
			target.value = ''; // Reset file input
		}
	}

	async function handleDelete(sessionId: number, event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();

		if (!confirm(`Are you sure you want to delete session #${sessionId}? This cannot be undone.`)) {
			return;
		}

		deletingId = sessionId;

		try {
			const result = await api.deleteSession(sessionId);
			if (result.success) {
				// Remove the deleted session from the local state
				sessions = sessions.filter((s) => s.id !== sessionId);
				importMessage = `Session #${sessionId} deleted successfully`;
				// Auto-dismiss success message after 3 seconds
				setTimeout(() => {
					importMessage = null;
				}, 3000);
			} else {
				importMessage = `Failed to delete session #${sessionId}`;
				// Auto-dismiss error message after 5 seconds
				setTimeout(() => {
					importMessage = null;
				}, 5000);
			}
		} catch (e) {
			importMessage = e instanceof Error ? e.message : 'Delete failed';
			// Auto-dismiss error message after 5 seconds
			setTimeout(() => {
				importMessage = null;
			}, 5000);
		} finally {
			deletingId = null;
		}
	}
</script>

<svelte:head>
	<title>Sessions - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-gray-50 to-gray-100">
	<Header>
		<!-- Import Button -->
		<input
			type="file"
			accept=".csv"
			bind:this={fileInput}
			onchange={handleFileSelected}
			class="hidden"
		/>
		<button
			onclick={handleImportClick}
			disabled={importing}
			class="flex items-center gap-2 px-4 py-2 bg-status-success-fg hover:bg-status-success-border disabled:bg-gray-400 text-white text-sm font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
		>
			<svg
				class="w-4 h-4"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
				xmlns="http://www.w3.org/2000/svg"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
				/>
			</svg>
			{importing ? 'Importing...' : 'Import CSV'}
		</button>
	</Header>

	<!-- Toast Notification -->
	{#if importMessage}
		<div class="fixed top-20 left-1/2 -translate-x-1/2 z-50 animate-slide-down">
			<div
				class="px-6 py-4 rounded-lg shadow-xl {importMessage.includes('Success')
					? 'bg-status-success border border-status-success-border'
					: 'bg-status-error border border-status-error-border'}"
			>
				<p
					class="text-sm font-medium {importMessage.includes('Success')
						? 'text-status-success-fg'
						: 'text-status-error-fg'}"
				>
					{importMessage}
				</p>
			</div>
		</div>
	{/if}

	<main class="container mx-auto px-6 py-8 max-w-7xl">
		{#if sessions.length === 0}
			<div class="bg-white border border-gray-200 rounded-xl shadow-sm p-12 text-center">
				<div class="text-6xl mb-4">📊</div>
				<h3 class="text-lg font-semibold text-gray-900 mb-2">No sessions found</h3>
				<p class="text-sm text-gray-500">Start recording to create your first session</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
				{#each sessions as session (session.id)}
					<div
						class="bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-lg transition-shadow"
					>
						<div class="p-6">
							<div class="flex items-center justify-between mb-4 gap-2">
								<a href="/sessions/{session.id}" class="flex-1 min-w-0">
									<h3
										class="text-lg font-semibold text-gray-900 hover:text-blue-600 transition-colors"
									>
										Session #{session.id}
									</h3>
									<p class="text-xs text-gray-500 mt-1">
										{formatTimestamp(session.start_time)}
									</p>
								</a>
								<div class="flex items-center gap-2 flex-shrink-0">
									<div
										class="bg-status-success text-status-success-fg text-xs font-medium px-2 py-1 rounded-full"
									>
										{session.sample_count.toLocaleString()} samples
									</div>
									<button
										onclick={(e) => handleDelete(session.id, e)}
										disabled={deletingId === session.id}
										class="p-2 text-gray-400 hover:text-status-error-fg hover:bg-status-error rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
										title="Delete session"
									>
										{#if deletingId === session.id}
											<div
												class="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"
											></div>
										{:else}
											<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
												/>
											</svg>
										{/if}
									</button>
								</div>
							</div>

							<a href="/sessions/{session.id}" class="block">
								<div class="space-y-3">
									{#if session.notes}
										<div class="text-sm">
											<p class="text-gray-700 italic line-clamp-2">"{session.notes}"</p>
										</div>
									{/if}

									<div class="flex items-center justify-between text-sm">
										<span class="text-gray-500">Duration</span>
										<span class="font-medium text-gray-900">
											{formatDuration(session.duration_seconds)}
										</span>
									</div>

									<div class="flex items-center justify-between text-sm">
										<span class="text-gray-500">Devices</span>
										<span class="font-medium text-gray-900">{session.device_count}</span>
									</div>

									{#if session.devices.length > 0}
										<div class="pt-3 border-t border-gray-100">
											<div class="flex flex-wrap gap-2">
												{#each session.devices as deviceId (deviceId)}
													{@const displayName = getDisplayNameFromMap(deviceId, deviceNicknameMap)}
													<span
														class="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded-md"
														title={deviceId !== displayName ? deviceId : undefined}
													>
														{displayName}
													</span>
												{/each}
											</div>
										</div>
									{/if}
								</div>

								<div class="mt-4 pt-4 border-t border-gray-100">
									<span class="text-sm text-blue-600 font-medium hover:text-blue-700">
										View Recording →
									</span>
								</div>
							</a>
						</div>
					</div>
				{/each}
			</div>

			<div class="mt-8 text-center text-sm text-gray-500">
				Showing {sessions.length} session{sessions.length === 1 ? '' : 's'}
			</div>
		{/if}
	</main>
</div>
