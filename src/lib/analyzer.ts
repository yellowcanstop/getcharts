import { type AsyncDuckDB } from '@duckdb/duckdb-wasm';
import { type ChartView, ChartType, ColumnType, type ColumnFeatures, type TransformedData, type TransformSpec, TransformType, TimeInterval } from './types';

export class Analyzer {
  private features = new Map<string, ColumnFeatures>();
  private columnNamesByType: Record<ColumnType, string[]> = {
    [ColumnType.NUMERICAL]: [],
    [ColumnType.CATEGORICAL]: [],
    [ColumnType.TEMPORAL]: []
  }
  private transformSpecs: TransformSpec[] = [];
  private transformedData: TransformedData = {};
  private views: ChartView[] = [];
  
  constructor(private db: AsyncDuckDB) {}

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
            const minDate = new Date(feature.min);
            const maxDate = new Date(feature.max);
            feature.interval = this.getInterval(minDate, maxDate);
          }
        }
      }
    } finally {
      await conn.close();
    }
  }

  private getInterval(min: Date, max: Date): TimeInterval {
    if (min.getFullYear() === max.getFullYear() &&
        min.getMonth() === max.getMonth() &&
        min.getDate() === max.getDate()) {
      if (min.getHours() === max.getHours()) {
        if (min.getMinutes() === max.getMinutes()) {
          return TimeInterval.SECOND;
        }
        return TimeInterval.MINUTE;
      }
      return TimeInterval.HOUR;
    }
    if (min.getFullYear() === max.getFullYear()) {
      if (min.getMonth() === max.getMonth()) {
        return TimeInterval.DAY;
      }
      return TimeInterval.MONTH;
    }
    return TimeInterval.YEAR;
  }

  public generateTransformSpecs(tableName='data'): void {
    const numericalCols = this.columnNamesByType[ColumnType.NUMERICAL];
    this.generateBasicTransformSpecs(tableName, numericalCols);
    this.generateCrossColumnTransformSpecs(tableName, numericalCols);
  }

  private generateBasicTransformSpecs(tableName: string, numericalCols: string[]): void {
     for (const [colName, feature] of this.features) {
      if (feature.type === ColumnType.CATEGORICAL && feature.ratio < 1.0) {
        const key = JSON.stringify([colName, colName])
        this.transformSpecs.push({
          key: `${key}`,
          sourceTable: tableName,
          transformType: TransformType.GROUP_DISTINCT,
          columns: { groupBy: [colName], aggregate: numericalCols },
          metadata: { xColumnType: feature.type }
        });
      }

      if (feature.type === ColumnType.TEMPORAL) {
        const interval = feature.interval;
        const intervalCol = `${colName}/(${interval})`;
        const key = JSON.stringify([intervalCol, colName])
        this.transformSpecs.push({
          key: `${key}`,
          sourceTable: tableName,
          transformType: TransformType.INTERVAL_BIN,
          columns: { groupBy: [colName], aggregate: numericalCols },
          metadata: { interval: interval, xColumnType: feature.type }
        });
      }

      if (feature.type === ColumnType.NUMERICAL && feature.min != null && feature.min < 0 && feature.max != null && feature.max > 0) {
        const key = JSON.stringify([colName, colName])
        this.transformSpecs.push({
          key: `${key}`,
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
          const key = JSON.stringify([col1, col2])
          this.transformSpecs.push({
            key: `${key}`,
            sourceTable: tableName,
            transformType: TransformType.CROSS_GROUP,
            columns: { groupBy: [col1, col2], aggregate: numericalCols },
            metadata: { xColumnType: ColumnType.CATEGORICAL }
          });
        }

        if (feature2.type === ColumnType.TEMPORAL) {
          const interval = feature2.interval || 'year';
          const key = JSON.stringify([col1, col2])
          this.transformSpecs.push({
            key: `${key}`,
            sourceTable: tableName,
            transformType: TransformType.CROSS_GROUP,
            columns: { groupBy: [col1, col2], aggregate: numericalCols },
            metadata: { binCol: col2, interval: interval, xColumnType: ColumnType.CATEGORICAL }
          });
        }
      }
    }
  }

  public async populateTransformedData(): Promise<void> {
    if (this.transformSpecs.length === 0) return;

    const conn = await this.db.connect();
    try {
      // group queries by column count to ensure UNION compatibility
      const queryGroups = new Map<string, { spec: TransformSpec; sql: string }[]>();
      for (const spec of this.transformSpecs) {
        const sql = this.buildTransformSQL(spec);
        const signature = this.getQuerySignature(spec);
        if (!queryGroups.has(signature)) {
          queryGroups.set(signature, []);
        }
        queryGroups.get(signature)!.push({ spec, sql });
      }
      
      for (const [signature, queries] of queryGroups) {
        const BATCH_SIZE = 20;
        for (let i = 0; i < queries.length; i += BATCH_SIZE) {
          const batch = queries.slice(i, i + BATCH_SIZE);
          const unionQuery = batch.map(q => `(${q.sql.trim()})`).join('\nUNION ALL\n');
          const result = await conn.query(unionQuery);
          const rows = result.toArray().map(row => this.convertBigIntToNumber(row));

          // group results by transform_key
          for (const row of rows) {
            const key = row._transform_key;
            if (!this.transformedData[key]) {
              this.transformedData[key] = [];
            }
            // remove the internal key before storing
            const { _transform_key, ...data } = row;
            
            /*
            SQL UNION uses column names from the first query by default.
            However, queries in a batch (query group) have different column names.
            Hence, my workaround is to use a generic alias (_group_col_0, _group_col_1) in the SQL queries,
            and rename back to the original column names (stringified to be _transform_key).
            */
            const renamedData = this.renameToOriginalColNames(key, data)
            
            this.transformedData[key].push(renamedData);
          }
        }
      }
    } finally {
      await conn.close();
    }
  }

  private getQuerySignature(spec: TransformSpec): string {
    const { transformType, columns } = spec;
    const colCountForGroupBy = columns.groupBy?.length || 0;
    const colCountForAggregate = columns.aggregate?.length || 0;
    return `${transformType}_g${colCountForGroupBy}_a${colCountForAggregate}`;
  }

  private buildTransformSQL(spec: TransformSpec): string {
    const { key, sourceTable, transformType, columns, metadata } = spec;
    const { groupBy = [], aggregate = [] } = columns;

    const numericalAggs = aggregate.flatMap(col => [
      `SUM("${col}")::DOUBLE as "SUM(${col})"`,
      `AVG("${col}")::DOUBLE as "AVG(${col})"`
    ]);

    switch (transformType) {
      case TransformType.GROUP_DISTINCT: {
        const groupCol = groupBy[0];
        return `
          SELECT 
            '${key}' as _transform_key,
            "${groupCol}" as _group_col_0,
            COUNT(*) as _count
            ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
          FROM ${sourceTable}
          GROUP BY "${groupCol}"
        `;
      }

      case TransformType.INTERVAL_BIN: {
        const groupCol = groupBy[0];
        const interval = metadata!.interval!;
        const binExpr = this.getTimeBinExpression(groupCol, interval);
        return `
          SELECT 
            '${key}' as _transform_key,
            ${binExpr} as _group_col_0,
            COUNT(*) as _count
            ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
          FROM ${sourceTable}
          GROUP BY ${binExpr}
          ORDER BY ${binExpr}
        `;
      }

      case TransformType.PN_BIN: {
        const groupCol = groupBy[0];
        return `
          SELECT 
            '${key}' as _transform_key,
            CASE WHEN "${groupCol}" > 0 THEN '>0' ELSE '<=0' END as _group_col_0,
            COUNT(*) as _count
          FROM ${sourceTable}
          GROUP BY CASE WHEN "${groupCol}" > 0 THEN '>0' ELSE '<=0' END
        `;
      }

      case TransformType.CROSS_GROUP: {
        if (metadata?.interval && metadata?.binCol) {
          // cross group with interval binning
          const [col1, col2] = groupBy;
          const binCol = metadata.binCol;
          const binExpr = this.getTimeBinExpression(binCol, metadata.interval);
          const orderBy = binExpr ? `ORDER BY "${col1}", ${binExpr}` : '';

          return `
            SELECT 
              '${key}' as _transform_key,
              "${col1}" as _group_col_0,
              ${binExpr} as _group_col_1,
              COUNT(*) as "COUNT"
              ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
            FROM ${sourceTable}
            GROUP BY "${col1}", ${binExpr}
            ${orderBy}
          `;
        } else {
          // simple cross categorical group
          const [col1, col2] = groupBy;
          return `
            SELECT 
              '${key}' as _transform_key,
              "${col1}" as _group_col_0,
              "${col2}" as _group_col_1,
              COUNT(*) as "COUNT"
              ${numericalAggs.length > 0 ? ', ' + numericalAggs.join(', ') : ''}
            FROM ${sourceTable}
            GROUP BY "${col1}", "${col2}"
          `;
        }
      }

      default:
        throw new Error(`Unknown transform type: ${transformType}`);
    }
  }

  private renameToOriginalColNames(key: string, data: any): any {
    const renamed: any = { ...data }; // shallow copy
    const cols = JSON.parse(key);
    if ('_group_col_0' in data && '_group_col_1' in data) {
      // cross-column transforms
      renamed[cols[0]] = data['_group_col_0'];
      delete renamed['_group_col_0'];
      renamed[cols[1]] = data['_group_col_1'];
      delete renamed['_group_col_1'];
    } else if ('_group_col_0' in data) {
      // basic transforms
      // for TransformType.INTERVAL_BIN, cols[0] is "${groupCol}/(${interval})"
      // for other basic transforms, cols[0] is "${groupCol}"
      renamed[cols[0]] = data['_group_col_0'];
      delete renamed['_group_col_0'];
      if ('_count' in data) {
        // for TransformType.INTERVAL_BIN, cols[1] is "${groupCol}"
        // for other basic transforms, cols[1] is "${groupCol}"
        const countCol = `COUNT(${cols[1]})`;
        renamed[countCol] = data['_count'];
        delete renamed['_count'];
      }
    }

    return renamed;    
  }
 
  public getTransformedData(key: string): any[] {
    return this.transformedData[key] || [];
  }

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
    return intervalMap[interval];
  }

  public async generateChartViews(tableName='data'): Promise<ChartView[]> {
    try {
      await this.generateOriginalViews(tableName);
      this.generateTransformedViews();
    } catch (e) {
      console.error('Error generating chart views:', e);
    } finally {
      return this.views;
    }
  }

  private async generateOriginalViews(tableName: string): Promise<void> {
    const columns = Array.from(this.features.keys());

    for (let i = 0; i < columns.length; i++) {
      for (let j = 0; j < columns.length; j++) {
        if (i === j) continue;
        
        const xCol = columns[i];
        const yCol = columns[j];
        const xFeature = this.features.get(xCol)!;
        const yFeature = this.features.get(yCol)!;

        const chartTypes: ChartType[] = [];
        if (xFeature.type === ColumnType.NUMERICAL && yFeature.type === ColumnType.NUMERICAL && i < j) {
          chartTypes.push(ChartType.SCATTER);
        }
        if (xFeature.type === ColumnType.TEMPORAL && yFeature.type === ColumnType.NUMERICAL && i < j) {
          chartTypes.push(ChartType.LINE);
        }

        for (const chartType of chartTypes) {
          const view = await this.createViewFromOriginalData(
            xCol, yCol, xFeature, yFeature, chartType, tableName
          );
          if (view) this.views.push(view);
        }
      }
    }
  }

  private generateTransformedViews(): void {    
    for (const spec of this.transformSpecs) {
      const data = this.transformedData[spec.key];
      if (!data || data.length === 0) continue;
      
      const transformViews = this.createViewsFromTransformedData(spec, data);
      this.views.push(...transformViews);
    }
  }

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
        query = `
          SELECT "${xCol}" as x, "${yCol}" as y
          FROM ${tableName}
          WHERE "${xCol}" IS NOT NULL AND "${yCol}" IS NOT NULL
          ORDER BY "${xCol}"
        `;
      
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
        seriesNum: 1,
        X,
        Y,
        chartType,
        score: this.calculateScore(xFeature, yFeature, chartType, rows.length),
        description: `${xCol} vs ${yCol}`
      };
    } finally {
      await conn.close();
    }
  }

  private createViewsFromTransformedData(spec: TransformSpec, data: any[]): ChartView[] {
    const views: ChartView[] = [];
    
    const groupCols = spec.columns.groupBy || [];
    const isCrossGroup = groupCols.length == 2;
    const aggCols = Object.keys(data[0]).filter(col => 
      col.startsWith('SUM(') || col.startsWith('AVG(') || col.startsWith('COUNT')
    );

    if (isCrossGroup) {
      views.push(...this.createMultiSeriesViews(spec, data, groupCols, aggCols));
    } else {
      // pair each groupBy column with aggregations: (SUM, AVG, COUNT)
      for (const groupCol of groupCols) {
        // if !TransformType.INTERVAL_BIN, transformed name is the same as original (groupCol)
        const transformedColName = this.getTransformedColNameForInterval(spec, groupCol);
        
        for (const aggCol of aggCols) {
          const chartTypes = this.determineTransformedChartTypes(spec, transformedColName, aggCol, data);
          
          for (const chartType of chartTypes) {
            const view = this.createTransformedView(
              spec, transformedColName, aggCol, chartType, data
            );
            if (view) views.push(view);
          }
        }
      }
    }
    
    return views;
  }

  private createMultiSeriesViews(
    spec: TransformSpec,
    data: any[],
    groupCols: string[],
    aggCols: string[]
  ): ChartView[] {
    const views: ChartView[] = [];
    const [col1, col2] = groupCols;
    // for cross-group (categorical-temporal) (col2 is binned temporal), get transformed name
    // for cross-group (categorical-categorical), transformed name is the same as original
    const transformedCol2 = this.getTransformedColNameForInterval(spec, col2);

    // for each aggregate measure (SUM, AVG, COUNT), create a grouped chart
    for (const aggCol of aggCols) {
      // create series for each distinct col2 value
      // group data by col1 values
      const col2Values = [...new Set(data.map(row => row[transformedCol2]))];
      const col1Values = [...new Set(data.map(row => row[col1]))];
      
      // skip if too many series (unreadable)
      if (col2Values.length > 10) continue;
      
      const X: any[][] = [];
      const Y: any[][] = [];
      
      for (const col2Val of col2Values) {
        const seriesData = data.filter(row => row[transformedCol2] === col2Val);
        const xVals = seriesData.map(row => row[col1]);
        const yVals = seriesData.map(row => row[aggCol]);
        X.push(xVals);
        Y.push(yVals);
      }
      
      // determine chart type
      let chartType: ChartType;
      if (spec.transformType === TransformType.INTERVAL_BIN) {
        chartType = col1Values.length < 7 ? ChartType.BAR : ChartType.LINE;
      } else {
        chartType = ChartType.BAR;
      }
      
      // create view
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
        xName: `${col2} group by ${col1}`,
        yName: aggCol,
        seriesNum: col2Values.length,
        seriesNames: col2Values.map(v => String(v)),
        X,
        Y,
        chartType,
        score: this.calculateScore(xFeature, yFeature, chartType, data.length),
        description: `${col2} group by ${col1} vs ${aggCol}`
      });
    }
    
    return views;
  }

  private getTransformedColNameForInterval(spec: TransformSpec, originalCol: string): string {
    switch (spec.transformType) {
      case TransformType.INTERVAL_BIN:
        return `${originalCol}/(${spec.metadata?.interval || 'year'})`;
      default:
        return originalCol;
    }
  }

  private determineTransformedChartTypes(
    spec: TransformSpec,
    groupCol: string,
    aggCol: string,
    data: any[]
  ): ChartType[] {
    const charts: ChartType[] = [];
    const distinctCount = new Set(data.map(row => row[groupCol])).size;
    const hasPositiveValues = data.every(row => row[aggCol] > 0);
    
    if (spec.transformType === TransformType.INTERVAL_BIN) {
      charts.push(distinctCount < 7 ? ChartType.BAR : ChartType.LINE);
    } else {
      if (hasPositiveValues && this.features.get(groupCol)!.distinct <= 15 && !this.isAvgColumn(aggCol)) {
        charts.push(ChartType.PIE);
      }
      if (distinctCount <= 20) {
        charts.push(ChartType.BAR);
      }
    }
    return charts;
  }

  private createTransformedView(
    spec: TransformSpec,
    groupCol: string,
    aggCol: string,
    chartType: ChartType,
    data: any[]
  ): ChartView | null {
    if (data.length === 0) return null;
    
    const X = [data.map(row => row[groupCol])];
    const Y = [data.map(row => row[aggCol])];

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
      seriesNum: 1,
      X,
      Y,
      chartType,
      score: this.calculateScore(xFeature, yFeature, chartType, data.length),
      description: `${groupCol} vs ${aggCol}`
    };
  }

  private isAvgColumn(feature: ColumnFeatures | string): boolean {
    const name = typeof feature === 'string' ? feature : (feature as any).name;
    if (!name) return false;
    return name.toLowerCase().includes('avg') || name.startsWith('AVG(');
  }

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