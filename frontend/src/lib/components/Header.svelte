<script lang="ts">
	import { page } from '$app/state';
	import { getContext } from 'svelte';
	import favicon from '$lib/assets/favicon.svg';
	import { setMockMode, isMockMode } from '$lib/api/client';

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

	// Mock mode state
	let mockMode = $state(isMockMode());

	function toggleMockMode() {
		mockMode = !mockMode;
		setMockMode(mockMode);
		// Reload page to refresh data
		if (typeof window !== 'undefined') {
			window.location.reload();
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

<header class="border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
	<div class="container mx-auto px-6 py-4 max-w-7xl">
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
						<span class="text-lg font-bold text-gray-900">ECG Streaming</span>
						<span class="text-xs text-gray-500 -mt-0.5">Real-time cardiac monitoring</span>
					</div>
				</a>

				<!-- Main Navigation -->
				<nav class="hidden md:flex items-center gap-1">
					<a
						href="/"
						class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/') &&
						page.url.pathname === '/'
							? 'bg-gray-100 text-gray-900'
							: 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'}"
					>
						Dashboard
					</a>
					<a
						href="/devices"
						class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/devices')
							? 'bg-gray-100 text-gray-900'
							: 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'}"
					>
						Devices
					</a>
					<a
						href="/sessions"
						class="px-3 py-2 text-sm font-medium rounded-lg transition-colors {isActive('/sessions')
							? 'bg-gray-100 text-gray-900'
							: 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'}"
					>
						Sessions
					</a>
				</nav>
			</div>

			<!-- Breadcrumbs (visible on smaller screens instead of nav) -->
			<div class="flex-1 md:hidden">
				<nav class="flex items-center gap-2 text-sm">
					{#each breadcrumbs as crumb, i (crumb.href)}
						{#if i > 0}
							<svg
								class="w-4 h-4 text-gray-400"
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
							class="text-gray-600 hover:text-gray-900 transition-colors {i ===
							breadcrumbs.length - 1
								? 'font-medium text-gray-900'
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
					<span class="text-xs text-gray-500 px-2 py-1 font-medium" title="Application version">
						v{version}
					</span>
				{/if}

				<!-- Mock Mode Toggle -->
				<button
					onclick={toggleMockMode}
					class="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors {mockMode
						? 'bg-blue-100 text-blue-700 border-blue-300 hover:bg-blue-200'
						: 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200'}"
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
