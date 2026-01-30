<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { BeepGenerator } from '$lib/utils/beep';

	interface Props {
		/**
		 * Array of delays in milliseconds between pulses
		 * Example: [1000] = steady 1 second interval
		 * Example: [1000, 500] = alternating 1s, 500ms, 500ms...
		 */
		delayPattern: number[];
		/**
		 * Whether the pulsing is currently active
		 */
		isRunning: boolean;
		/**
		 * Whether sound is enabled
		 */
		soundEnabled?: boolean;
		/**
		 * Size of the circle (applies to both width and height)
		 */
		size?: string;
	}

	let { delayPattern, isRunning, soundEnabled = true, size = 'w-64 h-64 md:w-96 md:h-96' }: Props =
		$props();

	let currentPatternIndex = $state(0);
	let isPulsing = $state(false);
	let timeoutId: number | null = null;
	let beepGenerator: BeepGenerator;

	onMount(() => {
		beepGenerator = new BeepGenerator();
	});

	onDestroy(() => {
		stopPulsing();
	});

	function pulse() {
		isPulsing = true;
		if (soundEnabled) {
			beepGenerator.beep();
		}

		// Reset pulse animation after animation duration
		setTimeout(() => {
			isPulsing = false;
		}, 300);
	}

	function scheduleNextPulse() {
		const delay = delayPattern[currentPatternIndex];
		currentPatternIndex = (currentPatternIndex + 1) % delayPattern.length;

		timeoutId = window.setTimeout(() => {
			pulse();
			if (isRunning) {
				scheduleNextPulse();
			}
		}, delay);
	}

	function startPulsing() {
		if (timeoutId !== null) return; // Already running
		currentPatternIndex = 0;
		pulse(); // Immediate first pulse
		scheduleNextPulse();
	}

	function stopPulsing() {
		if (timeoutId !== null) {
			clearTimeout(timeoutId);
			timeoutId = null;
		}
		currentPatternIndex = 0;
	}

	// Watch for isRunning changes
	$effect(() => {
		if (isRunning) {
			startPulsing();
		} else {
			stopPulsing();
		}
	});

	// Watch for delayPattern changes while running
	$effect(() => {
		// Create dependency on delayPattern
		const _ = delayPattern;
		if (isRunning) {
			stopPulsing();
			startPulsing();
		}
	});

	// Watch for soundEnabled changes
	$effect(() => {
		if (beepGenerator) {
			beepGenerator.setMuted(!soundEnabled);
		}
	});

	// Export current pattern index for parent component
	export function getCurrentPatternIndex(): number {
		return currentPatternIndex;
	}

	// Export next delay for display
	export function getNextDelay(): number {
		return delayPattern.length > 0 ? delayPattern[currentPatternIndex] : 1000;
	}
</script>

<div class="flex items-center justify-center">
	<div
		class="{size} rounded-full border-8 transition-all duration-300 {isPulsing
			? 'bg-blue-500 border-blue-600'
			: 'bg-gray-300 border-gray-400'}"
		style={isPulsing ? 'animation: pulse-ripple 0.6s ease-out;' : ''}
	></div>
</div>
