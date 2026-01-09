export enum ColumnType {
  CATEGORICAL = 0,
  NUMERICAL = 1,
  TEMPORAL = 2
}

export interface ColumnFeatures {
  type: ColumnType;
  min: any;
  max: any;
  distinct: number;
  ratio: number;
  binNum?: number;
  interval?: string;
  distinctValues?: Array<[any, number]>;
  intervalBins?: any[];
}

export enum ChartType {
  SCATTER = 0,
  LINE = 1,
  BAR = 2,
  PIE = 3
}

export interface ChartView {
  xFeature: ColumnFeatures;
  yFeature: ColumnFeatures;
  xName: string;
  yName: string;
  zId: number;
  seriesNum: number;
  seriesNames?: string[];
  X: any[][];
  Y: any[][];
  chartType: ChartType;
  tupleNum: number;
  score: number;
  description: string;
}

export interface IntervalBin {
  label: string;
  startTime: Date;
  endTime: Date;
  count: number;
}

export enum TimeInterval {
  SECOND = 'second',
  MINUTE = 'minute',
  HOUR = 'hour',
  DAY = 'day',
  MONTH = 'month',
  YEAR = 'year'
}

export interface TransformedData {
  // Map of transformation key -> rows
  // e.g., "group_by_Category" -> [{Category: "A", COUNT: 10, SUM_Sales: 100}, ...]
  [key: string]: any[];
}

export enum TransformType {
  GROUP_DISTINCT = 0,
  INTERVAL_BIN = 1,
  PN_BIN = 2,
  CROSS_GROUP = 3
}

export interface TransformSpec {
  key: string;  // Unique identifier for this transformation
  sourceTable: string;
  transformType: TransformType;
  columns: {
    groupBy?: string[];  // Columns to group by
    aggregate?: string[];  // Columns to aggregate
  };
  metadata?: {
    interval?: string;
    binCol?: string;
    binType?: 'interval' | 'pn';
    xColumnType?: ColumnType; 
  };
}