import type { AsyncDuckDB } from '@duckdb/duckdb-wasm';
import { IntervalCalculator } from './interval-calculator';
import { type ChartView, ChartType, ColumnType, type ColumnFeatures, type TransformedData, type TransformSpec, TransformType } from './types';

export class FeatureExtractor {
  private intervalCalculator: IntervalCalculator;
  private transformSpecs: TransformSpec[] = [];
  public transformedData: TransformedData = {};
  public features = new Map<string, ColumnFeatures>();
  public columnNamesByType: Record<ColumnType, string[]> = {
    [ColumnType.NUMERICAL]: [],
    [ColumnType.CATEGORICAL]: [],
    [ColumnType.TEMPORAL]: []
  }
  
  constructor(private db: AsyncDuckDB) {
    this.intervalCalculator = new IntervalCalculator(db);
  }

  private mapDuckDBType(duckdbType: string): ColumnType {
    const type = duckdbType.toLowerCase();
    if (type.includes('int') || type.includes('double') || 
        type.includes('float') || type.includes('decimal') ||
        type.includes('numeric') || type.includes('real')) {
      return ColumnType.NUMERICAL;
    }
    if (type.includes('date') || type.includes('timestamp') || 
        type.includes('time') || type === 'interval') {
      return ColumnType.TEMPORAL;
    }
    return ColumnType.CATEGORICAL;
  }

  private convertBigIntToNumber(row: any): any {
    const converted: any = {};
    for (const [key, value] of Object.entries(row)) {
      converted[key] = typeof value === 'bigint' ? Number(value) : value;
    }
    return converted;
  }

  public async extractFeatures(tableName='data'): Promise<void> {
    const conn = await this.db.connect();
    try {
      const summaryResult = await conn.query(`SUMMARIZE ${tableName}`);
      const summaryRows = summaryResult.toArray().map(row => this.convertBigIntToNumber(row));
      for (const row of summaryRows) {
        const type = this.mapDuckDBType(row.column_type);
        this.features.set(row.column_name, {
          type: type,
          min: row.min,
          max: row.max,
          distinct: row.approx_unique? row.approx_unique : 0,
          ratio: row.count > 0 ? row.approx_unique / row.count : 0
        });
        this.columnNamesByType[type].push(row.column_name);
      }

      // categorical: get distinct values
      if (this.columnNamesByType[ColumnType.CATEGORICAL].length > 0) {
        const result = await conn.query(`
          SELECT column_name, value::VARCHAR AS value, COUNT(*) as count
          FROM ${tableName}
          UNPIVOT (value FOR column_name IN (${this.columnNamesByType[ColumnType.CATEGORICAL].map(c=>`"${c}"::VARCHAR`).join(', ')}))
          GROUP BY column_name, value
        `);
        const rows = result.toArray().map(row => this.convertBigIntToNumber(row));
        for (const row of rows) {
          const feature = this.features.get(row.column_name)!;
          if (!feature.distinctValues) feature.distinctValues = [];
          feature.distinctValues.push([row.value, row.count]);
        }
      }

      // temporal: get distinct values + interval bins
      if (this.columnNamesByType[ColumnType.TEMPORAL].length > 0) {
        const result = await conn.query(`
          SELECT column_name, value, COUNT(*) as count
          FROM ${tableName}
          UNPIVOT (value FOR column_name IN (${this.columnNamesByType[ColumnType.TEMPORAL].map(c=>`"${c}"`).join(', ')}))
          GROUP BY column_name, value
        `);
        const rows = result.toArray().map(row => this.convertBigIntToNumber(row));
        for (const row of rows) {
          const feature = this.features.get(row.column_name)!;
          if (!feature.distinctValues) feature.distinctValues = [];
          feature.distinctValues.push([row.value, row.count]);
        }
        for (const colName of this.columnNamesByType[ColumnType.TEMPORAL]) {
          const feature = this.features.get(colName)!;
          if (feature.min && feature.max && feature.min !== feature.max) {
            this.intervalCalculator.calculateIntervalBins(feature, colName, tableName);
          }
        }
      }
    } finally {
      await conn.close();
    }
  }

