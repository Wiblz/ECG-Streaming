<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import { statusEvents } from '$lib/state/status-events.svelte';
  import type { Collector, DeviceInfo } from '$lib/types/api';
  import Card from '../layout/Card.svelte';
  import CollectorHealthBadge from '$lib/components/ui/CollectorHealthBadge.svelte';
  import DeviceStatusCard from './DeviceStatusCard.svelte';
  import { Moon } from 'lucide-svelte';

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
      <Moon class="w-8 h-8 mx-auto mb-2 text-text-secondary" />
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
                  <CollectorHealthBadge health={collector.collector.health} />
                {/if}
              </div>
              <div class="flex items-center gap-3 text-xs text-text-secondary mt-1">
                <span>
                  {collector.devices.length}
                  {collector.devices.length === 1 ? 'device' : 'devices'}
                </span>
                {#if collector.collector && collector.collector.connected}
                  <span class="text-status-success-fg">Connected</span>
                {/if}
              </div>
            </div>
          </div>

          <!-- Devices in this collector -->
          <div class="space-y-2 pl-2 border-l-2 border-border">
            {#each collector.devices as device (device.device_id)}
              <DeviceStatusCard {device} />
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</Card>
