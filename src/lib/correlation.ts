// src/lib/correlation.ts
import type { AsyncDuckDB } from '@duckdb/duckdb-wasm';

export class CorrelationCalculator {
  constructor(private db: AsyncDuckDB) {}

  /**
   * Calculate correlation using DuckDB's built-in CORR() function
   * Tests multiple relationship types: linear, exponential, logarithmic, power
   */
  async calculateCorrelation(
    xColumn: string, 
    yColumn: string, 
    tableName = 'data'
  ): Promise<number> {
    const conn = await this.db.connect();
    
    try {
      // Calculate all correlations in a single query - MUCH more efficient!
      const result = await conn.query(`
        WITH cleaned_data AS (
          SELECT 
            TRY_CAST("${xColumn}" AS DOUBLE) as x,
            TRY_CAST("${yColumn}" AS DOUBLE) as y
          FROM ${tableName}
          WHERE TRY_CAST("${xColumn}" AS DOUBLE) IS NOT NULL
            AND TRY_CAST("${yColumn}" AS DOUBLE) IS NOT NULL
            AND ISFINITE(TRY_CAST("${xColumn}" AS DOUBLE))
            AND ISFINITE(TRY_CAST("${yColumn}" AS DOUBLE))
        )
        SELECT 
          -- Linear correlation
          ABS(CORR(x, y)) as linear_corr,
          
          -- Exponential correlation (log Y)
          ABS(CORR(x, LN(y))) FILTER (WHERE y > 0) as exp_corr,
          
          -- Logarithmic correlation (log X)
          ABS(CORR(LN(x), y)) FILTER (WHERE x > 0) as log_corr,
          
          -- Power correlation (log both)
          ABS(CORR(LN(x), LN(y))) FILTER (WHERE x > 0 AND y > 0) as power_corr
        FROM cleaned_data
      `);
      
      const row = result.toArray()[0];
      
      // Get the maximum correlation across all types
      const correlations = [
        row.linear_corr,
        row.exp_corr,
        row.log_corr,
        row.power_corr
      ].filter(c => c !== null && !isNaN(c) && isFinite(c));
      
      return correlations.length > 0 ? Math.max(...correlations) : 0;
    } catch (e) {
      console.error(`Correlation calculation failed for ${xColumn} vs ${yColumn}:`, e);
      return 0;
    } finally {
      await conn.close();
    }
  }

  /**
   * Calculate correlations for multiple column pairs at once
   * More efficient than individual calls
   */
  async calculateMultipleCorrelations(
    columnPairs: Array<[string, string]>,
    tableName = 'data'
  ): Promise<Map<string, number>> {
    const results = new Map<string, number>();
    
    // Could be further optimized with UNION ALL queries
    for (const [x, y] of columnPairs) {
      const corr = await this.calculateCorrelation(x, y, tableName);
      results.set(`${x}|${y}`, corr);
    }
    
    return results;
  }
}