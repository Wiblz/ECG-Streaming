<script lang="ts">
  import { page } from '$app/state';
  import Header from '$lib/components/layout/Header.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import LinkButton from '$lib/components/ui/LinkButton.svelte';

  const status = $derived(page.status);
  const message = $derived(page.error?.message || 'An error occurred');
</script>

<svelte:head>
  <title>{status} - ECG Streaming</title>
</svelte:head>

<div class="min-h-screen bg-linear-to-br from-surface-muted to-surface">
  <Header />

  <main class="container mx-auto px-6 py-16 max-w-2xl">
    <div class="bg-surface border border-border rounded-xl shadow-sm p-12 text-center">
      <div class="text-8xl font-bold text-text-muted mb-4">{status}</div>

      <h1 class="text-3xl font-bold text-text mb-4">
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

      <p class="text-text-secondary mb-8">
        {message}
      </p>

      <div class="flex gap-4 justify-center">
        <LinkButton href="/" variant="primary" size="lg">Go to Home</LinkButton>
        <Button variant="secondary" size="lg" onclick={() => window.history.back()}>Go Back</Button>
      </div>
    </div>
  </main>
</div>
