<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { AccelerometerWebSocket } from '$lib/api/accelerometerWebsocket';
  import { ECGWebSocket } from '$lib/api/websocket';
  import { api } from '$lib/api/client';
  import Card from '$lib/components/layout/Card.svelte';
  import ConnectionStatus from '$lib/components/status/ConnectionStatus.svelte';
  import DeviceCard from '$lib/components/devices/DeviceCard.svelte';
  import DeviceStatusPanel from '$lib/components/devices/DeviceStatusPanel.svelte';
  import Header from '$lib/components/layout/Header.svelte';
  import LiveWaveforms from '$lib/components/waveforms/LiveWaveforms.svelte';
  import SessionControl from '$lib/components/session/SessionControl.svelte';
  import StatsPanel from '$lib/components/status/StatsPanel.svelte';
  import LiveActivityMonitor from '$lib/components/status/LiveActivityMonitor.svelte';
  import { getDevices, setDevices } from '$lib/state/devices.svelte';
  import { samples as ecgSamples } from '$lib/state/ecg-data';
  import { samples as accSamples } from '$lib/state/acc-data';

  let ecgWs: ECGWebSocket;
  let accWs: AccelerometerWebSocket;

  // Reactive derived devices
  const devices = $derived(Array.from(getDevices().values()));

  function getDeviceNickname(id: string): string {
    return getDevices().get(id)?.nickname ?? id;
  }

  onMount(async () => {
    // Load device info with nicknames
    try {
      const response = await api.getAllDevices();
      setDevices(response.devices);
    } catch (e) {
      console.error('Failed to load device info:', e);
    }

    ecgWs = new ECGWebSocket();
    ecgWs.connect();

    accWs = new AccelerometerWebSocket();
    accWs.connect();
  });

  onDestroy(() => {
    ecgWs?.disconnect();
    accWs?.disconnect();
  });
</script>

<svelte:head>
  <title>Live Dashboard - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-surface-muted to-surface">
  <Header>
    <ConnectionStatus />
  </Header>

  <main class="container mx-auto px-6 py-8 max-w-7xl">
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Waveforms (2/3 width) -->
      <div class="lg:col-span-2">
        <LiveWaveforms />
      </div>

      <!-- Sidebar (1/3 width) -->
      <div class="space-y-6">
        <SessionControl />

        <Card title="Activity Monitor">
          <div class="space-y-4">
            <LiveActivityMonitor
              getSamplesMap={() => ecgSamples}
              getValue={(s) => s.raw_value}
              label="ECG"
              {getDeviceNickname}
              height={50}
              windowDuration={30}
            />
            <LiveActivityMonitor
              getSamplesMap={() => accSamples}
              getValue={(s) => s.magnitude}
              label="Accelerometer"
              {getDeviceNickname}
              height={50}
              windowDuration={30}
            />
          </div>
        </Card>

        <StatsPanel />

        <DeviceStatusPanel />

        <Card title="Streaming Devices" badge={devices.length}>
          {#if devices.length === 0}
            <div class="text-center py-8">
              <div class="text-4xl mb-2">📡</div>
              <p class="text-sm font-medium text-text mb-1">No devices streaming</p>
              <p class="text-xs text-text-secondary">Waiting for ECG data...</p>
            </div>
          {:else}
            <div class="space-y-3">
              {#each devices as device (device.device_id)}
                <DeviceCard {device} />
              {/each}
            </div>
          {/if}
        </Card>
      </div>
    </div>
  </main>
</div>
