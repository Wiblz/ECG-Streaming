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
		 * Whether the button is in a loading state
		 */
		loading?: boolean;
		/**
		 * Additional CSS classes
		 */
		class?: string;
		/**
		 * Button type attribute
		 */
		type?: 'button' | 'submit' | 'reset';
		/**
		 * Click handler
		 */
		onclick?: (event: MouseEvent) => void;
		/**
		 * Title/tooltip
		 */
		title?: string;
		/**
		 * Icon before text (optional snippet)
		 */
		icon?: Snippet;
		/**
		 * Button content
		 */
		children?: Snippet;
	}

	let {
		variant = 'primary',
		size = 'md',
		disabled = false,
		loading = false,
		class: className = '',
		type = 'button',
		onclick,
		title,
		icon,
		children
	}: Props = $props();

	// Base button styles
	const baseClasses =
		'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

	// Size variants
	const sizeClasses = {
		sm: 'px-3 py-1.5 text-xs',
		md: 'px-4 py-2 text-sm',
		lg: 'px-6 py-3 text-base'
	};

	// Variant styles
	const variantClasses = {
		primary: 'bg-blue-600 hover:bg-blue-700 text-white',
		secondary: 'bg-gray-600 hover:bg-gray-700 text-white',
		success: 'bg-green-600 hover:bg-green-700 text-white',
		danger: 'bg-red-600 hover:bg-red-700 text-white',
		warning: 'bg-yellow-600 hover:bg-yellow-700 text-white',
		ghost:
			'bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300 disabled:bg-gray-50'
	};

	const buttonClasses = $derived(
		`${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`
	);
</script>

<button
	{type}
	{title}
	disabled={disabled || loading}
	onclick={onclick}
	class={buttonClasses}
>
	{#if loading}
		<div class="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
	{:else if icon}
		{@render icon()}
	{/if}

	{#if children}
		{@render children()}
	{/if}
</button>
