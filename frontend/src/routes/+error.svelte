<script lang="ts">
	import { page } from '$app/state';
	import Header from '$lib/components/Header.svelte';
	import Button from '$lib/components/buttons/Button.svelte';
	import LinkButton from '$lib/components/buttons/LinkButton.svelte';

	const status = $derived(page.status);
	const message = $derived(page.error?.message || 'An error occurred');
</script>

<svelte:head>
	<title>{status} - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-gray-50 to-gray-100">
	<Header />

	<main class="container mx-auto px-6 py-16 max-w-2xl">
		<div class="bg-white border border-gray-200 rounded-xl shadow-sm p-12 text-center">
			<div class="text-8xl font-bold text-gray-300 mb-4">{status}</div>

			<h1 class="text-3xl font-bold text-gray-900 mb-4">
				{#if status === 404}
					Page Not Found
				{:else if status === 403}
					Access Denied
				{:else if status === 500}
					Server Error
				{:else}
					Error
				{/if}
			</h1>

			<p class="text-gray-600 mb-8">
				{message}
			</p>

			<div class="flex gap-4 justify-center">
				<LinkButton href="/" variant="primary" size="lg">
					Go to Home
				</LinkButton>
				<Button variant="secondary" size="lg" onclick={() => window.history.back()}>
					Go Back
				</Button>
			</div>
		</div>
	</main>
</div>
