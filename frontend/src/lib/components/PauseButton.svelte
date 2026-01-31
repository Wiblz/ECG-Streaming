<script lang="ts">
	import { isPaused, togglePause } from '$lib/state/pause.svelte';

	const paused = $derived(isPaused());

	function handleToggle() {
		togglePause();
	}
</script>

<button
	onclick={handleToggle}
	class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium text-xs transition-colors"
	class:bg-yellow-500={paused}
	class:hover:bg-yellow-600={paused}
	class:text-white={paused}
	class:bg-gray-200={!paused}
	class:hover:bg-gray-300={!paused}
	class:text-gray-700={!paused}
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
</button>
