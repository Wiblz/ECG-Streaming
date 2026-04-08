<script lang="ts">
  import { formatTimeSince } from '$lib/utils/format';
  import type { DeviceInfo } from '$lib/types/api';
  import DeviceStatusBadge from '$lib/components/ui/DeviceStatusBadge.svelte';
  import { Battery, CheckCheck, Clock } from 'lucide-svelte';

  interface Props {
    device: DeviceInfo;
  }

  let { device }: Props = $props();

  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    STREAMING: {
      bg: 'bg-status-success',
      text: 'text-status-success-fg',
      border: 'border-status-success-border'
    },
    CONNECTED: {
      bg: 'bg-status-info',
      text: 'text-status-info-fg',
      border: 'border-status-info-border'
    },
    CONNECTING: {
      bg: 'bg-status-warning',
      text: 'text-status-warning-fg',
      border: 'border-status-warning-border'
    },
    ERROR: {
      bg: 'bg-status-error',
      text: 'text-status-error-fg',
      border: 'border-status-error-border'
    }
  };

  const colors = $derived(
    colorMap[device.status ?? ''] ?? {
      bg: 'bg-status-neutral',
      text: 'text-status-neutral-fg',
      border: 'border-status-neutral-border'
    }
  );
</script>

<div class="border {colors.border} rounded-lg p-3 {colors.bg}">
  <div class="flex items-start justify-between mb-2">
    <div class="flex-1 min-w-0">
      {#if device.nickname}
        <h4 class="text-sm font-semibold {colors.text}">{device.nickname}</h4>
        <span class="text-xs text-text-secondary font-mono">{device.device_id}</span>
      {:else}
        <h4 class="text-sm font-mono font-semibold {colors.text} truncate">{device.device_id}</h4>
      {/if}
    </div>
    <DeviceStatusBadge status={device.status} />
  </div>

  <div class="flex items-center gap-4 text-xs text-text-secondary mt-2">
    {#if device.last_update}
      <div class="flex items-center gap-1">
        <Clock class="w-3.5 h-3.5" />
        <span>{formatTimeSince(device.last_update)}</span>
      </div>
    {/if}

    {#if device.battery_level !== null && device.battery_level !== undefined}
      <div class="flex items-center gap-1">
        <Battery class="w-3.5 h-3.5" />
        <span>{device.battery_level}%</span>
      </div>
    {/if}

    {#if device.sync_ready}
      <div class="flex items-center gap-1 text-status-success-fg">
        <CheckCheck class="w-3.5 h-3.5" />
        <span>Synced</span>
      </div>
    {/if}
  </div>

  {#if device.error_message}
    <div class="mt-2 pt-2 border-t border-red-200">
      <p class="text-xs text-red-600 font-medium">{device.error_message}</p>
    </div>
  {/if}
</div>
