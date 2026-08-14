<script lang="ts">
  import { samples as accSamples } from '$lib/state/acc-data';
  import { samples as ecgSamples } from '$lib/state/ecg-data';
  import { getDevices } from '$lib/state/devices.svelte';
  import { ConnectionState, getAccWsState, getWsState } from '$lib/state/websocket.svelte';
  import { createDeviceNicknameMap } from '$lib/utils/device-names';
  import Button from '../ui/Button.svelte';
  import Card from '../layout/Card.svelte';
  import PauseButton from '../ui/PauseButton.svelte';
  import LiveWaveform from './LiveWaveform.svelte';
  import 'uplot/dist/uPlot.min.css';

  // Get connection states
  const ecgWsState = $derived(getWsState());
  const accWsState = $derived(getAccWsState());

  // Get devices for nicknames
  const devices = $derived(getDevices());
  const deviceNicknames = $derived(createDeviceNicknameMap(Array.from(devices.values())));

  // Shared state for verified points toggle
  let showVerifiedPoints = $state(false);

  // Collapsible state - will auto-collapse when >20 devices
  let isExpanded = $state(true);

  // Polling-based state (plain Maps have no reactivity)
  let ecgStreaming = $state(false);
  let accStreaming = $state(false);
  let activeDeviceCount = $state(0);
  let tooManyDevices = $state(false);

  // Poll for updates every 500ms (matches polling architecture)
  $effect(() => {
    const interval = setInterval(() => {
      // Update streaming indicators
      ecgStreaming = ecgWsState === ConnectionState.CONNECTED && ecgSamples.size > 0;
      accStreaming = accWsState === ConnectionState.CONNECTED && accSamples.size > 0;

      // Count unique devices across both ECG and ACC
      const ecgDevices = Array.from(ecgSamples.keys());
      const accDevices = Array.from(accSamples.keys());
      const allDevices = [...ecgDevices, ...accDevices];
      const newCount = new Set(allDevices).size;

      // Update device count and auto-collapse if needed
      if (newCount !== activeDeviceCount) {
        activeDeviceCount = newCount;
        tooManyDevices = activeDeviceCount > 20;

        // Auto-collapse when exceeding threshold
        if (tooManyDevices && isExpanded) {
          isExpanded = false;
        }
      }
    }, 500);

    return () => clearInterval(interval);
  });
</script>

<Card title="Live Waveforms" padding={isExpanded ? 'normal' : 'none'}>
  {#snippet headerActions()}
    {#if isExpanded}
      <Button
        variant={showVerifiedPoints ? 'success' : 'ghost'}
        size="sm"
        disabled={tooManyDevices}
        onclick={() => {
          showVerifiedPoints = !showVerifiedPoints;
        }}
        title={tooManyDevices
          ? `Verified points disabled with ${activeDeviceCount} devices (max 20 for performance)`
          : 'Toggle verified sample points (samples with direct Polar timestamps)'}
      >
        Verified Points
      </Button>
      <PauseButton />
    {/if}
    <Button
      variant="ghost"
      size="sm"
      disabled={tooManyDevices && !isExpanded}
      onclick={() => {
        isExpanded = !isExpanded;
      }}
      title={tooManyDevices && !isExpanded
        ? `Waveforms disabled with ${activeDeviceCount} devices (max 20 for performance)`
        : isExpanded
          ? 'Collapse waveforms'
          : 'Expand waveforms'}
    >
      {isExpanded ? 'Collapse' : 'Expand'}
    </Button>
  {/snippet}

  {#if isExpanded}
    <div class="space-y-6">
      <!-- ECG Waveform -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-text">ECG</h3>
          {#if ecgStreaming}
            <div class="flex items-center gap-1.5 text-xs text-text-secondary">
              <div class="w-1.5 h-1.5 bg-status-success-fg rounded-full animate-pulse"></div>
              <span>Active</span>
            </div>
          {:else}
            <div class="flex items-center gap-1.5 text-xs text-text-muted">
              <div class="w-1.5 h-1.5 bg-status-neutral-fg rounded-full"></div>
              <span>Idle</span>
            </div>
          {/if}
        </div>
        <LiveWaveform
          samples={ecgSamples}
          wsState={ecgWsState}
          {deviceNicknames}
          getValue={(s) => s.raw_value}
          yAxisLabel="Amplitude (mV)"
          title="ECG"
          emptyMessage="Waiting for ECG data..."
          standalone={false}
          {showVerifiedPoints}
        />
      </div>

      <!-- Divider -->
      <div class="border-t border-border"></div>

      <!-- Accelerometer Waveform -->
      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-text">Accelerometer</h3>
          {#if accStreaming}
            <div class="flex items-center gap-1.5 text-xs text-text-secondary">
              <div class="w-1.5 h-1.5 bg-status-success-fg rounded-full animate-pulse"></div>
              <span>Active</span>
            </div>
          {:else}
            <div class="flex items-center gap-1.5 text-xs text-text-muted">
              <div class="w-1.5 h-1.5 bg-status-neutral-fg rounded-full"></div>
              <span>Idle</span>
            </div>
          {/if}
        </div>
        <LiveWaveform
          samples={accSamples}
          wsState={accWsState}
          {deviceNicknames}
          getValue={(s) => s.magnitude}
          yAxisLabel="Magnitude (g)"
          title="Accelerometer"
          emptyMessage="Waiting for accelerometer data..."
          standalone={false}
          {showVerifiedPoints}
        />
      </div>
    </div>
  {/if}
</Card>
