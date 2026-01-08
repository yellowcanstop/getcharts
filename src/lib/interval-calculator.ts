import type { AsyncDuckDB } from '@duckdb/duckdb-wasm';
import { type ColumnFeatures, type IntervalBin, TimeInterval } from './types';

export class IntervalCalculator {
  constructor(private db: AsyncDuckDB) {}

  public async calculateIntervalBins(feature: ColumnFeatures, columnName: string, tableName='data') {
    const conn = await this.db.connect();
    try {
      const min = new Date(feature.min);
      const max = new Date(feature.max);
      const interval = this.determineInterval(min, max);
      const result = await conn.query(`
        SELECT
          date_trunc('${interval}', "${columnName}") as bin_start,
          COUNT(*) as count
        FROM "${tableName}"
        WHERE "${columnName}" IS NOT NULL
        GROUP BY bin_start
        ORDER BY bin_start
      `);
      const rows = result.toArray()
      const bins: IntervalBin[] = rows.map(row => {
        const start = new Date(row.bin_start);
        const end = this.calculateBinEnd(start, interval);
        return {
          label: this.formatLabel(start, end, interval),
          startTime: start,
          endTime: end,
          count: row.count
        };
      });
      feature.intervalBins = bins;
      feature.binNum = bins.length;
      feature.interval = interval;
    } finally {
      await conn.close();
    }
  }

  private determineInterval(min: Date, max: Date): TimeInterval {
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

  private calculateBinEnd(start: Date, interval: TimeInterval): Date {
    const end = new Date(start);
    switch (interval) {
      case TimeInterval.SECOND:
        end.setSeconds(end.getSeconds() + 1);
        end.setMilliseconds(-1);
        break;
      case TimeInterval.MINUTE:
        end.setMinutes(end.getMinutes() + 1);
        end.setMilliseconds(-1);
        break;
      case TimeInterval.HOUR:
        end.setHours(end.getHours() + 1);
        end.setMilliseconds(-1);
        break;
      case TimeInterval.DAY:
        end.setDate(end.getDate() + 1);
        end.setMilliseconds(-1);
        break;
      case TimeInterval.MONTH:
        end.setMonth(end.getMonth() + 1);
        end.setMilliseconds(-1);
        break;
      case TimeInterval.YEAR:
        end.setFullYear(end.getFullYear() + 1);
        end.setMilliseconds(-1);
        break;
    }
    return end;
  }

  private formatLabel(start: Date, end: Date, interval: TimeInterval): string {
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'June', 
                    'July', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'];
    switch (interval) {
      case TimeInterval.SECOND:
        return `${start.getSeconds()}s`;
      case TimeInterval.MINUTE:
        return `${start.getMinutes()}m`;
      case TimeInterval.HOUR:
        return `${start.getHours()}h`;
      case TimeInterval.DAY:
        return `${start.getDate()}`;
      case TimeInterval.MONTH:
        return MONTHS[start.getMonth()];
      case TimeInterval.YEAR:
        if (end.getFullYear() > start.getFullYear()) {
          return `${start.getFullYear()}~${end.getFullYear()}`;
        }
        return start.getFullYear().toString();
      default:
        return start.toISOString();
    }
  }

}