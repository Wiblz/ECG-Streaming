<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		/**
		 * Link destination
		 */
		href: string;
		/**
		 * Button variant
		 */
		variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'warning' | 'ghost';
		/**
		 * Button size
		 */
		size?: 'sm' | 'md' | 'lg';
		/**
		 * Additional CSS classes
		 */
		class?: string;
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
		/**
		 * Open in new tab
		 */
		target?: '_blank' | '_self' | '_parent' | '_top';
	}

	let {
		href,
		variant = 'primary',
		size = 'md',
		class: className = '',
		title,
		icon,
		children,
		target
	}: Props = $props();

	// Variant classes
	const variantClasses = {
		primary: 'bg-blue-600 hover:bg-blue-700 text-white',
		secondary: 'bg-gray-200 hover:bg-gray-300 text-gray-700',
		success: 'bg-status-success-fg hover:bg-status-success-border text-white',
		danger: 'bg-status-error-fg hover:bg-status-error-border text-white',
		warning: 'bg-status-warning-fg hover:bg-status-warning-border text-gray-900',
		ghost: 'bg-transparent hover:bg-gray-100 text-gray-700'
	};

	// Size classes
	const sizeClasses = {
		sm: 'px-3 py-1.5 text-xs',
		md: 'px-4 py-2 text-sm',
		lg: 'px-6 py-3 text-base'
	};

	const baseClasses =
		'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors';
	const classes = $derived(
		`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${className}`
	);
</script>

<a {href} class={classes} {title} {target}>
	{#if icon}
		{@render icon()}
	{/if}
	{#if children}
		{@render children()}
	{/if}
</a>
