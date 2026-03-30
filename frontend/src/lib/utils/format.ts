/**
 * Shared formatting utility functions
 * Used across components for consistent data display
 */

import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import relativeTime from 'dayjs/plugin/relativeTime';

// Enable plugins
dayjs.extend(relativeTime);
dayjs.extend(duration);

/**
 * Format a Unix timestamp as relative time ("3m ago", "2h ago", etc.)
 */
export function formatTimeSince(timestamp: number): string {
  return dayjs.unix(timestamp).fromNow();
}

/**
 * Format seconds as human-readable uptime ("5m", "2h 15m", etc.)
 */
export function formatUptime(seconds: number): string {
  const d = dayjs.duration(seconds, 'seconds');

  if (seconds < 60) {
    return `${Math.floor(seconds)}s`;
  }
  if (seconds < 3600) {
    return `${d.minutes()}m`;
  }
  const hours = d.hours();
  const minutes = d.minutes();
  return `${hours}h ${minutes}m`;
}

/**
 * Format a Unix timestamp as a localized date/time string
 * Example: "Jan 10, 2026 2:30 PM"
 */
export function formatTimestamp(timestamp: number): string {
  return dayjs.unix(timestamp).format('MMM D, YYYY h:mm A');
}

/**
 * Format a Unix timestamp as a full date/time string
 * Example: "January 10, 2026 at 2:30:45 PM"
 */
export function formatFullTimestamp(timestamp: number): string {
  return dayjs.unix(timestamp).format('MMMM D, YYYY [at] h:mm:ss A');
}

/**
 * Format a Unix timestamp as date only
 * Example: "Jan 10, 2026"
 */
export function formatDate(timestamp: number): string {
  return dayjs.unix(timestamp).format('MMM D, YYYY');
}

/**
 * Format a Unix timestamp as time only
 * Example: "2:30 PM"
 */
export function formatTime(timestamp: number): string {
  return dayjs.unix(timestamp).format('h:mm A');
}

/**
 * Format duration in seconds as human-readable string
 * Example: "2h 15m 30s"
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === 0) return '0s';

  const d = dayjs.duration(seconds, 'seconds');
  const hours = Math.floor(d.asHours());
  const mins = d.minutes();
  const secs = d.seconds();

  if (hours > 0) {
    return `${hours}h ${mins}m ${secs}s`;
  } else if (mins > 0) {
    return `${mins}m ${secs}s`;
  }
  return `${secs}s`;
}
