import math
import numpy as np
from numpy import corrcoef
from .types import ColumnType
from typing import List, Optional
import warnings


class ChartType(object):
    scatter = 0
    line = 1
    bar = 2
    pie = 3
    chart = ['scatter','line','bar','pie']


class View(object):
    """A class representing a visualization view of table data.
    
    Attributes:
        table: The table containing the data
        fx: Feature attributes for x-axis
        fy: Feature attributes for y-axis
        x_name: Name of x-axis
        y_name: Name of y-axis
        z_id: ID for z-axis (grouping)
        series_num: Number of data series
        X: List of x-axis data
        Y: List of y-axis data
        chart: Chart type
        tuple_num: Number of tuples after transformation
        score: View score
        describe: Description of the view
    """

    def __init__(self, table, x_id: int, y_id: int, z_id: int, 
                 series_num: int, X: List, Y: List, chart: int):
        self.table = table
        self.fx = table.features[x_id]
        self.fy = table.features[y_id]
        self.x_name = self.fx.name
        self.y_name = self.fy.name
        self.z_id = z_id
        self.series_num = series_num
        self.X = X
        self.Y = Y
        self.chart = chart
        self.tuple_num = table.tuple_num
        self.score = 0
        self.describe = self._generate_description()

    
    def _calculate_correlation_coefficient(self, data1: List[float], 
                                    data2: List[float]) -> float:
        """Calculate correlation coefficient between two data series."""
        try:
            # Filter out any inf/nan values before correlation
            mask = np.isfinite(data1) & np.isfinite(data2)
            if not np.any(mask):
                return 0
                
            filtered_data1 = np.array(data1)[mask]
            filtered_data2 = np.array(data2)[mask]
            
            if len(filtered_data1) < 2:  # Need at least 2 points for correlation
                return 0
                
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                result = abs(corrcoef(filtered_data1, filtered_data2)[0][1])

            return result if -1 <= result <= 1 else 0
        except Exception:
            return 0
    

    def _get_log_data(self, data: List[float], min_value: float) -> Optional[List[float]]:
        """Get logarithmic transformation of data if possible."""
        try:
            if min_value != '' and min_value > 0:
                return list(map(math.log, data))
        except Exception:
            pass
        return None


    def get_correlation(self, series_id: int) -> float:
        """Calculate the strongest correlation between X and Y data.
        
        Tests linear, exponential, logarithmic and power relationships.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).
        
        Args:
            series_id: Index of the data series
            
        Returns:
            Maximum correlation coefficient found
        """
        if self.fx.type == ColumnType.CATEGORICAL:
            return 0

        # Prepare data
        if self.fx.type == ColumnType.TEMPORAL:
            data1 = list(range(self.tuple_num // self.series_num))
        else:
            data1 = self.X[series_id]
        data2 = self.Y[series_id]

        # Get log transformations
        log_data1 = self._get_log_data(data1, self.fx.min) if self.fx.type != ColumnType.TEMPORAL else None
        log_data2 = self._get_log_data(data2, self.fy.min)

        correlations = []
        
        # Linear correlation
        correlations.append(self._calculate_correlation_coefficient(data1, data2))

        # Exponential correlation
        if log_data2:
            correlations.append(self._calculate_correlation_coefficient(data1, log_data2))

        # Logarithmic correlation
        if log_data1:
            correlations.append(self._calculate_correlation_coefficient(log_data1, data2))

        # Power correlation
        if log_data1 and log_data2:
            correlations.append(self._calculate_correlation_coefficient(log_data1, log_data2))

        return max(correlations) if correlations else 0
    

    def get_features(self) -> str:
        """
        Generating a string of the 14 core features of each view.

        For a new input dataset, 14 core features are stored with the format:
        <line> .=. <target> qid:<qid> <feature>:<value> <feature>:<value> ... <feature>:<value> 

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            None
            
        Returns:
            The 14 features represented as a string
            
        """
        correlation = max([self.get_correlation(i) for i in range(self.series_num)])
        if self.fx.min == '':
            self.fx.min = 0
        if self.fy.min == '':
            self.fy.min = 0
        if self.fx.type == ColumnType.TEMPORAL:
            return '1 qid:1 1:' + str(self.fx.type) + ' 2:' + str(self.fy.type) + ' 3:' + str(
                self.tuple_num) + ' 4:' + str(self.tuple_num) + ' 5:0 6:' + str(self.fy.min) + ' 7:0 8:' + str(
                self.fy.max) + ' 9:' + str(self.fx.distinct) + ' 10:' + str(self.fy.distinct) + ' 11:' + str(
                self.fx.ratio) + ' 12:' + str(self.fy.ratio) + ' 13:' + str(correlation) + ' 14:' + str(self.chart)
        else:
            return '1 qid:1 1:' + str(self.fx.type) + ' 2:' + str(self.fy.type) + ' 3:' + str(
                self.tuple_num) + ' 4:' + str(self.tuple_num) + ' 5:' + str(self.fx.min) + ' 6:' + str(
                self.fy.min) + ' 7:' + str(self.fx.max) + ' 8:' + str(self.fy.max) + ' 9:' + str(
                self.fx.distinct) + ' 10:' + str(self.fy.distinct) + ' 11:' + str(self.fx.ratio) + ' 12:' + str(
                self.fy.ratio) + ' 13:' + str(correlation) + ' 14:' + str(self.chart)
    

    def _generate_description(self) -> str:
        """Generate a description of the view."""
        return f"chart: {ChartType.chart[self.chart]} x_name: {self.fx.name} y_name: {self.fy.name} describe: {self.table.describe}".lower()
