<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { api } from '$lib/api/client';
	import Header from '$lib/components/Header.svelte';
	import { statusEvents } from '$lib/state/status-events.svelte';
	import type { Collector, DeviceInfo } from '$lib/types/api';
	import { formatTimeSince } from '$lib/utils/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Action to focus an element when it's mounted
	function focusElement(node: HTMLElement) {
		node.focus();
		return {};
	}

	// Track editing state for nicknames
	let editingDevice = $state<string | null>(null);
	let editingNickname = $state<string>('');
	let savingNickname = $state(false);

	// Filter and sort options
	let filterStatus = $state<'all' | 'connected' | 'disconnected'>('all');
	let sortBy = $state<'name' | 'last_seen' | 'total_samples'>('last_seen');

	async function startEditingNickname(deviceId: string, currentNickname: string | null) {
		editingDevice = deviceId;
		editingNickname = currentNickname || '';
	}

	function cancelEditingNickname() {
		editingDevice = null;
		editingNickname = '';
	}

	async function saveNickname(deviceId: string) {
		if (savingNickname) return;

		savingNickname = true;
		try {
			const nickname = editingNickname.trim() || null;
			await api.updateDeviceNickname(deviceId, nickname);

			// Reload data to reflect changes
			await invalidate(() => true);

			editingDevice = null;
			editingNickname = '';
		} finally {
			savingNickname = false;
		}
	}

	// Use SSE for real-time collector and device status updates
	let sseCollectors = $derived(statusEvents.getCollectors());
	let sseDevices = $derived(statusEvents.getDevices());

	// Create maps for quick lookup
	const sseDeviceMap = $derived(new Map(sseDevices.map((d) => [d.device_id, d])));
	const sseCollectorMap = $derived(new Map(sseCollectors.map((c) => [c.collector_id, c])));

	// Merge SSE status with initial load data
	const liveDevices = $derived.by(() => {
		return data.devices.map((device) => {
			const sseStatus = sseDeviceMap.get(device.device_id);
			if (sseStatus) {
				// Merge SSE status with device metadata from initial load
				return {
					...device,
					status: sseStatus.status,
					last_update: sseStatus.last_update,
					battery_level: sseStatus.battery_level,
					error_message: sseStatus.error_message,
					collector_id: sseStatus.collector_id
				} as DeviceInfo;
			}
			return device;
		});
	});

	const liveCollectors = $derived.by(() => {
		return data.collectors.map((collector) => {
			const sseCollector = sseCollectorMap.get(collector.collector_id);
			if (sseCollector) {
				// Merge SSE data with initial collector data
				return {
					...collector,
					connected: sseCollector.connected,
					health: sseCollector.health,
					samples_sent: sseCollector.samples_sent,
					active_devices: sseCollector.active_devices,
					last_heartbeat: sseCollector.last_heartbeat,
					time_since_heartbeat: sseCollector.time_since_heartbeat
				} as Collector;
			}
			return collector;
		});
	});

	// Helper functions for color mapping
	function getDeviceStatusColors(status: DeviceInfo['status']) {
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
				return 'bg-green-100 text-green-800 border-green-200';
			case 'warning':
				return 'bg-yellow-100 text-yellow-800 border-yellow-200';
			case 'disconnected':
				return 'bg-gray-100 text-gray-800 border-gray-200';
			default:
				return 'bg-gray-100 text-gray-800 border-gray-200';
		}
	}

	// Filtered and sorted devices (using live data from SSE)
	const filteredDevices = $derived.by(() => {
		let filtered = liveDevices;

		// Apply status filter
		if (filterStatus === 'connected') {
			filtered = filtered.filter(
				(d) => d.status && d.status !== 'DISCONNECTED' && d.status !== 'UNKNOWN'
			);
		} else if (filterStatus === 'disconnected') {
			filtered = filtered.filter(
				(d) => !d.status || d.status === 'DISCONNECTED' || d.status === 'UNKNOWN'
			);
		}

		// Apply sorting
		filtered = [...filtered].sort((a, b) => {
			switch (sortBy) {
				case 'name': {
					const nameA = a.nickname || a.device_id;
					const nameB = b.nickname || b.device_id;
					return nameA.localeCompare(nameB);
				}
				case 'last_seen':
					return (b.last_seen || 0) - (a.last_seen || 0);
				case 'total_samples':
					return (b.total_samples || 0) - (a.total_samples || 0);
				default:
					return 0;
			}
		});

		return filtered;
	});

	const collectorMap = $derived(new Map(liveCollectors.map((c) => [c.collector_id, c])));
