<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import { statusEvents } from '$lib/state/status-events.svelte';
  import type { Collector, DeviceInfo } from '$lib/types/api';
  import { formatTimeSince, formatUptime } from '$lib/utils/format';
  import Card from './Card.svelte';

  // Fetch device metadata (nicknames, etc.) once on mount
  let deviceMetadata = $state<Map<string, Pick<DeviceInfo, 'nickname' | 'sync_ready' | 'sync'>>>(
    new Map()
  );
  let loading = $state(true);
  let error = $state<string | null>(null);

  async function fetchDeviceMetadata() {
    try {
      const response = await api.getAllDevices();
      const metadata = new Map(
        response.devices.map((d) => [
          d.device_id,
          {
            nickname: d.nickname,
            sync_ready: d.sync_ready,
            sync: d.sync
          }
        ])
      );
      deviceMetadata = metadata;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Failed to fetch device metadata';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    fetchDeviceMetadata();
  });

  // Use SSE for real-time device status and collectors
  let collectors = $derived(statusEvents.getCollectors());
  let sseDevices = $derived(statusEvents.getDevices());

  // Merge SSE status with local metadata and filter to active devices only
  let devices = $derived.by(() => {
    return sseDevices
      .filter((d) => d.status !== 'DISCONNECTED' && d.status !== 'UNKNOWN')
      .map((d) => {
        const metadata = deviceMetadata.get(d.device_id);
        return {
          device_id: d.device_id,
          collector_id: d.collector_id,
          status: d.status,
          last_update: d.last_update,
          battery_level: d.battery_level,
          error_message: d.error_message,
          nickname: metadata?.nickname,
          sync_ready: metadata?.sync_ready ?? false,
          sync: metadata?.sync
        } as DeviceInfo;
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
      { name: string; devices: DeviceInfo[]; collector: Collector | null }
    > = {};

    // Add devices to their respective collectors
    for (const device of devices) {
      const collectorKey = device.collector_id || 'unknown';

      if (!groups[collectorKey]) {
        // Find matching collector info
        const collectorInfo = collectors.find((c) => c.collector_id === collectorKey) || null;
        const collectorName = collectorInfo?.display_name || collectorKey;

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

<Card
  title="Active Devices"
  badge="{devices.length} {devices.length === 1 ? 'device' : 'devices'}"
  divider={true}
>
  {#snippet headerActions()}
    <a
      href="/devices"
      class="text-xs text-status-info-fg hover:text-status-info-hover font-medium hover:underline"
    >
      Manage All Devices →
    </a>
  {/snippet}

  {#if loading}
    <div class="flex items-center justify-center py-8">
      <div
        class="inline-block w-8 h-8 border-4 border-border border-t-text-secondary rounded-full animate-spin"
      ></div>
    </div>
  {:else if error}
    <div class="bg-status-warning border border-status-warning-border rounded-lg p-4">
      <p class="text-status-warning-fg text-sm font-medium">
        {error}
      </p>
    </div>
  {:else if devices.length === 0}
    <div class="text-center py-8">
      <div class="text-4xl mb-2">💤</div>
      <p class="text-sm font-medium text-text mb-1">No active devices</p>
      <p class="text-xs text-text-secondary">Devices will appear when they start streaming</p>
    </div>
  {:else}
    <div class="space-y-4">
      {#each groupedDevices as collector (collector.collector_id)}
        <div>
          <!-- Collector Header -->
          <div class="flex items-center gap-2 mb-2 px-1">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <h3 class="text-sm font-semibold text-text truncate">
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
              <div class="flex items-center gap-3 text-xs text-text-secondary mt-1">
                <span>
                  {collector.devices.length}
                  {collector.devices.length === 1 ? 'device' : 'devices'}
                </span>
                {#if collector.collector && collector.collector.connected}
                  {#if collector.collector.time_since_heartbeat !== null}
                    <span>
                      ⏱️ {formatUptime(collector.collector.time_since_heartbeat)} ago
                    </span>
                  {/if}
                {/if}
              </div>
            </div>
          </div>

          <!-- Devices in this collector -->
          <div class="space-y-2 pl-2 border-l-2 border-border">
            {#each collector.devices as device (device.device_id)}
              {@const colors = getDeviceStatusColors(device.status)}
              <div class="border {colors.border} rounded-lg p-3 {colors.bg}">
                <div class="flex items-start justify-between mb-2">
                  <div class="flex-1 min-w-0">
                    {#if device.nickname}
                      <h4 class="text-sm font-semibold {colors.text}">
                        {device.nickname}
                      </h4>
                      <span class="text-xs text-text-secondary font-mono">{device.device_id}</span>
                    {:else}
                      <h4 class="text-sm font-mono font-semibold {colors.text} truncate">
                        {device.device_id}
                      </h4>
                    {/if}
                  </div>
                  <span
                    class="flex-shrink-0 text-xs font-bold px-2 py-1 rounded {colors.bg} {colors.text} {colors.border} border ml-2"
                  >
                    {device.status}
                  </span>
                </div>

                <div class="flex items-center gap-4 text-xs text-text-secondary mt-2">
                  {#if device.last_update}
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
                  {/if}

                  {#if device.battery_level !== null && device.battery_level !== undefined}
                    <div class="flex items-center gap-1">
                      <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          d="M5 4a2 2 0 00-2 2v6a2 2 0 002 2h8a2 2 0 002-2V6a2 2 0 00-2-2H5zm9 10H4V6h10v8zm3-6v4h1V8h-1z"
                        />
                      </svg>
                      <span>{device.battery_level}%</span>
                    </div>
                  {/if}

                  {#if device.sync_ready}
                    <div class="flex items-center gap-1">
                      <span class="text-status-success-fg">✓ Synced</span>
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
</Card>