  public generateTransformSpecs(tableName='data'): void {
    const numericalCols = this.columnNamesByType[ColumnType.NUMERICAL];
    this.generateBasicTransformSpecs(tableName, numericalCols);
    this.generateCrossColumnTransformSpecs(tableName, numericalCols);
  }

  private generateBasicTransformSpecs(tableName: string, numericalCols: string[]): void {
     for (const [colName, feature] of this.features) {
      if (this.shouldApplyGrouping(feature)) {
        this.transformSpecs.push({
          key: `group_${colName}`,
          sourceTable: tableName,
          transformType: TransformType.GROUP_DISTINCT,
          columns: { groupBy: [colName], aggregate: numericalCols },
          metadata: { xColumnType: feature.type }
        });
      }

      if (feature.type === ColumnType.TEMPORAL) {
        this.transformSpecs.push({
          key: `interval_${colName}`,
          sourceTable: tableName,
          transformType: TransformType.INTERVAL_BIN,
          columns: { groupBy: [colName], aggregate: numericalCols },
          metadata: { interval: feature.interval, xColumnType: feature.type }
        });
      }

      if (this.shouldApplyPNBinning(feature)) {
        this.transformSpecs.push({
          key: `pn_${colName}`,
          sourceTable: tableName,
          transformType: TransformType.PN_BIN,
          columns: { groupBy: [colName], aggregate: numericalCols },
          metadata: { xColumnType: feature.type }
        });
      }
    }
  }

  private generateCrossColumnTransformSpecs(tableName: string, numericalCols: string[]): void {
    for (const [col1, feature1] of this.features) {
      if (feature1.type !== ColumnType.CATEGORICAL || feature1.distinct > 5) continue;

      for (const [col2, feature2] of this.features) {
        if (col1 === col2) continue;

        if (feature2.type === ColumnType.CATEGORICAL) {
          this.transformSpecs.push({
            key: `cross_${col1}_${col2}`,
            sourceTable: tableName,
            transformType: TransformType.CROSS_GROUP,
            columns: { groupBy: [col1, col2], aggregate: numericalCols },
            metadata: { xColumnType: ColumnType.CATEGORICAL }
          });
        }

        if (feature2.type === ColumnType.TEMPORAL) {
          this.transformSpecs.push({
            key: `cross_${col1}_interval_${col2}`,
            sourceTable: tableName,
            transformType: TransformType.CROSS_GROUP,
            columns: { groupBy: [col1, col2], aggregate: numericalCols },
            metadata: { binCol: col2, interval: feature2.interval, xColumnType: ColumnType.CATEGORICAL }
          });
        }
      }
    }
  }

  /**
   * 3. Materialize ALL transformations in one batch query using UNION ALL
   * This is much faster than individual queries
   */
  public async materializeTransforms(): Promise<void> {
    if (this.transformSpecs.length === 0) return;

    const conn = await this.db.connect();
    try {
      // Build queries and group by column signature to ensure UNION compatibility
      const queryGroups = new Map<string, { spec: TransformSpec; sql: string }[]>();
      
      for (const spec of this.transformSpecs) {
        const sql = this.buildTransformSQL(spec);
        // Create a signature based on column structure
        const signature = this.getQuerySignature(spec);
        if (!queryGroups.has(signature)) {
          queryGroups.set(signature, []);
        }
        queryGroups.get(signature)!.push({ spec, sql });
      }
      
      // Execute each group separately
      for (const [signature, queries] of queryGroups) {
        const BATCH_SIZE = 20;
        for (let i = 0; i < queries.length; i += BATCH_SIZE) {
          const batch = queries.slice(i, i + BATCH_SIZE);
          
          //const unionQuery = batch.map(q => q.sql).join('\nUNION ALL\n');
          // Wrap each query in a subquery to handle ORDER BY clauses
          const unionQuery = batch
            .map(q => `(${q.sql.trim()})`)
            .join('\nUNION ALL\n');

          const result = await conn.query(unionQuery);
          const rows = result.toArray().map(row => this.convertBigIntToNumber(row));
          
          // Group results by transform_key
          for (const row of rows) {
            const key = row._transform_key;
            if (!this.transformedData[key]) {
              this.transformedData[key] = [];
            }
            // Remove the internal key before storing
            const { _transform_key, ...data } = this.convertBigIntToNumber(row);
            this.transformedData[key].push(data);
          }
        }
      }
    } finally {
      await conn.close();
    }
  }

