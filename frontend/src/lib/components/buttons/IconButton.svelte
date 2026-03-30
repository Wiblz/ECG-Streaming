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

	// Variant styles using theme colors
	const variantClasses = {
		primary: 'bg-primary-fg hover:bg-primary-hover text-white',
		secondary: 'bg-secondary-fg hover:bg-secondary-hover text-white',
		success: 'bg-status-success-fg hover:bg-status-success-hover text-white',
		danger: 'bg-status-error-fg hover:bg-status-error-hover text-white',
		warning: 'bg-status-warning-fg hover:bg-status-warning-hover text-text',
		ghost: 'bg-transparent hover:bg-surface-muted text-text'
	};

	const buttonClasses = $derived(
		`${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`
	);
</script>

<button type="button" {title} {disabled} {onclick} class={buttonClasses}>
	{@render children()}
</button>
