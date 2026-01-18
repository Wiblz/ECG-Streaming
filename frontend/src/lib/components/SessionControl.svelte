<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import { getActiveSession, isRecording, setActiveSession } from '$lib/state/session.svelte';
	import SessionDuration from './SessionDuration.svelte';

	const recording = $derived(isRecording());
	const activeSession = $derived(getActiveSession());

	let notes = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	// Load active session on mount
	onMount(async () => {
		try {
			const response = await api.getActiveSession();
			if (response.active && response.session) {
				setActiveSession(response.session);
			}
		} catch (err) {
			console.error('[SessionControl] Failed to load active session:', err);
		}
	});

	async function handleStart() {
		loading = true;
		error = null;
		try {
			const response = await api.startSession(notes || null);
			if (response.success && response.session_id) {
				// Fetch the full session details
				const session = await api.getSession(response.session_id);
				setActiveSession(session);
				notes = '';
				console.log(`[SessionControl] Session ${response.session_id} started`);
			} else {
				error = response.error || 'Failed to start session';
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to start session';
			console.error('[SessionControl] Error starting session:', err);
		} finally {
			loading = false;
		}
	}

	async function handleStop() {
		loading = true;
		error = null;
		try {
			const response = await api.stopSession();
			if (response.success) {
				setActiveSession(null);
				console.log(`[SessionControl] Session ${response.session_id} stopped`);
			} else {
				error = response.error || 'Failed to stop session';
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to stop session';
			console.error('[SessionControl] Error stopping session:', err);
		} finally {
			loading = false;
		}
	}
</script>

<div class="bg-white rounded-lg border border-gray-200 p-4">
	<div class="flex items-center justify-between mb-3">
		<h3 class="text-sm font-semibold text-gray-900">Recording Session</h3>
		{#if recording}
			<div class="flex items-center gap-2">
				<div class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
				<span class="text-xs font-medium text-red-600">Recording</span>
			</div>
		{:else}
			<div class="flex items-center gap-2">
				<div class="w-2 h-2 bg-gray-400 rounded-full"></div>
				<span class="text-xs font-medium text-gray-500">Not Recording</span>
			</div>
		{/if}
	</div>

	{#if error}
		<div class="mb-3 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
			{error}
		</div>
	{/if}

	{#if recording && activeSession}
		<div class="space-y-3">
			<div class="text-xs space-y-2">
				<div class="flex justify-between">
					<span class="text-gray-500">Session ID:</span>
					<span class="font-medium text-gray-900">#{activeSession.id}</span>
				</div>
				<div class="flex justify-between">
					<span class="text-gray-500">Started:</span>
					<span class="font-medium text-gray-900">
						{new Date(activeSession.start_time * 1000).toLocaleTimeString()}
					</span>
				</div>
				<div class="pt-1">
					<SessionDuration startTime={activeSession.start_time} />
				</div>
				{#if activeSession.notes}
					<div class="pt-1">
						<span class="text-gray-500">Notes:</span>
						<p class="text-gray-900 mt-1">{activeSession.notes}</p>
					</div>
				{/if}
			</div>

			<button
				onclick={handleStop}
				disabled={loading}
				class="w-full px-4 py-2 bg-red-500 hover:bg-red-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
			>
				{loading ? 'Stopping...' : 'Stop Recording'}
			</button>
		</div>
	{:else}
		<div class="space-y-3">
			<div>
				<label for="session-notes" class="block text-xs font-medium text-gray-700 mb-1">
					Notes (optional)
				</label>
				<input
					id="session-notes"
					type="text"
					bind:value={notes}
					placeholder="e.g., Exercise test, resting ECG..."
					class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
					disabled={loading}
				/>
			</div>

			<button
				onclick={handleStart}
				disabled={loading}
				class="w-full px-4 py-2 bg-green-500 hover:bg-green-600 disabled:bg-gray-300 text-white text-sm font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
			>
				{loading ? 'Starting...' : 'Start Recording'}
			</button>

			<p class="text-xs text-gray-500">
				Start recording to save samples to the database. Samples will continue streaming to the
				dashboard whether or not recording is active.
			</p>
		</div>
	{/if}
</div>
