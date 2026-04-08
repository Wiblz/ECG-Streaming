<script lang="ts">
  import type { DeviceInfo } from '$lib/types/api';

  interface Props {
    status: DeviceInfo['status'];
  }

  let { status }: Props = $props();

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
    colorMap[status ?? ''] ?? {
      bg: 'bg-status-neutral',
      text: 'text-status-neutral-fg',
      border: 'border-status-neutral-border'
    }
  );
</script>

<span
  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border {colors.bg} {colors.text} {colors.border}"
>
  {status || 'DISCONNECTED'}
</span>
