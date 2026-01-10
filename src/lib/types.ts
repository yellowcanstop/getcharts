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
  interval?: string;
  distinctValues?: Array<[any, number]>;
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
  seriesNum: number;
  seriesNames?: string[];
  X: any[][];
  Y: any[][];
  chartType: ChartType;
  score: number;
  description: string;
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
  // map of transformation key -> rows
  [key: string]: any[];
}

export enum TransformType {
  GROUP_DISTINCT = 0,
  INTERVAL_BIN = 1,
  PN_BIN = 2,
  CROSS_GROUP = 3
}

export interface TransformSpec {
  key: string; 
  sourceTable: string;
  transformType: TransformType;
  columns: {
    groupBy?: string[];  // names of columns to group by
    aggregate?: string[];  // names of columns to aggregate
  };
  metadata?: {
    interval?: string;
    binCol?: string;
    xColumnType?: ColumnType; 
  };
}