  /**
 * Create a signature for a query based on its column structure
 * Queries with the same signature can be combined with UNION ALL
 */
  private getQuerySignature(spec: TransformSpec): string {
    const { transformType, columns, metadata } = spec;
    const numGroups = columns.groupBy?.length || 0;
    const numAggs = columns.aggregate?.length || 0;
    
    // Signature includes: transform type, number of group columns, and number of aggregates
    return `${transformType}_g${numGroups}_a${numAggs}`;
  }

  private buildTransformSQL(spec: TransformSpec): string {
    const { key, sourceTable, transformType, columns, metadata } = spec;
    const { groupBy: group = [], aggregate = [] } = columns;

    const numericalAggs = aggregate.flatMap(col => [
      `SUM("${col}") as "SUM(${col})"`,
      `AVG("${col}") as "AVG(${col})"`
    ]);

    switch (transformType) {
      case TransformType.GROUP_DISTINCT: {
        const groupCol = group[0];
        return `
          SELECT 
            '${key}' as _transform_key,
            "${groupCol}",
            COUNT(*) as "COUNT(${groupCol})"
            ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
          FROM ${sourceTable}
          GROUP BY "${groupCol}"
        `;
      }

      case TransformType.INTERVAL_BIN: {
        const groupCol = group[0];
        const interval = metadata?.interval || 'day';
        const binExpr = this.getTimeBinExpression(groupCol, interval);
        return `
          SELECT 
            '${key}' as _transform_key,
            ${binExpr} as "${groupCol}/(${interval})",
            COUNT(*) as "COUNT(${groupCol})"
            ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
          FROM ${sourceTable}
          GROUP BY ${binExpr}
          ORDER BY ${binExpr}
        `;
      }

      case TransformType.PN_BIN: {
        const groupCol = group[0];
        return `
          SELECT 
            '${key}' as _transform_key,
            CASE WHEN "${groupCol}" > 0 THEN '>0' ELSE '<=0' END as "${groupCol}",
            COUNT(*) as "COUNT(${groupCol})"
          FROM ${sourceTable}
          GROUP BY CASE WHEN "${groupCol}" > 0 THEN '>0' ELSE '<=0' END
        `;
      }

      case TransformType.CROSS_GROUP: {
        if (metadata?.interval && metadata?.binCol) {
          // Cross-column with binning
          const [col1, col2] = group;
          const binCol = metadata.binCol;
          let binExpr = `"${binCol}"`;
          let orderByExpr = `"${binCol}"`;
          //let orderBy = '';

          binExpr = this.getTimeBinExpression(binCol, metadata.interval || 'day');
          orderByExpr = binExpr;

          const orderBy = orderByExpr ? `ORDER BY "${col1}", ${orderByExpr}` : '';

          return `
            SELECT 
              '${key}' as _transform_key,
              "${col1}",
              ${binExpr} as "${binCol}",
              COUNT(*) as "COUNT"
              ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
            FROM ${sourceTable}
            GROUP BY "${col1}", ${binExpr}
            ${orderBy}
          `;
        } else {
          // Simple cross-group
          const groupCols = group.map(c => `"${c}"`).join(', ');
          return `
            SELECT 
              '${key}' as _transform_key,
              ${groupCols},
              COUNT(*) as "COUNT"
              ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
            FROM ${sourceTable}
            GROUP BY ${groupCols}
          `;
        }
      }

      default:
        throw new Error(`Unknown transform type: ${transformType}`);
    }
  }

