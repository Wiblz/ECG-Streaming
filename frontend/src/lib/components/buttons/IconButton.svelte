<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		/**
		 * Button variant
		 */
		variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'warning' | 'ghost';
		/**
		 * Button size
		 */
		size?: 'sm' | 'md' | 'lg';
		/**
		 * Whether the button is disabled
		 */
		disabled?: boolean;
		/**
		 * Additional CSS classes
		 */
		class?: string;
		/**
		 * Click handler
		 */
		onclick?: (event: MouseEvent) => void;
		/**
		 * Title/tooltip (required for accessibility)
		 */
		title: string;
		/**
		 * Icon content
		 */
		children: Snippet;
	}

	let {
		variant = 'ghost',
		size = 'md',
		disabled = false,
		class: className = '',
		onclick,
		title,
		children
	}: Props = $props();

	// Base button styles
	const baseClasses =
		'inline-flex items-center justify-center rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

	// Size variants (square aspect ratio)
	const sizeClasses = {
		sm: 'w-8 h-8 text-xs',
		md: 'w-10 h-10 text-sm',
		lg: 'w-12 h-12 text-base'
	};

	// Variant styles
	const variantClasses = {
		primary: 'bg-blue-600 hover:bg-blue-700 text-white',
		secondary: 'bg-gray-600 hover:bg-gray-700 text-white',
		success: 'bg-green-600 hover:bg-green-700 text-white',
		danger: 'bg-red-600 hover:bg-red-700 text-white',
		warning: 'bg-yellow-600 hover:bg-yellow-700 text-white',
		ghost: 'bg-transparent hover:bg-gray-100 text-gray-700'
	};

	const buttonClasses = $derived(
		`${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`
	);
</script>

<button type="button" {title} {disabled} onclick={onclick} class={buttonClasses}>
	{@render children()}
</button>
