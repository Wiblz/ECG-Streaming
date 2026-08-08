<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api/client';
  import Header from '$lib/components/layout/Header.svelte';
  import { formatDuration, formatTimestamp } from '$lib/utils/format';
  import { createDeviceNicknameMap, getDisplayNameFromMap } from '$lib/utils/device-names';
  import { Upload, Trash2, BarChart2 } from 'lucide-svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();

  const deviceNicknameMap = $derived(createDeviceNicknameMap(data.devices));

  // Local mutable copy of sessions - using $state.raw to avoid the warning
  // since we're intentionally capturing the initial value and mutating it
  let sessions = $state.raw(data.sessions);
  let total = $state(data.sessionsPagination.total);
  let offset = $state(data.sessionsPagination.offset + data.sessionsPagination.count);
  const limit = data.sessionsPagination.limit ?? 20;
  let loadingMore = $state(false);

  async function loadMore() {
    loadingMore = true;
    try {
      const response = await api.getSessions({ limit, offset });
      sessions = [...sessions, ...response.sessions];
      offset = offset + response.count;
      total = response.total;
    } finally {
      loadingMore = false;
    }
  }

  let importing = $state(false);
  let importMessage = $state<string | null>(null);
  let fileInput: HTMLInputElement;
  let deletingId = $state<number | null>(null);

  function handleImportClick() {
    fileInput.click();
  }

  async function handleFileSelected(event: Event) {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];

    if (!file) return;

    importing = true;
    importMessage = null;

    try {
      const result = await api.importSession(file);

      if (result.success && result.session_id) {
        importMessage = `Successfully imported session #${result.session_id}`;
        // Reload sessions list to show the new one
        const response = await api.getSessions();
        sessions = response.sessions;
        // Navigate to the new session after a brief delay
        setTimeout(() => {
          goto(`/sessions/${result.session_id}`);
        }, 1000);
      } else {
        importMessage = result.error || 'Failed to import session';
      }
    } catch (e) {
      importMessage = e instanceof Error ? e.message : 'Import failed';
    } finally {
      importing = false;
      target.value = ''; // Reset file input
    }
  }

  async function handleDelete(sessionId: number, event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();

    if (!confirm(`Are you sure you want to delete session #${sessionId}? This cannot be undone.`)) {
      return;
    }

    deletingId = sessionId;

    try {
      const result = await api.deleteSession(sessionId);
      if (result.success) {
        // Remove the deleted session from the local state
        sessions = sessions.filter((s) => s.id !== sessionId);
        importMessage = `Session #${sessionId} deleted successfully`;
        // Auto-dismiss success message after 3 seconds
        setTimeout(() => {
          importMessage = null;
        }, 3000);
      } else {
        importMessage = `Failed to delete session #${sessionId}`;
        // Auto-dismiss error message after 5 seconds
        setTimeout(() => {
          importMessage = null;
        }, 5000);
      }
    } catch (e) {
      importMessage = e instanceof Error ? e.message : 'Delete failed';
      // Auto-dismiss error message after 5 seconds
      setTimeout(() => {
        importMessage = null;
      }, 5000);
    } finally {
      deletingId = null;
    }
  }
</script>

