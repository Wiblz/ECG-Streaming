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

	// Variant classes using theme colors
	const variantClasses = {
		primary: 'bg-primary-fg hover:bg-primary-hover text-white',
		secondary: 'bg-surface-muted hover:bg-secondary-hover text-text',
		success: 'bg-status-success-fg hover:bg-status-success-hover text-white',
		danger: 'bg-status-error-fg hover:bg-status-error-hover text-white',
		warning: 'bg-status-warning-fg hover:bg-status-warning-hover text-text',
		ghost: 'bg-transparent hover:bg-surface-muted text-text'
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
