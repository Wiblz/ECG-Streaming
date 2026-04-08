<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api/client';
  import Header from '$lib/components/layout/Header.svelte';
  import HistoricalWaveforms from '$lib/components/waveforms/HistoricalWaveforms.svelte';
  import { formatDuration, formatFullTimestamp } from '$lib/utils/format';
  import { createDeviceNicknameMap, getDisplayNameFromMap } from '$lib/utils/device-names';
  import { Download, Trash2 } from 'lucide-svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();

  const deviceNicknameMap = $derived(createDeviceNicknameMap(data.devices));

  let deleting = $state(false);

  function handleExport() {
    const exportUrl = api.getSessionExportUrl(data.session.id);
    window.open(exportUrl, '_blank');
  }

  async function handleDelete() {
    if (
      !confirm(
        `Are you sure you want to delete session #${data.session.id}? This cannot be undone.`
      )
    ) {
      return;
    }

    deleting = true;

    try {
      const result = await api.deleteSession(data.session.id);
      if (result.success) {
        // Navigate back to sessions list
        await goto('/sessions');
      } else {
        alert('Failed to delete session');
        deleting = false;
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Delete failed');
      deleting = false;
    }
  }
</script>

<svelte:head>
  <title>Session #{data.session.id} - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-surface-muted to-surface">
  <Header />

  <main class="container mx-auto px-6 py-8 max-w-7xl">
    <div class="space-y-6">
      <!-- Session Stats -->
      <div class="bg-surface border border-border rounded-xl shadow-lg p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-text">Session Information</h2>
          <div class="flex items-center gap-2">
            <button
              onclick={handleExport}
              class="flex items-center gap-2 px-3 py-1.5 text-sm font-medium bg-status-info-fg hover:bg-status-info-hover text-white rounded-lg transition-colors"
            >
              <Download class="w-4 h-4" />
              Export CSV
            </button>
            <button
              onclick={handleDelete}
              disabled={deleting}
              class="flex items-center gap-2 px-3 py-1.5 text-sm font-medium bg-status-error-fg hover:bg-status-error-hover text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {#if deleting}
                <div
                  class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"
                ></div>
              {:else}
                <Trash2 class="w-4 h-4" />
              {/if}
              Delete
            </button>
          </div>
        </div>
        <dl class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="bg-surface-muted rounded-lg p-4">
            <dt class="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1">
              Duration
            </dt>
            <dd class="text-xl font-bold text-text">
              {formatDuration(data.session.duration_seconds)}
            </dd>
          </div>
          <div class="bg-surface-muted rounded-lg p-4">
            <dt class="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1">
              Samples
            </dt>
            <dd class="text-xl font-bold text-text">
              {data.session.sample_count.toLocaleString()}
            </dd>
          </div>
          <div class="bg-surface-muted rounded-lg p-4">
            <dt class="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1">
              Devices
            </dt>
            <dd class="text-xl font-bold text-text">{data.session.device_count}</dd>
          </div>
          <div class="bg-surface-muted rounded-lg p-4">
            <dt class="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1">
              Started
            </dt>
            <dd class="text-xl font-bold text-text">
              {formatFullTimestamp(data.session.start_time)}
            </dd>
          </div>
        </dl>

        {#if data.session.notes}
          <div class="mt-6 pt-6 border-t border-border">
            <h3 class="text-sm font-semibold text-text-secondary mb-2">Notes</h3>
            <p class="text-text text-sm">{data.session.notes}</p>
          </div>
        {/if}

        {#if data.session.devices.length > 0}
          <div class="mt-6 pt-6 border-t border-border">
            <h3 class="text-sm font-semibold text-text-secondary mb-3">Connected Devices</h3>
            <div class="flex flex-wrap gap-2">
              {#each data.session.devices as deviceId (deviceId)}
                {@const displayName = getDisplayNameFromMap(deviceId, deviceNicknameMap)}
                <span
                  class="bg-status-info text-status-info-fg text-sm px-3 py-1.5 rounded-lg border border-status-info-border"
                  title={deviceId !== displayName ? deviceId : undefined}
                >
                  {displayName}
                </span>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      <!-- Waveform Visualization -->
      <HistoricalWaveforms
        session={data.session}
        loading={false}
        deviceNicknames={deviceNicknameMap}
      />
    </div>
  </main>
</div>
