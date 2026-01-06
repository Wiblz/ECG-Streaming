<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { getDeviceStatus, getCollectors } from '$lib/api/client';
	import type { DeviceStatus, Collector } from '$lib/types/api';
	import { formatTimeSince, formatUptime } from '$lib/utils/format';

	let devices = $state<DeviceStatus[]>([]);
	let collectors = $state<Collector[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let intervalId: number | undefined;

	async function fetchData() {
		try {
			const [devicesResponse, collectorsResponse] = await Promise.all([
				getDeviceStatus(),
				getCollectors()
			]);

			if (devicesResponse.error) {
				error = devicesResponse.error;
			} else if (collectorsResponse.error) {
				error = collectorsResponse.error;
			} else {
				devices = devicesResponse.devices;
				collectors = collectorsResponse.collectors;
				error = null;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to fetch status';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		fetchData();
		// Refresh status every 5 seconds
		intervalId = setInterval(fetchData, 5000) as unknown as number;
	});

	onDestroy(() => {
		if (intervalId !== undefined) {
			clearInterval(intervalId);
		}
	});

	// Helper functions for color mapping
	function getDeviceStatusColors(status: DeviceStatus['status']) {
		switch (status) {
			case 'STREAMING':
				return {
					bg: 'bg-status-success',
					text: 'text-status-success-fg',
					border: 'border-status-success-border'
				};
			case 'CONNECTED':
				return {
					bg: 'bg-status-info',
					text: 'text-status-info-fg',
					border: 'border-status-info-border'
				};
			case 'CONNECTING':
				return {
					bg: 'bg-status-warning',
					text: 'text-status-warning-fg',
					border: 'border-status-warning-border'
				};
			case 'ERROR':
				return {
					bg: 'bg-status-error',
					text: 'text-status-error-fg',
					border: 'border-status-error-border'
				};
			case 'DISCONNECTED':
			case 'UNKNOWN':
			default:
				return {
					bg: 'bg-status-neutral',
					text: 'text-status-neutral-fg',
					border: 'border-status-neutral-border'
				};
		}
	}

	function getCollectorHealthColors(health: Collector['health']) {
		switch (health) {
			case 'healthy':
				return {
					badge: 'bg-status-success-fg',
					badgeText: 'text-white'
				};
			case 'warning':
				return {
					badge: 'bg-status-warning-fg',
					badgeText: 'text-white'
				};
			case 'disconnected':
				return {
					badge: 'bg-status-error-fg',
					badgeText: 'text-white'
				};
			default:
				return {
					badge: 'bg-status-neutral-fg',
					badgeText: 'text-white'
				};
		}
	}

	// Group devices by collector with collector info
	const groupedDevices = $derived.by(() => {
		const groups: Record<
			string,
			{ name: string; devices: DeviceStatus[]; collector: Collector | null }
		> = {};

		for (const device of devices) {
			const collectorKey = device.collector_id || 'unknown';
			const collectorName = device.collector_name || device.collector_id || 'Unknown Collector';

			if (!groups[collectorKey]) {
				// Find matching collector info
				const collectorInfo = collectors.find((c) => c.collector_id === collectorKey) || null;
				groups[collectorKey] = { name: collectorName, devices: [], collector: collectorInfo };
			}
			groups[collectorKey].devices.push(device);
		}

		return Object.entries(groups).map(([id, group]) => ({
			collector_id: id,
			collector_name: group.name,
			devices: group.devices,
			collector: group.collector
		}));
	});
</script>

<div class="bg-white border border-gray-200 rounded-xl shadow-lg">
	<div class="px-6 py-4 border-b border-gray-200">
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-gray-900">Device Status</h2>
			<span class="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
				{devices.length}
				{devices.length === 1 ? 'device' : 'devices'}
			</span>
		</div>
	</div>

	<div class="p-6">
		{#if loading}
			<div class="flex items-center justify-center py-8">
				<div
					class="inline-block w-8 h-8 border-4 border-gray-200 border-t-gray-600 rounded-full animate-spin"
				></div>
			</div>
		{:else if error}
			<div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
				<p class="text-amber-800 text-sm font-medium">
					{error}
				</p>
			</div>
		{:else if devices.length === 0}
			<div class="text-center py-8">
				<div class="text-4xl mb-2">🔌</div>
				<p class="text-sm font-medium text-gray-900 mb-1">No devices configured</p>
				<p class="text-xs text-gray-500">Check collector configuration</p>
			</div>
		{:else}
			<div class="space-y-4">
				{#each groupedDevices as collector (collector.collector_id)}
					<div>
						<!-- Collector Header -->
						<div class="flex items-center gap-2 mb-2 px-1">
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2">
									<h3 class="text-sm font-semibold text-gray-900 truncate">
										{collector.collector_name}
									</h3>
									{#if collector.collector}
										{@const healthColors = getCollectorHealthColors(collector.collector.health)}
										<span
											class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {healthColors.badge} {healthColors.badgeText}"
										>
											{collector.collector.health}
										</span>
									{/if}
								</div>
								<div class="flex items-center gap-3 text-xs text-gray-500 mt-1">
									<span>
										{collector.devices.length}
										{collector.devices.length === 1 ? 'device' : 'devices'}
									</span>
									{#if collector.collector}
										<span>
											{collector.collector.active_devices} active
										</span>
										<span>
											{collector.collector.samples_sent.toLocaleString()} samples
										</span>
										<span>
											⏱️ {formatUptime(collector.collector.time_since_heartbeat)} ago
										</span>
									{/if}
								</div>
							</div>
						</div>

						<!-- Devices in this collector -->
						<div class="space-y-2 pl-2 border-l-2 border-gray-200">
							{#each collector.devices as device (device.device_id)}
								{@const colors = getDeviceStatusColors(device.status)}
								<div class="border {colors.border} rounded-lg p-3 {colors.bg}">
									<div class="flex items-start justify-between mb-2">
										<div class="flex-1 min-w-0">
											<h4 class="text-sm font-mono font-semibold {colors.text} truncate">
												{device.device_id}
											</h4>
										</div>
										<span
											class="flex-shrink-0 text-xs font-bold px-2 py-1 rounded {colors.bg} {colors.text} {colors.border} border ml-2"
										>
											{device.status}
										</span>
									</div>

									<div class="flex items-center gap-4 text-xs text-gray-600 mt-2">
										<div class="flex items-center gap-1">
											<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
												<path
													fill-rule="evenodd"
													d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
													clip-rule="evenodd"
												/>
											</svg>
											<span>{formatTimeSince(device.last_update)}</span>
										</div>

										{#if device.battery_level !== null}
											<div class="flex items-center gap-1">
												<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
													<path
														d="M5 4a2 2 0 00-2 2v6a2 2 0 002 2h8a2 2 0 002-2V6a2 2 0 00-2-2H5zm9 10H4V6h10v8zm3-6v4h1V8h-1z"
													/>
												</svg>
												<span>{device.battery_level}%</span>
											</div>
										{/if}
									</div>

									{#if device.error_message}
										<div class="mt-2 pt-2 border-t border-red-200">
											<p class="text-xs text-red-600 font-medium">{device.error_message}</p>
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
