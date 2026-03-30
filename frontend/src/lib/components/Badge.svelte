<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		/**
		 * Badge variant based on semantic meaning
		 */
		variant?: 'success' | 'info' | 'warning' | 'error' | 'neutral';
		/**
		 * Badge size
		 */
		size?: 'sm' | 'md';
		/**
		 * Additional CSS classes
		 */
		class?: string;
		/**
		 * Badge content
		 */
		children: Snippet;
	}

	let {
		variant = 'neutral',
		size = 'md',
		class: className = '',
		children
	}: Props = $props();

	// Variant styles using theme colors
	const variantClasses = {
		success: 'bg-status-success text-status-success-fg border-status-success-border',
		info: 'bg-status-info text-status-info-fg border-status-info-border',
		warning: 'bg-status-warning text-status-warning-fg border-status-warning-border',
		error: 'bg-status-error text-status-error-fg border-status-error-border',
		neutral: 'bg-surface-muted text-text-secondary border-border'
	};

	// Size variants
	const sizeClasses = {
		sm: 'px-2 py-0.5 text-xs',
		md: 'px-2.5 py-1 text-xs'
	};

	const baseClasses = 'inline-flex items-center font-medium rounded-full border';
	const badgeClasses = $derived(
		`${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`
	);
</script>

<span class={badgeClasses}>
	{@render children()}
</span>
