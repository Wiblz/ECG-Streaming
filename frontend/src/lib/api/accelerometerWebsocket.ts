import { addSamples } from '$lib/state/acc-data.svelte';
import { ConnectionState, setAccWsError, setAccWsState } from '$lib/state/websocket.svelte';
import type {
	AccelerometerDataMessage,
	BufferedAccelerometerSample,
	InitMessage
} from '$lib/types/api';
import { flattenGroupedSamples } from '$lib/utils/samples';

const DEFAULT_PATH = '/ws/accelerometer';

function resolveDefaultUrl(): string {
	// Prefer explicit override via Vite env
	const envUrl = import.meta.env.VITE_AGGREGATOR_WS as string | undefined;
	if (envUrl) {
		// Replace /ws/ecg with /ws/accelerometer
		return envUrl.replace('/ws/ecg', DEFAULT_PATH);
	}

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

export class AccelerometerWebSocket {
	private ws: WebSocket | null = null;
	private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
	private url: string;
	private shouldReconnect: boolean = true;

	constructor(url: string = resolveDefaultUrl()) {
		this.url = url;
	}

	connect() {
		console.log('[AccelerometerWebSocket] Attempting to connect to:', this.url);
		setAccWsState(ConnectionState.CONNECTING);
		setAccWsError(null);
		this.shouldReconnect = true;

		try {
			this.ws = new WebSocket(this.url);

			this.ws.onopen = () => {
				console.log('[AccelerometerWebSocket] Connected successfully');
				setAccWsState(ConnectionState.CONNECTED);
			};

			this.ws.onmessage = (event) => {
				const msg = JSON.parse(event.data);

				if (msg.type === 'init') {
					this.handleInit(msg as InitMessage);
				} else if (msg.type === 'data') {
					this.handleData(msg as AccelerometerDataMessage);
				}
			};

			this.ws.onerror = (error) => {
				console.error('[AccelerometerWebSocket] Error occurred:', error);
				setAccWsState(ConnectionState.ERROR);
				setAccWsError('Connection error');
			};

			this.ws.onclose = (event) => {
				console.log(
					'[AccelerometerWebSocket] Connection closed. Code:',
					event.code,
					'Reason:',
					event.reason
				);
				setAccWsState(ConnectionState.DISCONNECTED);
				if (this.shouldReconnect) {
					this.scheduleReconnect();
				}
			};
		} catch (error) {
			console.error('[AccelerometerWebSocket] Failed to create WebSocket:', error);
			setAccWsState(ConnectionState.ERROR);
			setAccWsError('Failed to create WebSocket connection');
		}
	}

	private handleInit(msg: InitMessage) {
		console.log('[AccelerometerWebSocket] Devices initialized:', msg.devices);
		// Devices are already initialized by ECG WebSocket
	}

	private handleData(msg: AccelerometerDataMessage) {
		// Flatten grouped data back into samples array with device_id
		const samples = flattenGroupedSamples<BufferedAccelerometerSample>(msg.devices);

		if (samples.length > 0) {
			addSamples(samples);
		}
	}

	private scheduleReconnect() {
		if (this.reconnectTimeout) return;

		this.reconnectTimeout = setTimeout(() => {
			console.log('[AccelerometerWebSocket] Attempting to reconnect...');
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
