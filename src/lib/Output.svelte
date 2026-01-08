<script lang="ts">
  import { onMount } from "svelte";
  import { dbManager } from "./db.svelte";

  let error = $state("");
  let container: HTMLDivElement;
  onMount(async () => {
    try {
      const outputtext = await dbManager.showOutput();
      const pre = document.createElement('pre');
      pre.style.whiteSpace = "pre-wrap"; // Optional: wraps long lines
      pre.textContent = outputtext;
      container.appendChild(pre);
    } catch (e: any) {
      error = "Failed to generate output: " + e.message;
    }
  });
</script>

<div>
  {#if error} 
    <p class="error">{error}</p>
  {:else if dbManager.isGenerating}
    <p class="loading">Analyzing data and generating charts...</p>
  {:else}
    <div bind:this={container} class="output-container"></div>
  {/if}
</div>