  /**
   * Get transformed data for a specific transformation
   */
  public getTransformedData(key: string): any[] {
    return this.transformedData[key] || [];
  }

  // Helper methods
  private getTimeBinExpression(colName: string, interval: string): string {
    const intervalMap: Record<string, string> = {
      'second': `date_trunc('second', "${colName}")`,
      'minute': `date_trunc('minute', "${colName}")`,
      'hour': `date_trunc('hour', "${colName}")`,
      'day': `date_trunc('day', "${colName}")`,
      'week': `date_trunc('week', "${colName}")`,
      'month': `date_trunc('month', "${colName}")`,
      'quarter': `date_trunc('quarter', "${colName}")`,
      'year': `date_trunc('year', "${colName}")`
    };
    return intervalMap[interval] || intervalMap['day'];
  }

  private shouldApplyGrouping(feature: ColumnFeatures): boolean {
    return (feature.type === ColumnType.TEMPORAL || 
            feature.type === ColumnType.CATEGORICAL) && 
            feature.ratio < 1.0;
  }

  private shouldApplyPNBinning(feature: ColumnFeatures): boolean {
    return feature.type === ColumnType.NUMERICAL && 
           feature.min != null && feature.min < 0 &&
           feature.max != null && feature.max > 0;
  }

  /**
   * 4. Generate chart views from materialized transformations and original data
   * This should be called after materializeTransforms()
   */
  public async generateChartViews(tableName = 'data'): Promise<ChartView[]> {
    const views: ChartView[] = [];
    
    // Generate views from original data (untransformed)
    const originalViews = await this.generateOriginalDataViews(tableName);
    views.push(...originalViews);
    
    // Generate views from transformed data
    const transformedViews = await this.generateTransformedDataViews();
    views.push(...transformedViews);
    
    return views;
  }

  /**
   * Generate chart views from the original untransformed data
   */
  private async generateOriginalDataViews(tableName: string): Promise<ChartView[]> {
    const views: ChartView[] = [];
    const columns = Array.from(this.features.keys());
    
    for (let i = 0; i < columns.length; i++) {
      for (let j = 0; j < columns.length; j++) {
        if (i === j) continue;
        
        const xCol = columns[i];
        const yCol = columns[j];
        const xFeature = this.features.get(xCol)!;
        const yFeature = this.features.get(yCol)!;
        
        const chartTypes = this.determine2DChartTypes(xFeature, yFeature, i, j);
        
        for (const chartType of chartTypes) {
          const view = await this.createViewFromOriginalData(
            xCol, yCol, xFeature, yFeature, chartType, tableName
          );
          if (view) views.push(view);
        }
      }
    }
    
    return views;
  }

  /**
   * Generate chart views from all materialized transformations
   */
  private generateTransformedDataViews(): Promise<ChartView[]> {
    const views: ChartView[] = [];
    
    for (const spec of this.transformSpecs) {
      const data = this.transformedData[spec.key];
      if (!data || data.length === 0) continue;
      
      const transformViews = this.createViewsFromTransformedData(spec, data);
      views.push(...transformViews);
    }
    
    return Promise.resolve(views);
  }

