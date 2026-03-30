<script lang="ts">
  /**
   * Unified Card component for consistent styling across the application
   */

  import Badge from './Badge.svelte';

  interface Props {
    /**
     * Optional title for the card header
     */
    title?: string;
    /**
     * Optional badge/count to display next to title
     */
    badge?: string | number;
    /**
     * Card content (main slot)
     */
    children?: import('svelte').Snippet;
    /**
     * Optional header actions (slot for buttons, etc.)
     */
    headerActions?: import('svelte').Snippet;
    /**
     * Whether to show a divider between header and content
     * @default false
     */
    divider?: boolean;
    /**
     * Padding size for the card body
     * @default 'normal' (p-6)
     */
    padding?: 'none' | 'small' | 'normal' | 'large';
    /**
     * Custom classes to add to the card wrapper
     */
    class?: string;
  }

  let {
    title,
    badge,
    children,
    headerActions,
    divider = false,
    padding = 'normal',
    class: className = ''
  }: Props = $props();

  const paddingClasses = {
    none: '',
    small: 'p-4',
    normal: 'p-6',
    large: 'p-8'
  };

  const hasHeader = $derived(title || badge || headerActions);
</script>

<div class="bg-surface border border-border rounded-xl shadow-lg {className}">
  {#if hasHeader}
    <div class="px-6 py-4 {divider ? 'border-b border-border' : ''}">
      <div class="flex items-center justify-between">
        {#if title}
          <h2 class="text-lg font-semibold text-text">{title}</h2>
        {/if}
        <div class="flex items-center gap-3">
          {#if badge !== undefined}
            <Badge variant="neutral" size="md">
              {badge}
            </Badge>
          {/if}
          {#if headerActions}
            {@render headerActions()}
          {/if}
        </div>
      </div>
    </div>
  {/if}

  {#if children}
    <div class={paddingClasses[padding]}>
      {@render children()}
    </div>
  {/if}
</div>
