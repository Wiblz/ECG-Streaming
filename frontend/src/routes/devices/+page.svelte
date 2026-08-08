<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api } from '$lib/api/client';
  import Header from '$lib/components/layout/Header.svelte';
  import { mergeDevice } from '$lib/state/devices.svelte';
  import { statusEvents } from '$lib/state/status-events.svelte';
  import type { Collector, DeviceInfo } from '$lib/types/api';
  import { formatTimeSince } from '$lib/utils/format';
  import CollectorHealthBadge from '$lib/components/ui/CollectorHealthBadge.svelte';
  import CollectorTypeIcon from '$lib/components/ui/CollectorTypeIcon.svelte';
  import DeviceStatusBadge from '$lib/components/ui/DeviceStatusBadge.svelte';
  import { Bot, Plug, Pencil, CheckCheck } from 'lucide-svelte';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
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

  // Filter and sort — URL-driven, reset to page 1 on change
  const filterStatus = $derived(data.filters.status ?? 'all');
  const sortBy = $derived(data.filters.sort_by ?? 'last_seen');
  const showSimulated = $derived(data.filters.show_simulated ?? false);

  function updateFilters(updates: {
    status?: string;
    sort_by?: string;
    sort_order?: string;
    show_simulated?: boolean;
  }) {
    const params = new SvelteURLSearchParams(page.url.searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value === 'all' || value === null || value === undefined) {
        params.delete(key);
      } else {
        params.set(key, String(value));
      }
    }
    // Reset to page 1 on filter/sort change
    params.delete('offset');
    goto(`?${params.toString()}`);
  }

  // Pagination
  const limit = data.devicesPagination.limit ?? 50;
  const total = $derived(data.devicesPagination.total);
  const currentOffset = $derived(data.devicesPagination.offset);
  const currentPage = $derived(Math.floor(currentOffset / limit) + 1);
  const totalPages = $derived(Math.ceil(total / limit));

  function goToPage(pageNum: number) {
    const params = new SvelteURLSearchParams(page.url.searchParams);
    params.set('limit', String(limit));
    params.set('offset', String((pageNum - 1) * limit));
    goto(`?${params.toString()}`);
  }

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
      const response = await api.updateDeviceNickname(deviceId, nickname);

      // Update both global devices state and local data
      if (response.success) {
        mergeDevice(response.device_id, { nickname: response.nickname });

        // Update local data.devices array for immediate UI update
        // With $state wrapper, deep reactivity works
        const device = data.devices.find((d) => d.device_id === response.device_id);
        if (device) {
          device.nickname = response.nickname;
        }
      }

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
          active_devices: sseCollector.active_devices
        } as Collector;
      }
      return collector;
    });
  });

  // Helper functions for color mapping
  // Devices with live SSE status applied — filtering/sorting done server-side
  const filteredDevices = $derived(liveDevices);

  const collectorMap = $derived(new Map(liveCollectors.map((c) => [c.collector_id, c])));
</script>

