import type { ApiClient } from '$lib/types/api';
import { HttpClient } from './httpClient';
import { MockClient } from './mockClient';

const MOCK_MODE_KEY = 'ecg-streaming-mock-mode';

/**
 * Current active client instance
 */
let currentClient: ApiClient;
let mockClientInstance: MockClient | null = null;

/**
 * Initialize client based on localStorage
 */
function initializeClient(): ApiClient {
	if (typeof window !== 'undefined') {
		const mockMode = localStorage.getItem(MOCK_MODE_KEY) === 'true';
		if (mockMode) {
			mockClientInstance = new MockClient();
			return mockClientInstance;
		}
	}
	return new HttpClient();
}

// Initialize on module load
currentClient = initializeClient();

/**
 * Check if mock mode is enabled
 */
export function isMockMode(): boolean {
	return currentClient instanceof MockClient;
}

/**
 * Enable or disable mock mode
 */
export function setMockMode(enabled: boolean): void {
	// Persist to localStorage
	if (typeof window !== 'undefined') {
		if (enabled) {
			localStorage.setItem(MOCK_MODE_KEY, 'true');
		} else {
			localStorage.removeItem(MOCK_MODE_KEY);
		}
	}

	// Cleanup old mock client if exists
	if (mockClientInstance) {
		mockClientInstance.destroy();
		mockClientInstance = null;
	}

	// Switch client
	if (enabled) {
		mockClientInstance = new MockClient();
		currentClient = mockClientInstance;
	} else {
		currentClient = new HttpClient();
	}
}

/**
 * API client proxy that forwards all calls to the current implementation.
 * This automatically works with any method defined in the ApiClient interface.
 */
export const api = new Proxy({} as ApiClient, {
	get(_target, prop) {
		const value = currentClient[prop as keyof ApiClient];
		// Bind methods to the current client to preserve 'this' context
		return typeof value === 'function' ? value.bind(currentClient) : value;
	}
});

/**
 * Get the API base URL for direct HTTP connections (WebSocket, SSE, etc.)
 */
export function get_api_base_url(): string {
	const envBase = import.meta.env.VITE_AGGREGATOR_HTTP as string | undefined;
	return (
		envBase ??
		(typeof window !== 'undefined'
			? `${window.location.protocol}//${window.location.hostname}:7999`
			: 'http://localhost:7999')
	);
}
