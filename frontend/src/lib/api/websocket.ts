import { mergeDevice } from '$lib/state/devices.svelte';
import { addSamples } from '$lib/state/ecg-data';
import { ConnectionState, setWsError, setWsState } from '$lib/state/websocket.svelte';
import type { BufferedECGSample, DataMessage, InitMessage } from '$lib/types/api';
import { flattenGroupedSamples } from '$lib/utils/samples';

const DEFAULT_PATH = '/ws/ecg';

function resolveDefaultUrl(): string {
  // Prefer explicit override via Vite env
  const envUrl = import.meta.env.VITE_AGGREGATOR_WS as string | undefined;
  if (envUrl) return envUrl;

  // Fallback to explicit HTTP base env, swap to ws
  const httpBase = import.meta.env.VITE_AGGREGATOR_HTTP as string | undefined;
  if (httpBase) {
    const url = new URL(httpBase);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = DEFAULT_PATH;
    return url.toString();
  }

  // Browser origin: default to same host but force the API port
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    return `${protocol}//${host}:7999${DEFAULT_PATH}`;
  }

  // Last resort: dev default
  return `ws://localhost:7999${DEFAULT_PATH}`;
}

export class ECGWebSocket {
  private ws: WebSocket | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private url: string;
  private shouldReconnect: boolean = true;
  private messageCount: number = 0;

  constructor(url: string = resolveDefaultUrl()) {
    this.url = url;
  }

  connect() {
    console.log('[WebSocket] Attempting to connect to:', this.url);
    setWsState(ConnectionState.CONNECTING);
    setWsError(null);
    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('[WebSocket] Connected successfully');
        setWsState(ConnectionState.CONNECTED);
      };

      this.ws.onmessage = (event) => {
        const receiveTime = performance.now();
        const msg = JSON.parse(event.data);

        if (msg.type === 'init') {
          this.handleInit(msg as InitMessage);
        } else if (msg.type === 'data') {
          const processStart = performance.now();
          this.handleData(msg as DataMessage);
          const processDuration = performance.now() - processStart;

          const parseAndProcessTime = performance.now() - receiveTime;
          if (parseAndProcessTime > 16) {
            console.warn(
              `[WebSocket] Slow message processing: ${parseAndProcessTime.toFixed(1)}ms (parse+process: ${processDuration.toFixed(1)}ms), samples: ${msg.count}`
            );
          }

          // Log every 60 messages (~2 seconds at 30 FPS)
          if (!this.messageCount) this.messageCount = 0;
          this.messageCount++;
          if (this.messageCount % 60 === 0) {
            console.log(
              `[WebSocket] Received ${this.messageCount} messages, last had ${msg.count} samples`
            );
          }
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error occurred:', error);
        setWsState(ConnectionState.ERROR);
        setWsError('Connection error');
      };

      this.ws.onclose = (event) => {
        console.log('[WebSocket] Connection closed. Code:', event.code, 'Reason:', event.reason);
        setWsState(ConnectionState.DISCONNECTED);
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };
    } catch (error) {
      console.error('[WebSocket] Failed to create WebSocket:', error);
      setWsState(ConnectionState.ERROR);
      setWsError('Failed to create WebSocket connection');
    }
  }

  private handleInit(msg: InitMessage) {
    console.log('Devices initialized:', msg.devices);
    // Merge devices from init message (preserves existing data like nicknames)
    msg.devices.forEach((deviceId) => {
      mergeDevice(deviceId, { sync_ready: false });
    });
  }

  private handleData(msg: DataMessage) {
    // Flatten grouped data back into samples array with device_id
    const samples = flattenGroupedSamples<BufferedECGSample>(msg.devices);

    if (samples.length > 0) {
      addSamples(samples);
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) return;

    this.reconnectTimeout = setTimeout(() => {
      console.log('Attempting to reconnect...');
      this.reconnectTimeout = null;
      this.connect();
    }, 2000);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    this.ws?.close();
  }
}
