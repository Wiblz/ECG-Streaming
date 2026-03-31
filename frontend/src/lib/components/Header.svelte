<script lang="ts">
  import { onMount, getContext } from 'svelte';
  import { page } from '$app/state';
  import { api } from '$lib/api/client';
  import { isMockMode, setMockMode } from '$lib/api/client';
  import { getActiveSession, isRecording, setActiveSession } from '$lib/state/session.svelte';
  import favicon from '$lib/assets/favicon.svg';

  interface Props {
    /**
     * Optional slot for page-specific action buttons
     */
    children?: import('svelte').Snippet;
  }

  let { children }: Props = $props();

  // Get version from context
  const versionContext = getContext<{ value: string }>('version');
  const version = $derived(versionContext?.value || '');

  // Session state
  const recording = $derived(isRecording());
  const activeSession = $derived(getActiveSession());
  let stoppingSession = $state(false);

  // Mock mode state
  let mockMode = $state(isMockMode());

  // Theme toggle: 'light' | 'dark'
  type Theme = 'light' | 'dark';

  let theme = $state<Theme>(
    (typeof localStorage !== 'undefined' && (localStorage.getItem('theme') as Theme)) ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  );

  function toggleTheme() {
    theme = theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', theme);
    document.documentElement.dataset.theme = theme;
  }

  // Load active session on mount
  onMount(async () => {
    try {
      const response = await api.getActiveSession();
      if (response.active && response.session) {
        setActiveSession(response.session);
      }
    } catch (err) {
      console.error('[Header] Failed to load active session:', err);
    }
  });

  function toggleMockMode() {
    mockMode = !mockMode;
    setMockMode(mockMode);
    // Reload page to refresh data
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  }

  async function handleStopSession() {
    if (stoppingSession) return;
    stoppingSession = true;
    try {
      const response = await api.stopSession();
      if (response.success) {
        setActiveSession(null);
        console.log(`[Header] Session ${response.session_id} stopped`);
      } else {
        console.error('[Header] Failed to stop session:', response.error);
      }
    } catch (err) {
      console.error('[Header] Error stopping session:', err);
    } finally {
      stoppingSession = false;
    }
  }

  // Determine current route for active nav styling
  function isActive(path: string): boolean {
    return page.url.pathname === path || page.url.pathname.startsWith(path + '/');
  }

  // Generate breadcrumbs from current path
  const breadcrumbs = $derived.by(() => {
    const path = page.url.pathname;
    if (path === '/') return [{ label: 'Dashboard', href: '/' }];
    if (path === '/devices') return [{ label: 'Devices', href: '/devices' }];
    if (path === '/sessions') return [{ label: 'Sessions', href: '/sessions' }];
    if (path === '/sync') return [{ label: 'Sync', href: '/sync' }];
    if (path.startsWith('/sessions/')) {
      const sessionId = path.split('/').pop();
      return [
        { label: 'Sessions', href: '/sessions' },
        { label: `Session #${sessionId}`, href: path }
      ];
    }
    return [{ label: 'Dashboard', href: '/' }];
  });
</script>

<header class="border-b border-border bg-surface/80 backdrop-blur-sm sticky top-0 z-10">
  <div class="px-6 py-4">
    <div class="flex items-center justify-between gap-6">
      <!-- Logo/Branding -->
      <div class="flex items-center gap-6">
        <a href="/" class="flex items-center gap-3 group">
          <img
            src={favicon}
            alt="ECG Streaming Logo"
            class="w-10 h-10 group-hover:scale-105 transition-transform"
          />
          <div class="flex flex-col">
            <span class="text-lg font-bold text-text">ECG Streaming</span>
            <span class="text-xs text-text-secondary -mt-0.5">Real-time cardiac monitoring</span>
          </div>
        </a>

        <!-- Main Navigation -->
        <nav class="hidden md:flex items-center gap-1">
          <a
            href="/"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/') &&
            page.url.pathname === '/'
              ? 'bg-surface-muted text-text'
              : 'text-text-secondary hover:text-text hover:bg-surface-hover'}"
          >
            Dashboard
          </a>
          <a
            href="/devices"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/devices')
              ? 'bg-surface-muted text-text'
              : 'text-text-secondary hover:text-text hover:bg-surface-hover'}"
          >
            Devices
          </a>
          <a
            href="/sessions"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/sessions')
              ? 'bg-surface-muted text-text'
              : 'text-text-secondary hover:text-text hover:bg-surface-hover'}"
          >
            Sessions
          </a>
          <a
            href="/sync"
            class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/sync')
              ? 'bg-surface-muted text-text'
              : 'text-text-secondary hover:text-text hover:bg-surface-hover'}"
          >
            Sync
          </a>
        </nav>
      </div>

      <!-- Breadcrumbs (visible on smaller screens instead of nav) -->
      <div class="flex-1 md:hidden">
        <nav class="flex items-center gap-2 text-sm">
          {#each breadcrumbs as crumb, i (crumb.href)}
            {#if i > 0}
              <svg
                class="w-4 h-4 text-text-muted"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 5l7 7-7 7"
                />
              </svg>
            {/if}
            <a
              href={crumb.href}
              class="text-text-secondary hover:text-text transition-colors {i ===
              breadcrumbs.length - 1
                ? 'font-medium text-text'
                : ''}"
            >
              {crumb.label}
            </a>
          {/each}
        </nav>
      </div>

      <!-- Page-specific actions (slot) -->
      <div class="flex items-center gap-3">
        <!-- Version Display -->
        {#if version}
          <span
            class="text-xs text-text-secondary px-2 py-1 font-medium"
            title="Application version"
          >
            v{version}
          </span>
        {/if}

        <!-- Stop Session Button (visible when recording) -->
        {#if recording && activeSession}
          <button
            onclick={handleStopSession}
            disabled={stoppingSession}
            class="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors bg-red-50 text-red-700 border-red-300 hover:bg-red-100 disabled:bg-surface-muted disabled:text-text-disabled disabled:border-border disabled:cursor-not-allowed flex items-center gap-1.5"
            title="Stop recording session #{activeSession.id}"
          >
            <div class="w-1.5 h-1.5 bg-red-600 rounded-full animate-pulse"></div>
            {stoppingSession ? 'Stopping...' : `Stop Session #${activeSession.id}`}
          </button>
        {/if}

        <!-- Theme Toggle -->
        <button
          onclick={toggleTheme}
          role="switch"
          aria-checked={theme === 'dark'}
          title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          class="relative inline-flex items-center w-14 h-7 rounded-full border border-border transition-colors bg-surface-muted dark:bg-status-info"
        >
          <span class="absolute inset-0 flex items-center justify-between px-1.5 text-xs pointer-events-none">
            <span>☀️</span>
            <span>🌙</span>
          </span>
          <span class="relative z-10 w-5 h-5 rounded-full bg-white shadow transition-transform translate-x-0.5 dark:translate-x-7"></span>
        </button>

        <!-- Mock Mode Toggle -->
        <button
          onclick={toggleMockMode}
          class="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors {mockMode
            ? 'bg-status-info text-status-info-fg border-status-info-border hover:bg-status-info-hover'
            : 'bg-surface-muted text-text-secondary border-border hover:bg-surface-hover'}"
          title={mockMode
            ? 'Using mock data - Click to use real API'
            : 'Using real API - Click to use mock data'}
        >
          {#if mockMode}
            🧪 Mock Mode
          {:else}
            📡 Live Mode
          {/if}
        </button>

        {#if children}
          {@render children()}
        {/if}
      </div>
    </div>
  </div>
</header>
