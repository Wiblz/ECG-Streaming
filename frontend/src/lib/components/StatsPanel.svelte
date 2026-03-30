<script lang="ts">
	import { statusEvents } from '$lib/state/status-events.svelte';
	import Card from './Card.svelte';

	// Use reactive state from SSE client
	let stats = $derived(statusEvents.bufferStats);
	let connectionStatus = $derived(statusEvents.connectionStatus);
</script>

<Card title="Statistics">
	{#if stats}
		{@const ecgStats = stats.ecg_buffer}
		{@const accStats = stats.acc_buffer}
		<dl class="grid grid-cols-2 gap-3">
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Samples</dt>
				<dd class="text-xl font-bold text-gray-900">
					{ecgStats.total_samples.toLocaleString()}
				</dd>
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Devices</dt>
				<dd class="text-xl font-bold text-gray-900">{ecgStats.device_count}</dd>
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">ECG Rate</dt>
				<dd class="text-xl font-bold text-gray-900">
					{ecgStats.samples_per_second.toFixed(1)} Hz
				</dd>
				{#if ecgStats.device_count > 1}
					<div class="mt-1 text-xs text-gray-400">
						{(ecgStats.samples_per_second / ecgStats.device_count).toFixed(1)} Hz avg/device
					</div>
				{/if}
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">ACC Rate</dt>
				<dd class="text-xl font-bold text-gray-900">
					{accStats.samples_per_second.toFixed(1)} Hz
				</dd>
				{#if accStats.device_count > 1}
					<div class="mt-1 text-xs text-gray-400">
						{(accStats.samples_per_second / accStats.device_count).toFixed(1)} Hz avg/device
					</div>
				{/if}
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Buffer</dt>
				<dd class="text-xl font-bold text-gray-900">
					{(ecgStats.buffer_utilization * 100).toFixed(1)}%
				</dd>
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Processed</dt>
				<dd class="text-xl font-bold text-gray-900">
					{ecgStats.total_processed.toLocaleString()}
				</dd>
			</div>
		</dl>
		<div class="mt-5 pt-4 border-t border-gray-200">
			<div class="flex items-center justify-between text-xs">
				<span class="text-gray-500">Buffer Duration</span>
				<span class="font-medium text-gray-900">{ecgStats.duration_seconds.toFixed(1)}s</span>
			</div>
		</div>
	{:else}
		<div class="flex items-center justify-center py-8">
			<div class="text-center">
				{#if connectionStatus === 'error'}
					<p class="text-sm text-status-error-fg">Connection error</p>
					<p class="text-xs text-text-muted mt-1">Check console for details</p>
				{:else if connectionStatus === 'disconnected'}
					<p class="text-sm text-status-warning-fg">Disconnected</p>
					<p class="text-xs text-text-muted mt-1">Reconnecting...</p>
				{:else}
					<div
						class="inline-block w-8 h-8 border-4 border-gray-200 border-t-gray-600 rounded-full animate-spin"
					></div>
					<p class="text-sm text-text-secondary mt-2">
						Loading stats... ({connectionStatus})
					</p>
				{/if}
			</div>
		</div>
	{/if}
</Card>
