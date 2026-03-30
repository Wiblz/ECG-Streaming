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

  // Variant styles using theme colors
  const variantClasses = {
    primary: 'bg-primary-fg hover:bg-primary-hover text-white',
    secondary: 'bg-secondary-fg hover:bg-secondary-hover text-white',
    success: 'bg-status-success-fg hover:bg-status-success-hover text-white',
    danger: 'bg-status-error-fg hover:bg-status-error-hover text-white',
    warning: 'bg-status-warning-fg hover:bg-status-warning-hover text-text',
    ghost:
      'bg-surface-muted hover:bg-secondary-hover text-text border border-border disabled:bg-surface-muted'
  };

  const buttonClasses = $derived(
    `${baseClasses} ${sizeClasses[size]} ${variantClasses[variant]} ${className}`
  );
</script>

<button {type} {title} disabled={disabled || loading} {onclick} class={buttonClasses}>
  {#if loading}
    <div
      class="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"
    ></div>
  {:else if icon}
    {@render icon()}
  {/if}

  {#if children}
    {@render children()}
  {/if}
</button>
