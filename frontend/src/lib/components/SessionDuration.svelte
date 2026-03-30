<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { formatDuration } from '$lib/utils/format';

  interface Props {
    /**
     * Session start time (Unix timestamp in seconds)
     */
    startTime: number;
  }

  let { startTime }: Props = $props();

  let duration = $state(0);
  let intervalId: ReturnType<typeof setInterval> | undefined;

  // Calculate current duration
  function updateDuration() {
    const now = Math.floor(Date.now() / 1000);
    duration = now - startTime;
  }

  onMount(() => {
    // Initial update
    updateDuration();

    // Update every second
    intervalId = setInterval(updateDuration, 1000);
  });

  onDestroy(() => {
    if (intervalId !== undefined) {
      clearInterval(intervalId);
    }
  });
</script>

<div class="flex items-center gap-2 text-xs">
  <svg
    class="w-3.5 h-3.5 text-text-secondary"
    fill="none"
    stroke="currentColor"
    viewBox="0 0 24 24"
  >
    <path
      stroke-linecap="round"
      stroke-linejoin="round"
      stroke-width="2"
      d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
  <span class="text-text-secondary">Duration:</span>
  <span class="font-medium text-text tabular-nums">{formatDuration(duration)}</span>
</div>
