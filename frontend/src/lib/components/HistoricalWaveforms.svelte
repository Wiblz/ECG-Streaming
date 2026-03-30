<script lang="ts">
  import type { Session, SessionSample, SessionAccelerometerSample } from '$lib/types/api';
  import { api } from '$lib/api/client';
  import Button from './buttons/Button.svelte';
  import Card from './Card.svelte';
  import Waveform from './Waveform.svelte';
  import 'uplot/dist/uPlot.min.css';

  interface Props {
    session: Session;
    loading?: boolean;
    deviceNicknames?: Map<string, string>;
  }

  let { session, loading = false, deviceNicknames }: Props = $props();

  // Shared state for verified points toggle
  let showVerifiedPoints = $state(false);

  // Shared state for time sync
  let timeSyncEnabled = $state(false);
  let sharedTimeWindow = $state<{ minTime: number; maxTime: number } | null>(null);

  // Determine if session has both ECG and ACC data
  const hasBothSignals = $derived(session.ecg_sample_count > 0 && session.acc_sample_count > 0);

  // Handler for time window changes from either chart
  function handleTimeWindowChange(window: { minTime: number; maxTime: number }) {
    if (timeSyncEnabled) {
      sharedTimeWindow = window;
    }
  }
</script>

<Card title="Session Waveforms">
  {#snippet headerActions()}
    {#if hasBothSignals}
      <Button
        variant={timeSyncEnabled ? 'success' : 'ghost'}
        size="sm"
        onclick={() => {
          timeSyncEnabled = !timeSyncEnabled;
        }}
        title="Synchronize time windows between ECG and Accelerometer"
      >
        Time Sync
      </Button>
    {/if}
    <Button
      variant={showVerifiedPoints ? 'success' : 'ghost'}
      size="sm"
      onclick={() => {
        showVerifiedPoints = !showVerifiedPoints;
      }}
      title="Toggle verified sample points (samples with direct Polar timestamps)"
    >
      Verified Points
    </Button>
  {/snippet}

  <div class="mb-4 text-xs text-text-secondary">
    Middle-click + drag to pan, scroll wheel to zoom. Data loads dynamically.
  </div>

  <div class="space-y-6">
    <!-- ECG Waveform -->
    <div>
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-text">ECG</h3>
      </div>
      {#key showVerifiedPoints}
        <Waveform
          {session}
          {loading}
          {showVerifiedPoints}
          {deviceNicknames}
          {timeSyncEnabled}
          {sharedTimeWindow}
          onTimeWindowChange={handleTimeWindowChange}
          alignMode="linear"
          fetchSamples={api.getSessionSamples}
          getValue={(s: SessionSample) => s.raw_value}
          yAxisLabel="Amplitude (mV)"
          formatTooltip={(sample: SessionSample, xVal) => {
            const verified = sample.time_verified ? ' ✓' : '';
            return `
							<table style="border-collapse: collapse;">
								<tr><td style="padding: 1px 4px 1px 0;">ID:</td><td style="padding: 1px 0;">${sample.id}</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Value:</td><td style="padding: 1px 0;">${sample.raw_value}</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(4)}s</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Global:</td><td style="padding: 1px 0;">${sample.global_time.toFixed(3)}s</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Polar:</td><td style="padding: 1px 0;">${(sample.polar_clock_us / 1_000_000).toFixed(3)}s${verified}</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Receiver:</td><td style="padding: 1px 0;">${(sample.receiver_clock_us / 1_000_000).toFixed(3)}s</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Wall:</td><td style="padding: 1px 0;">${(sample.wall_clock_us / 1_000_000).toFixed(3)}s</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Conf:</td><td style="padding: 1px 0;">${(sample.confidence * 100).toFixed(0)}%</td></tr>
							</table>
						`;
          }}
        />
      {/key}
    </div>

    <!-- Divider -->
    <div class="border-t border-border"></div>

    <!-- Accelerometer Waveform -->
    <div>
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-text">Accelerometer</h3>
      </div>
      {#key showVerifiedPoints}
        <Waveform
          {session}
          {loading}
          {showVerifiedPoints}
          {deviceNicknames}
          {timeSyncEnabled}
          {sharedTimeWindow}
          onTimeWindowChange={handleTimeWindowChange}
          alignMode="linear"
          fetchSamples={api.getSessionAccelerometerSamples}
          getValue={(s: SessionAccelerometerSample) => s.magnitude}
          yAxisLabel="Magnitude (g)"
          formatTooltip={(sample: SessionAccelerometerSample, xVal) => {
            const verified = sample.time_verified ? ' ✓' : '';
            return `
							<table style="border-collapse: collapse;">
								<tr><td style="padding: 1px 4px 1px 0;">ID:</td><td style="padding: 1px 0;">${sample.id}</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">X:</td><td style="padding: 1px 0;">${sample.x.toFixed(3)}g</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Y:</td><td style="padding: 1px 0;">${sample.y.toFixed(3)}g</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Z:</td><td style="padding: 1px 0;">${sample.z.toFixed(3)}g</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Mag:</td><td style="padding: 1px 0;">${sample.magnitude.toFixed(3)}g</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Time:</td><td style="padding: 1px 0;">${xVal.toFixed(4)}s</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Global:</td><td style="padding: 1px 0;">${sample.global_time.toFixed(3)}s</td></tr>
								<tr><td style="padding: 1px 4px 1px 0;">Polar:</td><td style="padding: 1px 0;">${(sample.polar_clock_us / 1_000_000).toFixed(3)}s${verified}</td></tr>
							</table>
						`;
          }}
        />
      {/key}
    </div>
  </div>
</Card>
