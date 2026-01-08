from datetime import datetime, date, timedelta
from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum


class TimeInterval(Enum):
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"
    MONTH = "MONTH"
    YEAR = "YEAR"


@dataclass
class IntervalBin:
    label: str
    start_time: datetime
    end_time: datetime
    count: int = 0


class TimeIntervalCalculator:

    MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'June', 
              'July', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec']
    

    def __init__(self, min_time: datetime, max_time: datetime):
        self.min_time = min_time
        self.max_time = max_time


    def _create_same_day_bins(self) -> Tuple[List[IntervalBin], TimeInterval]:
        """Handle intervals within the same day (seconds, minutes, hours)"""
        if self.min_time.hour == self.max_time.hour:
            if self.min_time.minute == self.max_time.minute:
                return self._create_second_bins(), TimeInterval.SECOND
            return self._create_minute_bins(), TimeInterval.MINUTE
        return self._create_hour_bins(), TimeInterval.HOUR


    def _create_second_bins(self) -> List[IntervalBin]:
        """Create second bins."""
        return [
            IntervalBin(
                f"{i}s",
                datetime(self.min_time.year, self.min_time.month, self.min_time.day,
                        self.min_time.hour, self.min_time.minute, i),
                datetime(self.min_time.year, self.min_time.month, self.min_time.day,
                        self.min_time.hour, self.min_time.minute, i)
            )
            for i in range(self.min_time.second, self.max_time.second + 1)
        ]


    def _create_minute_bins(self) -> List[IntervalBin]:
        """Create minute bins."""
        return [
            IntervalBin(
                f"{i}m",
                datetime(self.min_time.year, self.min_time.month, self.min_time.day,
                        self.min_time.hour, i, 0),
                datetime(self.min_time.year, self.min_time.month, self.min_time.day,
                        self.min_time.hour, i, 59)
            )
            for i in range(self.min_time.minute, self.max_time.minute + 1)
        ]


    def _create_hour_bins(self) -> List[IntervalBin]:
        """Create hour bins."""
        return [
            IntervalBin(
                f"{i} oclock",
                datetime(self.min_time.year, self.min_time.month, self.min_time.day, i, 0, 0),
                datetime(self.min_time.year, self.min_time.month, self.min_time.day, i, 59, 59)
            )
            for i in range(self.min_time.hour, self.max_time.hour + 1)
        ]


    def _create_day_bins(self) -> List[IntervalBin]:
        """Create day bins."""
        return [
            IntervalBin(
                f"{i}th",
                date(self.min_time.year, self.min_time.month, i),
                date(self.min_time.year, self.min_time.month, i)
            )
            for i in range(self.min_time.day, self.max_time.day + 1)
        ]


    def _create_month_bins(self) -> List[IntervalBin]:
        """
        Create month bins.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        """
        bins = []
        for month in range(self.min_time.month, self.max_time.month + 1):
            start_date = date(self.min_time.year, month, 1)
            if month == 12:
                end_date = date(self.min_time.year, 12, 31)
            else:
                end_date = (date(self.min_time.year, month + 1, 1) - timedelta(1))
            bins.append(IntervalBin(self.MONTHS[month], start_date, end_date))
        return bins


    def _create_year_bins(self) -> List[IntervalBin]:
        """
        Create year bins.
        
        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        """
        year_span = self.max_time.year - self.min_time.year + 1
        if year_span <= 20:
            return [
                IntervalBin(
                    str(year),
                    date(year, 1, 1),
                    date(year, 12, 31)
                )
                for year in range(self.min_time.year, self.max_time.year + 1)
            ]
        
        year_delta = (year_span // 10) + (1 if year_span % 10 > year_span // 10 else 0)
        bins = []
        begin_year = self.min_time.year
        
        while begin_year <= self.max_time.year:
            end_year = min(begin_year + year_delta - 1, self.max_time.year)
            label = str(begin_year) if begin_year == end_year else f"{begin_year}~{end_year}"
            bins.append(IntervalBin(
                label,
                date(begin_year, 1, 1),
                date(end_year, 12, 31)
            ))
            begin_year += year_delta
        return bins


    def calculate_bins(self) -> Tuple[List[IntervalBin], TimeInterval]:
        """Calculate the appropriate time interval bins"""
        if (not isinstance(self.min_time, date) and 
            self.min_time.year == self.max_time.year and 
            self.min_time.month == self.max_time.month and 
            self.min_time.day == self.max_time.day):
            return self._create_same_day_bins()
        
        if self.min_time.year == self.max_time.year:
            if self.min_time.month == self.max_time.month:
                return self._create_day_bins(), TimeInterval.DAY
            return self._create_month_bins(), TimeInterval.MONTH
        return self._create_year_bins(), TimeInterval.YEAR

