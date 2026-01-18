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

	const statusColor = $derived(
		{
			[ConnectionState.DISCONNECTED]: '#4b5563',
			[ConnectionState.CONNECTING]: '#eab308',
			[ConnectionState.CONNECTED]: '#16a34a',
			[ConnectionState.ERROR]: '#dc2626'
		}[state]
	);
</script>

<div
	class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-white text-sm font-medium shadow-sm"
	style="background-color: {statusColor}"
>
	<span
		class="w-1.5 h-1.5 rounded-full bg-white block"
		class:animate-pulse={state === ConnectionState.CONNECTING}
	></span>
	<span>{label}</span>
</div>
