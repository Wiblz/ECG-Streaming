<script lang="ts">
  import { statusEvents } from '$lib/state/status-events.svelte';
  import { formatUptime } from '$lib/utils/format';
  import CollectorHealthBadge from '$lib/components/ui/CollectorHealthBadge.svelte';
  import { TriangleAlert } from 'lucide-svelte';

  // Use reactive state from SSE client
  let collectors = $derived(statusEvents.getCollectors());
  let error = $derived(statusEvents.connectionStatus === 'error' ? statusEvents.error : null);
  let lastUpdate = $derived(statusEvents.lastUpdate);
</script>

<div class="collector-panel">
  <div class="panel-header">
    <h2>Collector Status</h2>
    {#if lastUpdate}
      <span class="last-update">Updated: {lastUpdate.toLocaleTimeString()}</span>
    {/if}
  </div>

  {#if error}
    <div class="error-message">
      <TriangleAlert class="w-4 h-4 flex-shrink-0" />
      <span>{error}</span>
    </div>
  {:else if collectors.length === 0}
    <div class="no-collectors">
      <p>No collectors connected</p>
    </div>
  {:else}
    <div class="collectors-grid">
      {#each collectors as collector (collector.collector_id)}
        <div class="collector-card">
          <div class="collector-header">
            <div class="collector-title">
              <h3>{collector.display_name}</h3>
              <span class="collector-id">{collector.collector_id}</span>
            </div>
            <CollectorHealthBadge health={collector.health} />
          </div>

          <div class="collector-info">
            <div class="info-row">
              <span class="label">Version:</span>
              <span class="value">{collector.version || 'N/A'}</span>
            </div>
            {#if collector.device_ids}
              <div class="info-row">
                <span class="label">Devices:</span>
                <span class="value">{collector.device_ids.length}</span>
              </div>
            {/if}
            {#if collector.active_devices !== undefined}
              <div class="info-row">
                <span class="label">Active:</span>
                <span class="value">{collector.active_devices}</span>
              </div>
            {/if}
            {#if collector.samples_sent !== undefined}
              <div class="info-row">
                <span class="label">Samples:</span>
                <span class="value">{collector.samples_sent.toLocaleString()}</span>
              </div>
            {/if}
            {#if collector.connected_at}
              <div class="info-row">
                <span class="label">Connected:</span>
                <span class="value">{formatUptime(Date.now() / 1000 - collector.connected_at)}</span
                >
              </div>
            {/if}
            {#if collector.connected}
              <div class="info-row">
                <span class="label">Status:</span>
                <span class="value">Connected</span>
              </div>
            {:else if collector.last_seen}
              <div class="info-row">
                <span class="label">Last Seen:</span>
                <span class="value"
                  >{formatUptime(Date.now() / 1000 - collector.last_seen)} ago</span
                >
              </div>
            {/if}
          </div>

          {#if collector.device_ids && collector.device_ids.length > 0}
            <div class="device-list">
              <span class="devices-label">Devices:</span>
              <div class="device-tags">
                {#each collector.device_ids as deviceId (deviceId)}
                  <span class="device-tag">{deviceId}</span>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .collector-panel {
    background: var(--color-surface);
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--color-border);
  }

  .panel-header h2 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .last-update {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
  }

  .error-message {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem;
    background: var(--color-status-error);
    border: 1px solid var(--color-status-error-border);
    border-radius: 6px;
    color: var(--color-status-error-fg);
  }

  .no-collectors {
    text-align: center;
    padding: 2rem;
    color: var(--color-text-secondary);
  }

  .collectors-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 1rem;
  }

  .collector-card {
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 1rem;
    background: var(--color-surface-muted);
    transition: box-shadow 0.2s;
  }

  .collector-card:hover {
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  }

  .collector-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }

  .collector-title h3 {
    margin: 0 0 0.25rem 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--color-text);
  }

  .collector-id {
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    font-family: monospace;
  }

  .collector-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
  }

  .info-row .label {
    color: var(--color-text-secondary);
    font-weight: 500;
  }

  .info-row .value {
    color: var(--color-text);
    font-weight: 400;
  }

  .device-list {
    border-top: 1px solid var(--color-border);
    padding-top: 1rem;
  }

  .devices-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    display: block;
    margin-bottom: 0.5rem;
  }

  .device-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .device-tag {
    display: inline-block;
    padding: 0.25rem 0.625rem;
    background: var(--color-border);
    border-radius: 4px;
    font-size: 0.75rem;
    color: var(--color-text);
    font-family: monospace;
  }
</style>
