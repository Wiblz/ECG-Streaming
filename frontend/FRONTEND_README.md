# ECG Streaming Dashboard

A real-time ECG data visualization dashboard built with SvelteKit 5, Tailwind CSS 4, and D3.js.

## Quick Start

```bash
# Install dependencies (already done)
pnpm install

# Run development server
pnpm run dev
# Open http://localhost:5173

# Build for production
pnpm run build
```

## Features

- ✅ Real-time ECG waveform visualization using D3.js
- ✅ WebSocket connection with auto-reconnect (2s interval)
- ✅ Device status monitoring with sync confidence
- ✅ System statistics dashboard (polls every 5s)
- ✅ Modern Svelte 5 runes ($state, $derived, $effect)
- ✅ TypeScript with full type safety
- ✅ Tailwind CSS 4 for styling
- ✅ Static site generation

## Backend Connection

The dashboard connects to the ECG aggregator backend:

- **REST API**: http://localhost:8000
- **WebSocket**: ws://localhost:8000/ws/ecg

⚠️ **Important**: Make sure the ECG aggregator is running before starting the frontend!

## Development Commands

```bash
# Type checking
pnpm run check

# Linting
pnpm run lint

# Format code
pnpm run format

# Build for production
pnpm run build

# Preview production build
pnpm run preview
```

## Project Structure

```
src/
├── lib/
│   ├── api/                    # API clients
│   │   ├── client.ts           # REST API client
│   │   └── websocket.ts        # WebSocket client with auto-reconnect
│   ├── components/             # Svelte 5 components
│   │   ├── ConnectionStatus.svelte
│   │   ├── DeviceCard.svelte
│   │   ├── ECGWaveform.svelte  # D3.js canvas visualization
│   │   └── StatsPanel.svelte
│   ├── state/                  # Reactive state (.svelte.ts)
│   │   ├── devices.svelte.ts
│   │   ├── ecg-data.svelte.ts  # 30s circular buffer
│   │   └── websocket.svelte.ts
│   └── types/                  # TypeScript interfaces
│       └── api.ts
├── routes/                     # SvelteKit routes
│   ├── +layout.svelte
│   ├── +layout.ts
│   └── +page.svelte            # Main dashboard
├── app.css                     # Tailwind imports
└── app.html                    # HTML template
```

## Modern Svelte 5 Features

This project uses Svelte 5's modern rune-based reactivity:

### Reactive State (`.svelte.ts` files)

```typescript
// Instead of writable() stores, use $state runes
let _state = $state(ConnectionState.DISCONNECTED);

export function getWsState() {
	return _state; // Auto-tracked reactivity
}
```

### Components with Runes

```svelte
<script lang="ts">
	// Props with $props()
	let { device }: Props = $props();

	// Derived values with $derived
	const syncLabel = $derived(device.sync_ready ? 'Synced' : 'Syncing...');

	// Effects with $effect (auto-tracks dependencies)
	$effect(() => {
		console.log('Device changed:', device);
	});
</script>
```

## Components Overview

### ECGWaveform.svelte

- Canvas-based rendering with D3.js scales
- Real-time updates via `$effect` (runs when samples change)
- Multi-device support with color coding
- Grid background for better readability
- 30-second circular buffer

### ConnectionStatus.svelte

- Reactive WebSocket state indicator
- Color-coded: 🟢 Connected, 🟡 Connecting, 🔴 Disconnected/Error
- Auto-updates via derived state

### DeviceCard.svelte

- Shows device sync status
- Displays confidence percentage
- Sample count and drift (ppm) metrics

### StatsPanel.svelte

- Polls system stats every 5 seconds
- Buffer utilization metrics
- Total samples and dropped counts

## WebSocket Protocol

The dashboard receives two types of messages:

### Init Message (on connect)

```json
{
	"type": "init",
	"devices": ["Polar H10 ABC123"],
	"timestamp": 1733599200.0
}
```

### Data Message (30 FPS / ~33ms)

```json
{
	"type": "data",
	"samples": [
		{
			"device_id": "Polar H10 ABC123",
			"global_time": 1733599230.5,
			"raw_value": 512,
			"confidence": 0.95
		}
	],
	"timestamp": 1733599230.7,
	"count": 1
}
```

## Build Output

After running `pnpm run build`, static files are generated in the `build/` directory:

```
build/
├── _app/           # JavaScript and CSS bundles
├── index.html      # Main HTML file
└── robots.txt
```

These can be deployed to any static hosting service (Vercel, Netlify, GitHub Pages, etc.)

## Notes

- All files use **Svelte 5 syntax** (runes, not stores)
- Shared reactive state is in **`.svelte.ts` files** (not `.js`)
- Components use **`$props()`** instead of `export let`
- No shadcn-svelte installed yet (using custom Tailwind components)
- Auto-reconnect WebSocket with 2-second retry delay
- ECG data automatically pruned to last 30 seconds