  /**
   * Create chart view from original table data
   */
  private async createViewFromOriginalData(
    xCol: string,
    yCol: string,
    xFeature: ColumnFeatures,
    yFeature: ColumnFeatures,
    chartType: ChartType,
    tableName: string
  ): Promise<ChartView | null> {
    const conn = await this.db.connect();
    
    try {
      let query: string;
      
      if (chartType === ChartType.BAR || chartType === ChartType.PIE) {
        // Aggregate data for bar/pie charts
        query = `
          SELECT 
            "${xCol}" as x, 
            SUM("${yCol}") as y
          FROM ${tableName}
          WHERE "${xCol}" IS NOT NULL AND "${yCol}" IS NOT NULL
          GROUP BY "${xCol}"
          ORDER BY "${xCol}"
        `;
      } else {
        // Raw data for scatter/line charts
        query = `
          SELECT "${xCol}" as x, "${yCol}" as y
          FROM ${tableName}
          WHERE "${xCol}" IS NOT NULL AND "${yCol}" IS NOT NULL
          ORDER BY "${xCol}"
        `;
      }
      
      const result = await conn.query(query);
      const rows = result.toArray().map(row => this.convertBigIntToNumber(row));
      
      if (rows.length === 0) return null;
      
      const X = [rows.map(r => r.x)];
      const Y = [rows.map(r => r.y)];
      
      return {
        xFeature,
        yFeature,
        xName: xCol,
        yName: yCol,
        zId: -1,
        seriesNum: 1,
        X,
        Y,
        chartType,
        tupleNum: rows.length,
        score: this.calculateScore(xFeature, yFeature, chartType, rows.length),
        description: `${xCol} vs ${yCol}`
      };
    } finally {
      await conn.close();
    }
  }

  /**
   * Create chart views from a single transformed dataset
   */
  private createViewsFromTransformedData(spec: TransformSpec, data: any[]): ChartView[] {
    const views: ChartView[] = [];
    
    // Determine which columns are dimensions (group) and which are measures (aggregates)
    const groupCols = spec.columns.groupBy || [];
    const isCrossGroup = groupCols.length == 2;
    const aggCols = Object.keys(data[0]).filter(col => 
      col.startsWith('SUM(') || col.startsWith('AVG(') || col.startsWith('COUNT')
    );

    if (isCrossGroup) {
    // Handle cross-group: create multi-series charts
    views.push(...this.createCrossGroupViews(spec, data, groupCols, aggCols));
    } else {
    
    // For each dimension, pair it with each measure
      for (const groupCol of groupCols) {
        // Get the actual column name in the transformed data (might be binned)
        const actualGroupCol = this.getTransformedColumnName(spec, groupCol);
        
        for (const aggCol of aggCols) {
          const chartTypes = this.determineTransformedChartTypes(spec, actualGroupCol, aggCol, data);
          
          for (const chartType of chartTypes) {
            const view = this.createViewFromTransformedRow(
              spec, actualGroupCol, aggCol, chartType, data
            );
            if (view) views.push(view);
          }
        }
      }
    }
    
    return views;
  }