</script>

<svelte:head>
	<title>Devices - ECG Streaming</title>
</svelte:head>

<Header />

<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
	<!-- Page Header -->
	<div class="mb-8">
		<h1 class="text-3xl font-bold text-gray-900">Device Management</h1>
		<p class="mt-2 text-sm text-gray-600">
			Manage devices, assign nicknames, and view collector status
		</p>
	</div>

	<!-- Collectors Summary -->
	{#if liveCollectors.length > 0}
		<div class="mb-8">
			<h2 class="text-lg font-semibold text-gray-900 mb-4">Collectors</h2>
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
				{#each liveCollectors as collector (collector.collector_id)}
					<div class="border border-gray-200 rounded-lg p-4 bg-white">
						<div class="flex items-start justify-between mb-3">
							<div class="flex-1 min-w-0">
								<h3 class="text-sm font-semibold text-gray-900 truncate">
									{collector.display_name}
								</h3>
								<p class="text-xs text-gray-500 font-mono truncate">{collector.collector_id}</p>
							</div>
							<span
								class="flex-shrink-0 px-2 py-1 text-xs font-medium rounded-full border {getCollectorHealthColors(
									collector.health
								)}"
							>
								{collector.health}
							</span>
						</div>

						<div class="space-y-1 text-xs text-gray-600">
							{#if collector.version}
								<div class="flex justify-between">
									<span>Version:</span>
									<span class="font-mono">{collector.version}</span>
								</div>
							{/if}
							{#if collector.connected}
								<div class="flex justify-between">
									<span>Status:</span>
									<span class="text-green-600 font-medium">Connected</span>
								</div>
								{#if collector.active_devices !== undefined}
									<div class="flex justify-between">
										<span>Active Devices:</span>
										<span>{collector.active_devices}</span>
									</div>
								{/if}
								{#if collector.samples_sent !== undefined}
									<div class="flex justify-between">
										<span>Samples Sent:</span>
										<span>{collector.samples_sent.toLocaleString()}</span>
									</div>
								{/if}
							{:else}
								<div class="flex justify-between">
									<span>Status:</span>
									<span class="text-gray-600">Disconnected</span>
								</div>
								{#if collector.last_seen}
									<div class="flex justify-between">
										<span>Last Seen:</span>
										<span>{formatTimeSince(collector.last_seen)}</span>
									</div>
								{/if}
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Filters and Controls -->
	<div class="mb-6 flex flex-wrap gap-4 items-center justify-between">
		<div class="flex gap-4">
			<div>
				<label for="filter-status" class="block text-sm font-medium text-gray-700 mb-1">
					Filter by Status
				</label>
				<select
					id="filter-status"
					bind:value={filterStatus}
					class="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
				>
					<option value="all">All Devices</option>
					<option value="connected">Connected Only</option>
					<option value="disconnected">Disconnected Only</option>
				</select>
			</div>

			<div>
				<label for="sort-by" class="block text-sm font-medium text-gray-700 mb-1"> Sort By </label>
				<select
					id="sort-by"
					bind:value={sortBy}
					class="block w-full pl-3 pr-10 py-2 text-base border border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
				>
					<option value="last_seen">Last Seen</option>
					<option value="name">Name</option>
					<option value="total_samples">Total Samples</option>
				</select>
			</div>
		</div>

		<div class="text-sm text-gray-600">
			Showing {filteredDevices.length} of {liveDevices.length} devices
		</div>
	</div>

	<!-- Devices Table -->
	{#if filteredDevices.length === 0}
		<div class="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
			<div class="text-4xl mb-2">🔌</div>
			<p class="text-sm font-medium text-gray-900 mb-1">No devices found</p>
			<p class="text-xs text-gray-500">
				{liveDevices.length === 0
					? 'Devices will appear after first connection'
					: 'Try adjusting your filters'}
			</p>
		</div>
	{:else}
		<div class="bg-white shadow-sm border border-gray-200 rounded-lg overflow-hidden">
			<table class="min-w-full divide-y divide-gray-200">
				<thead class="bg-gray-50">
					<tr>
						<th
							scope="col"
							class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
						>
							Device
						</th>
						<th
							scope="col"
							class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
						>
							Collector
						</th>
						<th
							scope="col"
							class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
						>
							Status
						</th>
						<th
							scope="col"
							class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
						>
							Statistics
						</th>
						<th
							scope="col"
							class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
						>
							Last Activity
						</th>
					</tr>
				</thead>
				<tbody class="bg-white divide-y divide-gray-200">
					{#each filteredDevices as device (device.device_id)}
						{@const colors = getDeviceStatusColors(device.status)}
						{@const isEditing = editingDevice === device.device_id}
						{@const deviceCollector = device.collector_id
							? collectorMap.get(device.collector_id)
							: null}
						<tr class="hover:bg-gray-50">
							<!-- Device Name/ID -->
							<td class="px-6 py-4 whitespace-nowrap">
								{#if isEditing}
									<div class="flex items-center gap-2">
										<input
											type="text"
											bind:value={editingNickname}
											placeholder="Enter nickname"
											class="text-sm font-medium px-2 py-1 border border-gray-300 rounded w-48"
											onkeydown={(e) => {
												if (e.key === 'Enter') {
													saveNickname(device.device_id);
												} else if (e.key === 'Escape') {
													cancelEditingNickname();
												}
											}}
											use:focusElement
										/>
										<button
											onclick={() => saveNickname(device.device_id)}
											disabled={savingNickname}
											class="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
										>
											Save
										</button>
										<button
											onclick={cancelEditingNickname}
											disabled={savingNickname}
											class="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600 disabled:opacity-50"
										>
											Cancel
										</button>
									</div>
								{:else}
									<div class="flex items-center gap-2">
										<div class="min-w-0 flex-1">
											{#if device.nickname}
												<div class="text-sm font-medium text-gray-900">{device.nickname}</div>
												<div class="text-xs text-gray-500 font-mono truncate">
													{device.device_id}
												</div>
											{:else}
												<div class="text-sm font-medium font-mono text-gray-900 truncate">
													{device.device_id}
												</div>
											{/if}
										</div>
										<button
											onclick={() =>
												startEditingNickname(device.device_id, device.nickname || null)}
											class="text-gray-400 hover:text-gray-600"
											title="Edit nickname"
										>
											✏️
										</button>
									</div>
								{/if}
							</td>

							<!-- Collector -->
							<td class="px-6 py-4 whitespace-nowrap">
								{#if deviceCollector}
									<div class="text-sm text-gray-900">{deviceCollector.display_name}</div>
									<div
										class="text-xs {deviceCollector.connected ? 'text-green-600' : 'text-gray-500'}"
									>
										{deviceCollector.connected ? 'Connected' : 'Disconnected'}
									</div>
								{:else}
									<span class="text-sm text-gray-400">Unknown</span>
								{/if}
							</td>

							<!-- Status -->
							<td class="px-6 py-4 whitespace-nowrap">
								<span
									class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border {colors.bg} {colors.text} {colors.border}"
								>
									{device.status || 'DISCONNECTED'}
								</span>
								{#if device.sync_ready}
									<div class="text-xs text-green-600 mt-1">✓ Synced</div>
								{/if}
							</td>

							<!-- Statistics -->
							<td class="px-6 py-4 whitespace-nowrap">
								<div class="text-sm text-gray-900">
									{#if device.total_samples}
										{device.total_samples.toLocaleString()} samples
									{:else}
										No samples
									{/if}
								</div>
								{#if device.battery_level !== null && device.battery_level !== undefined}
									<div class="text-xs text-gray-500">Battery: {device.battery_level}%</div>
								{/if}
							</td>

							<!-- Last Activity -->
							<td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
								{#if device.last_seen}
									<div>{formatTimeSince(device.last_seen)}</div>
									{#if device.first_seen}
										<div class="text-xs text-gray-400">
											First seen: {formatTimeSince(device.first_seen)}
										</div>
									{/if}
								{:else}
									<span class="text-gray-400">Never</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
