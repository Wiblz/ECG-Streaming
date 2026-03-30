<script lang="ts">
  import { ConnectionState, getWsState } from '$lib/state/websocket.svelte';

  // Reactive derived value
  const state = $derived(getWsState());
  const label = $derived(
    {
      [ConnectionState.DISCONNECTED]: 'Disconnected',
      [ConnectionState.CONNECTING]: 'Connecting...',
      [ConnectionState.CONNECTED]: 'Connected',
      [ConnectionState.ERROR]: 'Error'
    }[state]
  );

  const statusClass = $derived(
    {
      [ConnectionState.DISCONNECTED]: 'bg-status-neutral-fg',
      [ConnectionState.CONNECTING]: 'bg-status-warning-fg',
      [ConnectionState.CONNECTED]: 'bg-status-success-fg',
      [ConnectionState.ERROR]: 'bg-status-error-fg'
    }[state]
  );
</script>

<div
  class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-white text-sm font-medium shadow-sm {statusClass}"
>
  <span
    class="w-1.5 h-1.5 rounded-full bg-white block"
    class:animate-pulse={state === ConnectionState.CONNECTING}
  ></span>
  <span>{label}</span>
</div>