  /**
 * Create multi-series chart views from cross-group data
 */
private createCrossGroupViews(
  spec: TransformSpec,
  data: any[],
  groupCols: string[],
  aggCols: string[]
): ChartView[] {
  const views: ChartView[] = [];
  const [col1, col2] = groupCols;
  
  // Get actual column names (might be binned)
  const actualCol1 = col1;
  const actualCol2 = this.getTransformedColumnName(spec, col2);
  
  // For each aggregate, create a grouped chart
  for (const aggCol of aggCols) {
    // Pivot data: group by col1, create series for each col2 value
    const col2Values = [...new Set(data.map(row => row[actualCol2]))];
    const col1Values = [...new Set(data.map(row => row[actualCol1]))];
    
    // Skip if too many series (would be unreadable)
    if (col2Values.length > 10) continue;
    
    // Build X and Y arrays for multi-series
    const X: any[][] = [];
    const Y: any[][] = [];
    
    for (const col2Val of col2Values) {
      const seriesData = data.filter(row => row[actualCol2] === col2Val);
      const xVals = seriesData.map(row => row[actualCol1]);
      const yVals = seriesData.map(row => row[aggCol]);
      
      X.push(xVals);
      Y.push(yVals);
    }
    
    // Determine chart type
    const isTemporal = spec.transformType === TransformType.INTERVAL_BIN ||
                       spec.metadata?.interval != null;
    const distinctCount = col1Values.length;
    
    let chartType: ChartType;
    if (isTemporal) {
      chartType = distinctCount < 7 ? ChartType.BAR : ChartType.LINE;
    } else {
      chartType = ChartType.BAR; // Cross-groups typically use bar charts
    }
    
    // Create synthetic features
    const xFeature: ColumnFeatures = {
      type: spec.metadata?.xColumnType || ColumnType.CATEGORICAL,
      min: col1Values[0],
      max: col1Values[col1Values.length - 1],
      distinct: col1Values.length,
      ratio: col1Values.length / data.length
    };
    
    const allYValues = Y.flat();
    const yFeature: ColumnFeatures = {
      type: ColumnType.NUMERICAL,
      min: Math.min(...allYValues),
      max: Math.max(...allYValues),
      distinct: new Set(allYValues).size,
      ratio: new Set(allYValues).size / allYValues.length
    };
    
    views.push({
      xFeature,
      yFeature,
      xName: actualCol1,
      yName: aggCol,
      zId: -1,
      seriesNum: col2Values.length,
      seriesNames: col2Values.map(v => String(v)),
      X,
      Y,
      chartType,
      tupleNum: data.length,
      score: this.calculateScore(xFeature, yFeature, chartType, data.length),
      description: `${spec.key} - ${actualCol1} vs ${aggCol} (by ${actualCol2})`
    });
  }
  
  return views;
}

  /**
   * Get the actual column name in transformed data (handles binned columns)
   */
  private getTransformedColumnName(spec: TransformSpec, originalCol: string): string {
    // Check the transform type and return the appropriate column name
    switch (spec.transformType) {
      case TransformType.INTERVAL_BIN:
        return `${originalCol}/(${spec.metadata?.interval || 'day'})`;
      case TransformType.GROUP_DISTINCT:
      case TransformType.PN_BIN:
      default:
        return originalCol;
    }
  }

  /**
   * Determine chart types for transformed data
   */
  private determineTransformedChartTypes(
    spec: TransformSpec,
    groupCol: string,
    aggCol: string,
    data: any[]
  ): ChartType[] {
    const charts: ChartType[] = [];
    const distinctCount = new Set(data.map(row => row[groupCol])).size;
    
    // Check if it's temporal data
    const isTemporal = spec.transformType === TransformType.INTERVAL_BIN; 
    
    // Check if aggregate has positive values (for pie chart)
    const hasPositiveValues = data.every(row => row[aggCol] > 0);
    
    if (isTemporal) {
      // Temporal data: use bar for few points, line for many
      charts.push(distinctCount < 7 ? ChartType.BAR : ChartType.LINE);
    } else {
      // Categorical data
      if (hasPositiveValues && distinctCount <= 5 && !this.isAvgColumn(aggCol)) {
        charts.push(ChartType.PIE);
      }
      if (distinctCount <= 20) {
        charts.push(ChartType.BAR);
      }
    }
    
    return charts;
  }

