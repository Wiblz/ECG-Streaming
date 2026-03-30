<script lang="ts">
	import type { DeviceInfo } from '$lib/types/api';
	import Badge from './Badge.svelte';

	interface Props {
		device: DeviceInfo;
	}

	let { device }: Props = $props();

	const syncLabel = $derived(device.sync_ready ? 'Synced' : 'Syncing...');
	const confidencePercent = $derived(
		device.sync?.confidence ? (device.sync.confidence * 100).toFixed(1) : 'N/A'
	);

	// Use badge variant for sync status
	const syncVariant = $derived(device.sync_ready ? 'success' : 'warning');
</script>

<div class="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
	<div class="flex items-center justify-between mb-3">
		<h3 class="text-sm font-medium text-gray-900">{device.device_id}</h3>
		<Badge variant={syncVariant} size="sm">
			{syncLabel}
		</Badge>
	</div>
	<dl class="space-y-1 text-sm">
		<div class="flex justify-between">
			<dt class="text-text-secondary">Confidence:</dt>
			<dd class="font-medium text-text">{confidencePercent}%</dd>
		</div>
		{#if device.sync?.sample_count}
			<div class="flex justify-between">
				<dt class="text-text-secondary">Samples:</dt>
				<dd class="font-medium text-text">{device.sync.sample_count.toLocaleString()}</dd>
			</div>
		{/if}
		{#if device.sync?.drift_ppm !== undefined}
			<div class="flex justify-between">
				<dt class="text-text-secondary">Drift:</dt>
				<dd class="font-medium text-text">{device.sync.drift_ppm.toFixed(2)} ppm</dd>
			</div>
		{/if}
	</dl>
</div>
