<script lang="ts">
  import type { Collector } from '$lib/types/api';

  interface Props {
    health: Collector['health'];
  }

  let { health }: Props = $props();

  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    healthy: {
      bg: 'bg-status-success',
      text: 'text-status-success-fg',
      border: 'border-status-success-border'
    },
    warning: {
      bg: 'bg-status-warning',
      text: 'text-status-warning-fg',
      border: 'border-status-warning-border'
    },
    disconnected: {
      bg: 'bg-status-neutral',
      text: 'text-status-neutral-fg',
      border: 'border-status-neutral-border'
    }
  };

  const colors = $derived(
    colorMap[health] ?? {
      bg: 'bg-status-neutral',
      text: 'text-status-neutral-fg',
      border: 'border-status-neutral-border'
    }
  );
</script>

<span
  class="flex-shrink-0 px-2 py-1 text-xs font-medium rounded-full border {colors.bg} {colors.text} {colors.border}"
>
  {health}
</span>
