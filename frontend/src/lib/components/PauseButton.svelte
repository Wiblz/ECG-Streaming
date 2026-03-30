<script lang="ts">
	import { isPaused, togglePause } from '$lib/state/pause.svelte';
	import Button from './buttons/Button.svelte';

	const paused = $derived(isPaused());

	function handleToggle() {
		togglePause();
	}
</script>

<Button
	variant={paused ? 'warning' : 'ghost'}
	size="sm"
	onclick={handleToggle}
	title={paused ? 'Resume data streaming' : 'Pause data streaming'}
>
	{#if paused}
		<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
			<path d="M8 5v14l11-7z" />
		</svg>
		Resume
	{:else}
		<svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
			<path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
		</svg>
		Pause
	{/if}
</Button>
