<script lang="ts">
	/**
	 * Unified Card component for consistent styling across the application
	 */

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

<div class="bg-white border border-gray-200 rounded-xl shadow-lg {className}">
	{#if hasHeader}
		<div class="px-6 py-4 {divider ? 'border-b border-gray-200' : ''}">
			<div class="flex items-center justify-between">
				{#if title}
					<h2 class="text-lg font-semibold text-gray-900">{title}</h2>
				{/if}
				<div class="flex items-center gap-3">
					{#if badge !== undefined}
						<span class="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
							{badge}
						</span>
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