<svelte:head>
  <title>Sessions - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-surface-muted to-surface">
  <Header>
    <!-- Import Button -->
    <input
      type="file"
      accept=".csv"
      bind:this={fileInput}
      onchange={handleFileSelected}
      class="hidden"
    />
    <button
      onclick={handleImportClick}
      disabled={importing}
      class="flex items-center gap-2 px-4 py-2 bg-status-success-fg hover:bg-status-success-border disabled:bg-status-neutral-fg text-white text-sm font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
    >
      <Upload class="w-4 h-4" />
      {importing ? 'Importing...' : 'Import CSV'}
    </button>
  </Header>

  <!-- Toast Notification -->
  {#if importMessage}
    <div class="fixed top-20 left-1/2 -translate-x-1/2 z-50 animate-slide-down">
      <div
        class="px-6 py-4 rounded-lg shadow-xl {importMessage.toLowerCase().includes('success')
          ? 'bg-status-success border border-status-success-border'
          : 'bg-status-error border border-status-error-border'}"
      >
        <p
          class="text-sm font-medium {importMessage.toLowerCase().includes('success')
            ? 'text-status-success-fg'
            : 'text-status-error-fg'}"
        >
          {importMessage}
        </p>
      </div>
    </div>
  {/if}

  <main class="container mx-auto px-6 py-8 max-w-7xl">
    {#if sessions.length === 0}
      <div class="bg-surface border border-border rounded-xl shadow-sm p-12 text-center">
        <BarChart2 class="w-12 h-12 mx-auto mb-4 text-text-secondary" />
        <h3 class="text-lg font-semibold text-text mb-2">No sessions found</h3>
        <p class="text-sm text-text-secondary">Start recording to create your first session</p>
      </div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {#each sessions as session (session.id)}
          <div
            class="bg-surface border border-border rounded-xl shadow-sm hover:shadow-lg transition-shadow"
          >
            <div class="p-6">
              <div class="flex items-center justify-between mb-4 gap-2">
                <a href="/sessions/{session.id}" class="flex-1 min-w-0">
                  <h3
                    class="text-lg font-semibold text-text hover:text-status-info-fg transition-colors"
                  >
                    Session #{session.id}
                  </h3>
                  <p class="text-xs text-text-secondary mt-1">
                    {formatTimestamp(session.start_time)}
                  </p>
                </a>
                <div class="flex items-center gap-2 flex-shrink-0">
                  <div
                    class="bg-status-success text-status-success-fg text-xs font-medium px-2 py-1 rounded-full"
                  >
                    {session.sample_count.toLocaleString()} samples
                  </div>
                  <button
                    onclick={(e) => handleDelete(session.id, e)}
                    disabled={deletingId === session.id}
                    class="p-2 text-text-muted hover:text-status-error-fg hover:bg-status-error rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Delete session"
                  >
                    {#if deletingId === session.id}
                      <div
                        class="w-4 h-4 border-2 border-border border-t-text-secondary rounded-full animate-spin"
                      ></div>
                    {:else}
                      <Trash2 class="w-4 h-4" />
                    {/if}
                  </button>
                </div>
              </div>

              <a href="/sessions/{session.id}" class="block">
                <div class="space-y-3">
                  {#if session.notes}
                    <div class="text-sm">
                      <p class="text-text-secondary italic line-clamp-2">"{session.notes}"</p>
                    </div>
                  {/if}

                  <div class="flex items-center justify-between text-sm">
                    <span class="text-text-secondary">Duration</span>
                    <span class="font-medium text-text">
                      {formatDuration(session.duration_seconds)}
                    </span>
                  </div>

                  <div class="flex items-center justify-between text-sm">
                    <span class="text-text-secondary">Devices</span>
                    <span class="font-medium text-text">{session.device_count}</span>
                  </div>

                  {#if session.devices.length > 0}
                    <div class="pt-3 border-t border-border">
                      <div class="flex flex-wrap gap-2">
                        {#each session.devices as deviceId (deviceId)}
                          {@const displayName = getDisplayNameFromMap(deviceId, deviceNicknameMap)}
                          <span
                            class="bg-surface-muted text-text-secondary text-xs px-2 py-1 rounded-md"
                            title={deviceId !== displayName ? deviceId : undefined}
                          >
                            {displayName}
                          </span>
                        {/each}
                      </div>
                    </div>
                  {/if}
                </div>

                <div class="mt-4 pt-4 border-t border-border">
                  <span
                    class="text-sm text-status-info-fg font-medium hover:text-status-info-hover"
                  >
                    View Recording →
                  </span>
                </div>
              </a>
            </div>
          </div>
        {/each}
      </div>

      <div class="mt-8 flex flex-col items-center gap-4">
        <p class="text-sm text-text-secondary">
          Showing {sessions.length} of {total} session{total === 1 ? '' : 's'}
        </p>
        {#if sessions.length < total}
          <button
            onclick={loadMore}
            disabled={loadingMore}
            class="px-6 py-2 text-sm font-medium bg-surface border border-border rounded-lg hover:bg-surface-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loadingMore ? 'Loading...' : 'Load more'}
          </button>
        {/if}
      </div>
    {/if}
  </main>
</div>
