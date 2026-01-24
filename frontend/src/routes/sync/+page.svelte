<script lang="ts">
	import { onMount } from 'svelte';
	import PulsingCircle from '$lib/components/PulsingCircle.svelte';
	import Button from '$lib/components/buttons/Button.svelte';
	import IconButton from '$lib/components/buttons/IconButton.svelte';

	let isRunning = $state(false);
	let isFullscreen = $state(false);
	let soundEnabled = $state(true);
	let delayPattern = $state<number[]>([1000]);
	let delayPatternInput = $state('1000');

	let containerElement: HTMLElement;
	let pulsingCircle: PulsingCircle;

	onMount(() => {
		// Listen for fullscreen changes (e.g., user presses ESC)
		const handleFullscreenChange = () => {
			isFullscreen = !!document.fullscreenElement;
		};

		document.addEventListener('fullscreenchange', handleFullscreenChange);

		return () => {
			document.removeEventListener('fullscreenchange', handleFullscreenChange);
		};
	});

	function parseDelayPattern(input: string): number[] {
		try {
			// Try parsing as JSON array first
			const parsed = JSON.parse(input);
			if (Array.isArray(parsed) && parsed.every((v) => typeof v === 'number' && v > 0)) {
				return parsed;
			}
		} catch {
			// Try parsing as comma-separated values
			const values = input
				.split(',')
				.map((v) => parseInt(v.trim()))
				.filter((v) => !isNaN(v) && v > 0);
			if (values.length > 0) {
				return values;
			}
		}
		// Fallback to default
		return [1000];
	}

	function updateDelayPattern() {
		delayPattern = parseDelayPattern(delayPatternInput);
	}

	function toggleRunning() {
		isRunning = !isRunning;
	}

	async function toggleFullscreen() {
		if (!document.fullscreenElement) {
			try {
				await containerElement.requestFullscreen();
				isFullscreen = true;
			} catch (err) {
				console.error('Failed to enter fullscreen:', err);
			}
		} else {
			try {
				await document.exitFullscreen();
				isFullscreen = false;
			} catch (err) {
				console.error('Failed to exit fullscreen:', err);
			}
		}
	}

	function toggleSound() {
		soundEnabled = !soundEnabled;
	}

</script>

<svelte:head>
	<title>Device Synchronization - ECG Streaming</title>
</svelte:head>

<div
	bind:this={containerElement}
	class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex flex-col items-center justify-center relative"
>
	<!-- Exit button (top-left) -->
	<a href="/" class="absolute top-4 left-4">
		<Button variant="ghost" size="sm">← Exit</Button>
	</a>

	<!-- Fullscreen button (top-right) -->
	<div class="absolute top-4 right-4">
		<Button
			variant="ghost"
			size="sm"
			onclick={toggleFullscreen}
			title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
		>
			{isFullscreen ? '⊡' : '⛶'}
		</Button>
	</div>

	<!-- Central pulsing circle -->
	<div class="flex-1 flex items-center justify-center">
		<PulsingCircle
			bind:this={pulsingCircle}
			{delayPattern}
			{isRunning}
			{soundEnabled}
			size="w-80 h-80 md:w-96 md:h-96 lg:w-[32rem] lg:h-[32rem]"
		/>
	</div>

	<!-- Control panel -->
	<div class="w-full max-w-4xl p-6 bg-white border-t border-gray-200 shadow-lg">
		<div class="space-y-6">
			<!-- Main controls -->
			<div class="flex items-center justify-center gap-4">
				<!-- Start/Stop button -->
				<Button
					variant={isRunning ? 'danger' : 'success'}
					size="lg"
					onclick={toggleRunning}
					class="px-8"
				>
					{isRunning ? '⏸ Stop' : '▶ Start'}
				</Button>

				<!-- Sound toggle -->
				<Button
					variant={soundEnabled ? 'primary' : 'secondary'}
					size="lg"
					onclick={toggleSound}
					title={soundEnabled ? 'Mute sound' : 'Enable sound'}
				>
					{soundEnabled ? '🔊' : '🔇'}
				</Button>
			</div>

			<!-- Delay pattern input -->
			<div class="space-y-2">
				<label for="delay-pattern" class="block text-sm font-medium text-gray-700">
					Delay Pattern (milliseconds)
				</label>
				<div class="flex gap-2">
					<input
						id="delay-pattern"
						type="text"
						bind:value={delayPatternInput}
						onkeydown={(e) => e.key === 'Enter' && updateDelayPattern()}
						placeholder="[1000] or 1000,500"
						class="flex-1 px-4 py-2 bg-white text-gray-900 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
					/>
					<Button variant="primary" onclick={updateDelayPattern}>Apply</Button>
				</div>
			</div>
		</div>
	</div>
</div>
