<script lang="ts">
  import { dbManager } from './lib/db.svelte';
  import { onMount } from 'svelte';
  import Uploader from './lib/Uploader.svelte';
  import ChartsView from './lib/ChartsView.svelte';

  onMount(async () => {
    if (!dbManager.db) await dbManager.init();
  })
</script>

<main>
  {#if dbManager.status === 'loading'}
    <p>Welcome to AutoChart!</p>
    <p>Getting things ready for you...</p>
  {:else if dbManager.status === 'error'}
    <p>Error booting DuckDB. Please try again.</p>
  {:else if dbManager.status === 'ready'}
    <h1>AutoChart</h1>
    <p>Automatically turn your file into charts, without manually choosing columns, all within your browser.</p>
    {#if dbManager.view === 'upload'}
      <Uploader />
    {:else}
      <ChartsView />
    {/if}
  {/if}
</main>