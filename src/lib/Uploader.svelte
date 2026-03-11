<script lang="ts">
  import { DuckDBDataProtocol } from '@duckdb/duckdb-wasm';
  import { dbManager } from './db.svelte';

  let dragging = $state(false);
  let error = $state("");

  async function handleFile(file: File) {
    if (!file.name.endsWith('.csv')) {
      error = "Only CSV files are supported.";
      return;
    }

    try {
      error = "";
      const db = dbManager.db!;

      await db.registerFileHandle(file.name, file, DuckDBDataProtocol.BROWSER_FILEREADER, true);
      const conn = await db.connect();
      await conn.query(`DROP TABLE IF EXISTS data;`);
      await conn.query(`CREATE TABLE data AS SELECT * FROM read_csv_auto('${file.name}')`);
      await conn.close();
      dbManager.view = 'chart';
    } catch (e: any) {
      error = "Error processing file: " + e.message;
    }
  }

  function onFileChange(event: Event) {
    const target = event.target as HTMLInputElement;
    if (target.files?.length) handleFile(target.files[0]);
  }

  async function loadRemoteSample(fileName: string) {
    try {
      error = ""; 

      const response = await fetch(`./public/samples/${fileName}`);
      if (!response.ok) throw new Error("Could not find the sample file.");

      const blob = await response.blob();
      const file = new File([blob], fileName, { type: 'text/csv' });

      await handleFile(file);
    } catch (e: any) {
      error = "Error loading sample: " + e.message;
    }
  }
</script>

<h3>Upload any CSV file:</h3>

<div
  class="uploader"
  class:dragging
  ondragover={(e) => { e.preventDefault(); dragging = true; }}
  ondragleave={() => (dragging = false)}
  ondrop={(e) => { 
    e.preventDefault(); dragging = false; 
    if (e.dataTransfer?.files?.length) handleFile(e.dataTransfer.files[0]); 
  }}
  role="region"
  aria-label="Upload files by dragging and dropping or selecting"
>
  <input type="file" accept=".csv" onchange={onFileChange} />

  {#if error}
    <p class="error">{error}</p>
  {/if}
</div>

<div class="samples-grid">
  <p>Don't have data? Try a sample:</p>
  <button type="button" onclick={() => loadRemoteSample('flight-stats.csv')}>
    flight_statistics.csv
  </button>
  <button type="button" onclick={() => loadRemoteSample('olympic.csv')}>
    olympic_performance.csv
  </button>
</div>