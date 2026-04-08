<script lang="ts">
  import { isPaused, togglePause } from '$lib/state/pause.svelte';
  import Button from './Button.svelte';
  import { Play, Pause } from 'lucide-svelte';

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
    <Play class="w-3.5 h-3.5" />
    Resume
  {:else}
    <Pause class="w-3.5 h-3.5" />
    Pause
  {/if}
</Button>
