<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api/client';
  import { getActiveSession, isRecording, setActiveSession } from '$lib/state/session.svelte';
  import Button from '../ui/Button.svelte';
  import Card from '../layout/Card.svelte';
  import SessionDuration from './SessionDuration.svelte';

  const recording = $derived(isRecording());
  const activeSession = $derived(getActiveSession());

  let notes = $state('');
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Load active session on mount
  onMount(async () => {
    try {
      const response = await api.getActiveSession();
      if (response.active && response.session) {
        setActiveSession(response.session);
      }
    } catch (err) {
      console.error('[SessionControl] Failed to load active session:', err);
    }
  });

  async function handleStart() {
    loading = true;
    error = null;
    try {
      const response = await api.startSession(notes || null);
      if (response.success && response.session_id) {
        // Fetch the full session details
        const session = await api.getSession(response.session_id);
        setActiveSession(session);
        notes = '';
        console.log(`[SessionControl] Session ${response.session_id} started`);
      } else {
        error = response.error || 'Failed to start session';
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to start session';
      console.error('[SessionControl] Error starting session:', err);
    } finally {
      loading = false;
    }
  }

  async function handleStop() {
    loading = true;
    error = null;
    try {
      const response = await api.stopSession();
      if (response.success) {
        setActiveSession(null);
        console.log(`[SessionControl] Session ${response.session_id} stopped`);
      } else {
        error = response.error || 'Failed to stop session';
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to stop session';
      console.error('[SessionControl] Error stopping session:', err);
    } finally {
      loading = false;
    }
  }
</script>

<Card title="Recording Session">
  {#snippet headerActions()}
    {#if recording}
      <div class="flex items-center gap-2">
        <div class="w-1.5 h-1.5 bg-status-error-fg rounded-full animate-pulse"></div>
        <span class="text-xs font-medium text-status-error-fg">Recording</span>
      </div>
    {:else}
      <div class="flex items-center gap-2">
        <div class="w-1.5 h-1.5 bg-status-neutral-fg rounded-full"></div>
        <span class="text-xs font-medium text-text-secondary">Not Recording</span>
      </div>
    {/if}
  {/snippet}

  {#if error}
    <div
      class="mb-3 p-2 bg-status-error border border-status-error-border rounded text-xs text-status-error-fg"
    >
      {error}
    </div>
  {/if}

  {#if recording && activeSession}
    <div class="space-y-3">
      <div class="text-xs space-y-2">
        <div class="flex justify-between">
          <span class="text-text-secondary">Session ID:</span>
          <span class="font-medium text-text">#{activeSession.id}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-text-secondary">Started:</span>
          <span class="font-medium text-text">
            {new Date(activeSession.start_time * 1000).toLocaleTimeString()}
          </span>
        </div>
        <div class="pt-1">
          <SessionDuration startTime={activeSession.start_time} />
        </div>
        {#if activeSession.notes}
          <div class="pt-1">
            <span class="text-text-secondary">Notes:</span>
            <p class="text-text mt-1">{activeSession.notes}</p>
          </div>
        {/if}
      </div>

      <Button variant="danger" size="md" onclick={handleStop} disabled={loading} class="w-full">
        {loading ? 'Stopping...' : 'Stop Recording'}
      </Button>
    </div>
  {:else}
    <div class="space-y-3">
      <div>
        <label for="session-notes" class="block text-xs font-medium text-text-secondary mb-1">
          Notes (optional)
        </label>
        <input
          id="session-notes"
          type="text"
          bind:value={notes}
          placeholder="e.g., Exercise test, resting ECG..."
          class="w-full px-3 py-2 text-sm bg-surface text-text border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-focus focus:border-transparent disabled:bg-surface-muted disabled:text-text-disabled"
          disabled={loading}
        />
      </div>

      <Button variant="success" size="md" onclick={handleStart} disabled={loading} class="w-full">
        {loading ? 'Starting...' : 'Start Recording'}
      </Button>

      <p class="text-xs text-text-secondary">
        Start recording to save samples to the database. Samples will continue streaming to the
        dashboard whether or not recording is active.
      </p>
    </div>
  {/if}
</Card>
