// src/lib/db.svelte.ts (updated)
import * as duckdb from '@duckdb/duckdb-wasm';
import duckdb_wasm from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url';
import mvp_worker from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url';
import duckdb_wasm_eh from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import eh_worker from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';
import type { ChartView } from './types';
import { FeatureExtractor } from './feature-extractor';


class DuckDBManager {
  db = $state<duckdb.AsyncDuckDB | null>(null);
  status = $state<'loading' | 'ready' | 'error'>('loading');
  view = $state<'upload' | 'chart'>('upload');
  recommendedCharts = $state<ChartView[]>([]);
  isGenerating = $state<boolean>(false);

  async init() {
    try {
      const MANUAL_BUNDLES: duckdb.DuckDBBundles = {
        mvp: { mainModule: duckdb_wasm, mainWorker: mvp_worker },
        eh: { mainModule: duckdb_wasm_eh, mainWorker: eh_worker }
      };
      const bundle = await duckdb.selectBundle(MANUAL_BUNDLES);
      const worker = new Worker(bundle.mainWorker!);
      const logger = new duckdb.ConsoleLogger();
      const database = new duckdb.AsyncDuckDB(logger, worker);
      await database.instantiate(bundle.mainModule, bundle.pthreadWorker);
      this.db = database;
      this.status = 'ready';
    } catch (e) {
      console.error('Failed to initialize DuckDB:', e);
      this.status = 'error';
    }
  }

  async generateRecommendations() {
    try {
      this.isGenerating = true;
      const extractor = new FeatureExtractor(this.db!);
      await extractor.extractFeatures('data');
      extractor.generateTransformSpecs('data');
      await extractor.populateTransformedData();
      this.recommendedCharts = await extractor.generateChartViews('data');
    } catch(e) {
      console.error('Failed to generate recommendations:', e);
      throw e;
    } finally {
      this.isGenerating = false;
    }
  }

  reset() {
    this.view = 'upload';
    this.recommendedCharts = [];
    this.isGenerating = false;
  }
  
}

export const dbManager = new DuckDBManager();