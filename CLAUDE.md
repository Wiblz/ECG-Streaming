## Frontend Stack

The frontend uses:
- **SvelteKit** with **Svelte 5** (runes API)
- **Vite** as build tool
- **TypeScript** for type safety
- **Tailwind CSS v4** for styling (using `@theme` directive)
- **pnpm** as package manager
- **D3.js** for data visualization

### Frontend Scripts (run with pnpm)

```bash
pnpm dev          # Start development server
pnpm build        # Build for production
pnpm preview      # Preview production build
pnpm check        # Type check with svelte-check
pnpm check:watch  # Type check in watch mode
pnpm format       # Format code with prettier
pnpm lint         # Lint code with eslint and prettier
```

**IMPORTANT**: Always use `pnpm` for frontend commands, NOT `npm`.

## Styling & Theming Conventions

### Color System

All UI colors are defined using **Tailwind CSS v4's `@theme` directive** in `frontend/src/app.css`:

```css
@theme {
  --color-status-success: oklch(0.85 0.15 145);      /* Streaming, healthy, active */
  --color-status-success-fg: oklch(0.35 0.15 145);
  --color-status-success-border: oklch(0.75 0.12 145);

  --color-status-info: oklch(0.85 0.12 230);         /* Connected, ready */
  --color-status-info-fg: oklch(0.35 0.12 230);
  --color-status-info-border: oklch(0.75 0.10 230);

  --color-status-warning: oklch(0.90 0.15 85);       /* Connecting, degraded */
  --color-status-warning-fg: oklch(0.40 0.15 85);
  --color-status-warning-border: oklch(0.80 0.12 85);

  --color-status-error: oklch(0.85 0.18 25);         /* Error, failed */
  --color-status-error-fg: oklch(0.40 0.18 25);
  --color-status-error-border: oklch(0.75 0.15 25);

  --color-status-neutral: oklch(0.90 0 0);           /* Disconnected, idle, unknown */
  --color-status-neutral-fg: oklch(0.45 0 0);
  --color-status-neutral-border: oklch(0.80 0 0);
}
```

### Using Colors in Components

**DO NOT** hardcode Tailwind colors like `bg-green-500` or `text-blue-700` directly in components.

**Instead**, define color mapping functions within each component that use the theme colors:

```svelte
<script lang="ts">
  import { formatTimeSince, formatUptime } from '$lib/utils/format';

  // Define color mapping inside the component
  function getDeviceStatusColors(status: DeviceStatus['status']) {
    switch (status) {
      case 'STREAMING':
        return {
          bg: 'bg-status-success',
          text: 'text-status-success-fg',
          border: 'border-status-success-border'
        };
      case 'ERROR':
        return {
          bg: 'bg-status-error',
          text: 'text-status-error-fg',
          border: 'border-status-error-border'
        };
      // ... etc
    }
  }
</script>

<!-- Use in template with {@const} -->
{#each devices as device}
  {@const colors = getDeviceStatusColors(device.status)}
  <div class="border {colors.border} rounded-lg p-3 {colors.bg}">
    <span class={colors.text}>{device.status}</span>
  </div>
{/each}
```

### Shared Utilities

`frontend/src/lib/utils/format.ts` contains shared formatting functions:

```typescript
import { formatTimeSince, formatUptime, formatTimestamp } from '$lib/utils/format';

formatTimeSince(timestamp)  // "3m ago", "2h ago"
formatUptime(seconds)        // "5m", "2h 15m"
formatTimestamp(timestamp)   // Localized date/time string
```

### Why This Approach?

1. **Single source of truth for colors**: Defined once in `app.css` using Tailwind's `@theme`
2. **Component self-containment**: Each component manages its own styling logic
3. **Svelte-native patterns**: Uses `{@const}` and component functions instead of external helpers
4. **Easy theme changes**: Modify color tokens in `app.css`, affects all references
5. **Shared utilities for common logic**: Time formatting is truly reusable across components

## Svelte MCP Tools

You have access to the Svelte MCP server for comprehensive Svelte 5 and SvelteKit documentation:

### 1. list-sections

Use this FIRST to discover all available documentation sections. Returns a structured list with titles, use_cases, and paths.
When asked about Svelte or SvelteKit topics, ALWAYS use this tool at the start of the chat to find relevant sections.

### 2. get-documentation

Retrieves full documentation content for specific sections. Accepts single or multiple sections.
After calling the list-sections tool, you MUST analyze the returned documentation sections (especially the use_cases field) and then use the get-documentation tool to fetch ALL documentation sections that are relevant for the user's task.

### 3. svelte-autofixer

Analyzes Svelte code and returns issues and suggestions.
You MUST use this tool whenever writing Svelte code before sending it to the user. Keep calling it until no issues or suggestions are returned.

### 4. playground-link

Generates a Svelte Playground link with the provided code.
After completing the code, ask the user if they want a playground link. Only call this tool after user confirmation and NEVER if code was written to files in their project.
