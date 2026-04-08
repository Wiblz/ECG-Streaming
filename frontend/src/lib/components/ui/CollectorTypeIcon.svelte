<script lang="ts">
  import { Bluetooth, Bot, CircuitBoard, Usb } from 'lucide-svelte';

  interface Props {
    collectorType: string | null;
  }

  let { collectorType }: Props = $props();

  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    ble: { bg: 'bg-status-info', text: 'text-status-info-fg', border: 'border-status-info-border' },
    usb: {
      bg: 'bg-status-success',
      text: 'text-status-success-fg',
      border: 'border-status-success-border'
    },
    simulator: {
      bg: 'bg-status-warning',
      text: 'text-status-warning-fg',
      border: 'border-status-warning-border'
    }
  };

  const colors = $derived(
    colorMap[collectorType ?? ''] ?? {
      bg: 'bg-status-neutral',
      text: 'text-status-neutral-fg',
      border: 'border-status-neutral-border'
    }
  );

  function getIcon(type: string | null) {
    switch (type) {
      case 'ble':
        return Bluetooth;
      case 'usb':
        return Usb;
      case 'simulator':
        return Bot;
      default:
        return CircuitBoard;
    }
  }

  const Icon = $derived(getIcon(collectorType));
</script>

<span class="flex items-center justify-center p-1.5 rounded-lg border {colors.bg} {colors.border}">
  <Icon class="size-3.5 {colors.text}" />
</span>