  /**
   * Create a chart view from transformed data
   */
  private createViewFromTransformedRow(
    spec: TransformSpec,
    groupCol: string,
    aggCol: string,
    chartType: ChartType,
    data: any[]
  ): ChartView | null {
    if (data.length === 0) return null;
    
    const X = [data.map(row => row[groupCol])];
    const Y = [data.map(row => row[aggCol])];
    
    // Create synthetic features for the transformed columns
    const xFeature: ColumnFeatures = {
      type: spec.metadata?.xColumnType || ColumnType.CATEGORICAL,
      min: X[0][0],
      max: X[0][X[0].length - 1],
      distinct: new Set(X[0]).size,
      ratio: new Set(X[0]).size / X[0].length
    };
    
    const yFeature: ColumnFeatures = {
      type: ColumnType.NUMERICAL,
      min: Math.min(...Y[0]),
      max: Math.max(...Y[0]),
      distinct: new Set(Y[0]).size,
      ratio: new Set(Y[0]).size / Y[0].length
    };
    
    return {
      xFeature,
      yFeature,
      xName: groupCol,
      yName: aggCol,
      zId: -1,
      seriesNum: 1,
      X,
      Y,
      chartType,
      tupleNum: data.length,
      score: this.calculateScore(xFeature, yFeature, chartType, data.length),
      description: `${spec.key} - ${groupCol} vs ${aggCol}`
    };
  }

  /**
   * Determine chart types for 2D views (original data)
   */
  private determine2DChartTypes(
    fi: ColumnFeatures, 
    fj: ColumnFeatures, 
    i: number, 
    j: number
  ): ChartType[] {
    if (fi.type === ColumnType.CATEGORICAL && 
        fj.type === ColumnType.NUMERICAL && 
        fi.ratio === 1.0) {
      return this.getCategoricalNumericalCharts(fi, fj);
    }
  
    if (fi.type === ColumnType.TEMPORAL && 
        fj.type === ColumnType.NUMERICAL && 
        fi.ratio === 1.0) {
      return this.getTemporalNumericalCharts(fi.distinct);
    }
    
    if (fi.type === ColumnType.NUMERICAL && 
        fj.type === ColumnType.NUMERICAL && 
        i < j) {
      return [ChartType.SCATTER];
    }
  
    return [];
  }

  /**
   * Get chart types for categorical vs numerical data
   */
  private getCategoricalNumericalCharts(fi: ColumnFeatures, fj: ColumnFeatures): ChartType[] {
    const charts: ChartType[] = [];
    
    // Pie chart: positive values, small number of categories
    if (fj.min !== undefined && fj.min > 0 && fi.distinct <= 5 && !this.isAvgColumn(fj)) {
      charts.push(ChartType.PIE);
    }
    
    // Bar chart: reasonable number of categories
    if (fi.distinct <= 20) {
      charts.push(ChartType.BAR);
    }
    
    return charts;
  }

  /**
   * Get chart types for temporal vs numerical data
   */
  private getTemporalNumericalCharts(distinctCount: number): ChartType[] {
    return distinctCount < 7 ? [ChartType.BAR] : [ChartType.LINE];
  }

  /**
   * Check if a column name indicates it's an average column
   */
  private isAvgColumn(feature: ColumnFeatures | string): boolean {
    const name = typeof feature === 'string' ? feature : (feature as any).name;
    if (!name) return false;
    return name.toLowerCase().includes('avg') || name.startsWith('AVG(');
  }

  /**
   * Calculate score for a chart view
   */
  private calculateScore(
    xFeature: ColumnFeatures,
    yFeature: ColumnFeatures,
    chartType: ChartType,
    tupleNum: number
  ): number {
    let score = 0;
    
    // Factor 1: Data completeness
    score += Math.min(tupleNum / 1000, 1) * 2;
    
    // Factor 2: Distinct value ratio for categorical
    if (xFeature.type === ColumnType.CATEGORICAL) {
      score += (1 - Math.min(xFeature.ratio, 1)) * 1.5;
    }
    
    // Factor 3: Chart type preference
    const chartTypeScores = {
      [ChartType.SCATTER]: 0.5,
      [ChartType.LINE]: 0.8,
      [ChartType.BAR]: 0.7,
      [ChartType.PIE]: 0.3
    };
    score += chartTypeScores[chartType] || 0;
    
    // Factor 4: Penalize too many or too few data points
    if (tupleNum < 3) score *= 0.5;
    if (tupleNum > 10000) score *= 0.8;
    
    return score;
  }
  
}