<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import type { BufferStats } from '$lib/types/api';
	import Card from './Card.svelte';

	let stats = $state<BufferStats | null>(null);
	let interval: ReturnType<typeof setInterval>;

	async function fetchStats() {
		try {
			stats = await api.getBufferStats();
		} catch (error) {
			console.error('Failed to fetch stats:', error);
		}
	}

	onMount(() => {
		fetchStats();
		interval = setInterval(fetchStats, 5000); // Poll every 5 seconds

		return () => clearInterval(interval);
	});
</script>

<Card title="Statistics">
	{#if stats}
		<dl class="grid grid-cols-2 gap-3">
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Samples</dt>
				<dd class="text-xl font-bold text-gray-900">
					{stats.total_samples.toLocaleString()}
				</dd>
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Devices</dt>
				<dd class="text-xl font-bold text-gray-900">{stats.device_count}</dd>
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Buffer</dt>
				<dd class="text-xl font-bold text-gray-900">
					{(stats.buffer_utilization * 100).toFixed(1)}%
				</dd>
			</div>
			<div class="bg-gray-50 rounded-lg p-4">
				<dt class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Processed</dt>
				<dd class="text-xl font-bold text-gray-900">
					{stats.total_processed.toLocaleString()}
				</dd>
			</div>
		</dl>
		<div class="mt-5 pt-4 border-t border-gray-200">
			<div class="flex items-center justify-between text-xs">
				<span class="text-gray-500">Buffer Duration</span>
				<span class="font-medium text-gray-900">{stats.duration_seconds.toFixed(1)}s</span>
			</div>
		</div>
	{:else}
		<div class="flex items-center justify-center py-8">
			<div class="text-center">
				<div
					class="inline-block w-8 h-8 border-4 border-gray-200 border-t-gray-600 rounded-full animate-spin"
				></div>
				<p class="text-sm text-gray-500 mt-2">Loading stats...</p>
			</div>
		</div>
	{/if}
</Card>