<svelte:head>
  <title>Devices - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-surface-muted to-surface">
  <Header />

  <main class="container mx-auto px-6 py-8 max-w-7xl">
    <!-- Collectors Summary -->
    {#if liveCollectors.length > 0}
      <div class="mb-8">
        <h2 class="text-lg font-semibold text-text mb-4">Collectors</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {#each liveCollectors as collector (collector.collector_id)}
            <div class="bg-surface border border-border rounded-xl shadow-sm p-6">
              <div class="flex items-start justify-between mb-3">
                <div class="flex items-center gap-2 flex-1 min-w-0">
                  <CollectorTypeIcon collectorType={collector.collector_type} />
                  <div class="min-w-0">
                    <h3 class="text-sm font-semibold text-text truncate">
                      {collector.display_name}
                    </h3>
                    <p class="text-xs text-text-secondary font-mono truncate">
                      {collector.collector_id}
                    </p>
                  </div>
                </div>
                <CollectorHealthBadge health={collector.health} />
              </div>

              <div class="space-y-1 text-xs text-text-secondary">
                {#if collector.version}
                  <div class="flex justify-between">
                    <span>Version:</span>
                    <span class="font-mono">{collector.version}</span>
                  </div>
                {/if}
                {#if collector.connected}
                  <div class="flex justify-between">
                    <span>Status:</span>
                    <span class="text-status-success-fg font-medium">Connected</span>
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
                    <span class="text-text-secondary">Disconnected</span>
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
          <label for="filter-status" class="block text-sm font-medium text-text-secondary mb-1">
            Filter by Status
          </label>
          <select
            id="filter-status"
            value={filterStatus}
            onchange={(e) => updateFilters({ status: (e.target as HTMLSelectElement).value })}
            class="block w-full pl-3 pr-10 py-2 text-base border border-border focus:outline-none focus:ring-focus focus:border-transparent sm:text-sm rounded-md bg-surface text-text hover:bg-surface-hover cursor-pointer"
          >
            <option value="all">All Devices</option>
            <option value="CONNECTED">Connected</option>
            <option value="STREAMING">Streaming</option>
            <option value="DISCONNECTED">Disconnected</option>
            <option value="ERROR">Error</option>
          </select>
        </div>

        <div>
          <label for="sort-by" class="block text-sm font-medium text-text-secondary mb-1">
            Sort By
          </label>
          <select
            id="sort-by"
            value={sortBy}
            onchange={(e) => updateFilters({ sort_by: (e.target as HTMLSelectElement).value })}
            class="block w-full pl-3 pr-10 py-2 text-base border border-border focus:outline-none focus:ring-focus focus:border-transparent sm:text-sm rounded-md bg-surface text-text hover:bg-surface-hover cursor-pointer"
          >
            <option value="last_seen">Last Seen</option>
            <option value="nickname">Name</option>
            <option value="total_samples">Total Samples</option>
            <option value="first_seen">First Seen</option>
            <option value="status">Status</option>
          </select>
        </div>
        <div class="flex items-end pb-1">
          <label class="flex items-center gap-2 cursor-pointer select-none text-sm text-text">
            <input
              type="checkbox"
              checked={showSimulated}
              onchange={(e) =>
                updateFilters({
                  show_simulated: (e.target as HTMLInputElement).checked ? true : false
                })}
              class="rounded border-border accent-status-info-fg focus:ring-focus cursor-pointer"
            />
            Show simulated
          </label>
        </div>
      </div>

      <div class="text-sm text-text-secondary">
        {total} device{total === 1 ? '' : 's'}
        {#if totalPages > 1}· page {currentPage} of {totalPages}{/if}
      </div>
    </div>

    <!-- Devices Table -->
    {#if filteredDevices.length === 0}
      <div class="bg-surface border border-border rounded-xl shadow-sm p-12 text-center">
        <Plug class="w-12 h-12 mx-auto mb-4 text-text-secondary" />
        <h3 class="text-lg font-semibold text-text mb-2">No devices found</h3>
        <p class="text-sm text-text-secondary">
          {total === 0
            ? 'Devices will appear after first connection'
            : 'Try adjusting your filters'}
        </p>
      </div>
    {:else}
      <div class="bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
        <table class="min-w-full divide-y divide-border">
          <thead class="bg-surface-muted">
            <tr>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider"
              >
                Device
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider"
              >
                Collector
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider"
              >
                Status
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider"
              >
                Statistics
              </th>
              <th
                scope="col"
                class="px-6 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider"
              >
                Last Activity
              </th>
            </tr>
          </thead>
          <tbody class="bg-surface divide-y divide-border">
            {#each filteredDevices as device (device.device_id)}
              {@const isEditing = editingDevice === device.device_id}
              {@const deviceCollector = device.collector_id
                ? collectorMap.get(device.collector_id)
                : null}
              <tr class="hover:bg-surface-hover">
                <!-- Device Name/ID -->
                <td class="px-6 py-4 whitespace-nowrap">
                  {#if isEditing}
                    <div class="flex items-center gap-2">
                      <input
                        type="text"
                        bind:value={editingNickname}
                        placeholder="Enter nickname"
                        class="text-sm font-medium px-2 py-1 border border-border rounded w-48 bg-surface text-text"
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
                        class="px-2 py-1 text-xs bg-status-neutral-fg text-white rounded hover:bg-status-neutral-border disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  {:else}
                    <div class="group">
                      {#if device.nickname}
                        <div class="flex items-center gap-1.5">
                          <span class="text-sm font-medium text-text">{device.nickname}</span>
                          <button
                            onclick={() =>
                              startEditingNickname(device.device_id, device.nickname || null)}
                            class="shrink-0 p-0.5 text-text-muted hover:text-text-secondary hover:bg-surface-muted rounded transition-colors opacity-0 group-hover:opacity-100"
                            title="Edit nickname"
                          >
                            <Pencil class="size-4" />
                          </button>
                        </div>
                        <div class="flex items-center gap-1 text-xs text-text-secondary font-mono">
                          {device.device_id}
                          {#if device.is_simulated}<Bot size={12} class="-translate-y-px" />{/if}
                        </div>
                      {:else}
                        <div class="flex items-center gap-1.5">
                          <span class="text-sm font-medium font-mono text-text truncate">
                            {device.device_id}
                          </span>
                          {#if device.is_simulated}<Bot size={14} class="-translate-y-px" />{/if}
                          <button
                            onclick={() =>
                              startEditingNickname(device.device_id, device.nickname || null)}
                            class="shrink-0 p-0.5 text-text-muted hover:text-text-secondary hover:bg-surface-muted rounded transition-colors opacity-0 group-hover:opacity-100"
                            title="Edit nickname"
                          >
                            <Pencil class="size-4" />
                          </button>
                        </div>
                      {/if}
                    </div>
                  {/if}
                </td>

                <!-- Collector -->
                <td class="px-6 py-4 whitespace-nowrap">
                  {#if deviceCollector}
                    <div class="text-sm text-text">{deviceCollector.display_name}</div>
                    <div
                      class="text-xs {deviceCollector.connected
                        ? 'text-status-success-fg'
                        : 'text-text-secondary'}"
                    >
                      {deviceCollector.connected ? 'Connected' : 'Disconnected'}
                    </div>
                  {:else}
                    <span class="text-sm text-text-muted">Unknown</span>
                  {/if}
                </td>

                <!-- Status -->
                <td class="px-6 py-4 whitespace-nowrap">
                  <DeviceStatusBadge status={device.status} />
                  {#if device.sync_ready}
                    <div class="flex items-center gap-1 text-xs text-status-success-fg mt-1">
                      <CheckCheck class="w-3.5 h-3.5" />
                      <span>Synced</span>
                    </div>
                  {/if}
                </td>

                <!-- Statistics -->
                <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm text-text">
                    {#if device.total_samples}
                      {device.total_samples.toLocaleString()} samples
                    {:else}
                      No samples
                    {/if}
                  </div>
                  {#if device.battery_level !== null && device.battery_level !== undefined}
                    <div class="text-xs text-text-secondary">Battery: {device.battery_level}%</div>
                  {/if}
                </td>

                <!-- Last Activity -->
                <td class="px-6 py-4 whitespace-nowrap text-sm text-text-secondary">
                  {#if device.last_seen}
                    <div>{formatTimeSince(device.last_seen)}</div>
                    {#if device.first_seen}
                      <div class="text-xs text-text-muted">
                        First seen: {formatTimeSince(device.first_seen)}
                      </div>
                    {/if}
                  {:else}
                    <span class="text-text-muted">Never</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      {#if totalPages > 1}
        <div class="mt-6 flex items-center justify-between">
          <p class="text-sm text-text-secondary">
            Page {currentPage} of {totalPages}
          </p>
          <div class="flex items-center gap-2">
            <button
              onclick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              class="px-3 py-1.5 text-sm font-medium bg-surface border border-border rounded-lg hover:bg-surface-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              onclick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              class="px-3 py-1.5 text-sm font-medium bg-surface border border-border rounded-lg hover:bg-surface-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      {/if}
    {/if}
  </main>
</div>
