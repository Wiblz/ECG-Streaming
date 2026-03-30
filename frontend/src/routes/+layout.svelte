<script lang="ts">
  import '../app.css';
  import { setContext } from 'svelte';
  import favicon from '$lib/assets/favicon.svg';
  import type { LayoutProps } from './$types';

  let { children, data }: LayoutProps = $props();

  // Provide version to children components
  setContext('version', {
    get value() {
      return data.version;
    }
  });
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
  <title>ECG Streaming {data.version ? `v${data.version}` : ''}</title>
</svelte:head>

{@render children()}
