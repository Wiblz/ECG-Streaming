/**
 * Shared formatting utility functions
 * Used across components for consistent data display
 */

/**
 * Format a Unix timestamp as relative time ("3m ago", "2h ago", etc.)
 */
export function formatTimeSince(timestamp: number): string {
	const now = Date.now() / 1000;
	const diff = now - timestamp;

	if (diff < 60) return 'just now';
	if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
	if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
	return `${Math.floor(diff / 86400)}d ago`;
}

/**
 * Format seconds as human-readable uptime ("5m", "2h 15m", etc.)
 */
export function formatUptime(seconds: number): string {
	if (seconds < 60) {
		return `${Math.floor(seconds)}s`;
	}
	if (seconds < 3600) {
		return `${Math.floor(seconds / 60)}m`;
	}
	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	return `${hours}h ${minutes}m`;
}

/**
 * Format a Unix timestamp as a localized date/time string
 */
export function formatTimestamp(timestamp: number): string {
	return new Date(timestamp * 1000).toLocaleString();
}
