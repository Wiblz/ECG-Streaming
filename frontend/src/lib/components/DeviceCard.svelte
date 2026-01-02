<script lang="ts">
	import type { DeviceInfo } from '$lib/types/api';

	interface Props {
		device: DeviceInfo;
	}

	let { device }: Props = $props();

	const syncLabel = $derived(device.sync_ready ? 'Synced' : 'Syncing...');
	const confidencePercent = $derived(
		device.sync?.confidence ? (device.sync.confidence * 100).toFixed(1) : 'N/A'
	);
</script>

<div class="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
	<div class="flex items-center justify-between mb-3">
		<h3 class="text-sm font-medium text-gray-900">{device.device_id}</h3>
		<span
			class="px-2 py-1 text-xs rounded-full {device.sync_ready
				? 'bg-green-100 text-green-800'
				: 'bg-yellow-100 text-yellow-800'}"
		>
			{syncLabel}
		</span>
	</div>
	<dl class="space-y-1 text-sm">
		<div class="flex justify-between">
			<dt class="text-gray-500">Confidence:</dt>
			<dd class="font-medium text-gray-900">{confidencePercent}%</dd>
		</div>
		{#if device.sync?.sample_count}
			<div class="flex justify-between">
				<dt class="text-gray-500">Samples:</dt>
				<dd class="font-medium text-gray-900">{device.sync.sample_count.toLocaleString()}</dd>
			</div>
		{/if}
		{#if device.sync?.drift_ppm !== undefined}
			<div class="flex justify-between">
				<dt class="text-gray-500">Drift:</dt>
				<dd class="font-medium text-gray-900">{device.sync.drift_ppm.toFixed(2)} ppm</dd>
			</div>
		{/if}
	</dl>
</div>
