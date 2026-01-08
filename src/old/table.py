import datetime
from typing import List, Callable, Union

from .features import Features
from .types import ColumnType
from .view import View, ChartType
from .interval_calculator import TimeIntervalCalculator

class Table(object):
    """
    Represent a data table which can be transformed based on column types and features.

    CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

    Attributes:
        source: Matrix representing the original data table
        viewManager: ViewManager instance to manage views
        transformed: Flag to indicate if the table is transformed
        describe_2d: Description of 2D views
        describe_3d: Description of 3D views
        describe: Combined description of the table
        column_num: Number of columns in the table
        tuple_num: Number of rows (or transformed columns) in the table
        view_num: Number of views generated from the table
        names: List of column names
        types: List of column types
        origins: List of which column the data originated from
        features: List of Features objects for each column
        views: List of View objects generated from the table
        classify_id: ID of the column used for classification
        classify_num: Number of classifications
        classes: List of classification values
    """
    def __init__(self, viewManager, transformed, describe_2d, describe_3d):
        self.source = [] 
        self.viewManager = viewManager 
        self.transformed = transformed
        self.describe_2d, self.describe_3d = describe_2d, describe_3d
        self.describe = self.describe_2d + ', ' + self.describe_3d if self.describe_3d else self.describe_2d
        self.column_num = self.tuple_num = self.view_num = 0
        self.names = []
        self.types = []
        self.origins = []
        self.features = []
        self.views = []
        self.classify_id = -1
        self.classify_num = 1
        self.classes = []


    def get_interval_bins(self, feature):
        """
        Calculate interval bins and update feature properties based on time range.
        
        Args:
            feature: The feature object containing min and max time values.
        """
        calculator = TimeIntervalCalculator(feature.min, feature.max)
        bins, interval = calculator.calculate_bins()
        
        feature.interval_bins = [[b.label, b.start_time, b.end_time, b.count] for b in bins]
        feature.bin_num = len(bins)
        feature.interval = interval.value


    def generate_views(self) -> None:
        """
        Generate syntactically correct views from column type based on guidelines adapted from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).
        """
        transposed = self._transpose_source_table()
        self._process_columns(transposed)
        self._generate_chart_views(transposed)
        self.viewManager.view_num += self.view_num


    def _transpose_source_table(self) -> List[List]:
        """Transpose the source table for column-wise operations."""
        # * unpacks rows of source table to be passed into zip
        return list(map(list, zip(*self.source)))


    def _process_columns(self, transposed: List[List]) -> None:
        """Process each column to extract features."""
        for column_id in range(self.column_num):
            feature = Features(self.names[column_id], self.types[column_id], self.origins[column_id])
            
            if self.transformed:
                self._process_transformed_column(feature, transposed, column_id)
            else:
                self._process_untransformed_column(feature, transposed, column_id)
                
            self.features.append(feature)


    def _process_transformed_column(self, feature: Features, transposed: List[List], column_id: int) -> None:
        """Process column in transformed state."""
        if feature.type == ColumnType.NUMERICAL:
            feature.min, feature.max = min(transposed[column_id]), max(transposed[column_id])
            if feature.min == feature.max:
                self.types[column_id] = feature.type = ColumnType.NONE
                return 

        if feature.type in (ColumnType.CATEGORICAL, ColumnType.TEMPORAL):
            feature.distinct = self.tuple_num
            feature.ratio = 1.0 # indicate all values are distinct


    def _process_untransformed_column(self, feature: Features, transposed: List[List], column_id: int) -> None:
        """Process column in untransformed state."""
        if feature.type in (ColumnType.NUMERICAL, ColumnType.TEMPORAL):
            feature.min, feature.max = min(transposed[column_id]), max(transposed[column_id])
            if feature.min == feature.max:
                self.types[column_id] = feature.type = ColumnType.NONE
                return

        if feature.type in (ColumnType.CATEGORICAL, ColumnType.TEMPORAL):
            self._calculate_distinct_values(feature, column_id)
            if feature.type == ColumnType.TEMPORAL:
                self.get_interval_bins(feature)


    def _calculate_distinct_values(self, feature: Features, column_id: int) -> None:
        """Calculate distinct values and their frequencies for a column."""
        value_counts = {}
        for i in range(self.tuple_num):
            value = self.source[i][column_id]
            value_counts[value] = value_counts.get(value, 0) + 1
        
        feature.distinct = len(value_counts)
        feature.ratio = feature.distinct / self.tuple_num
        feature.distinct_values = [(k, value_counts[k]) for k in sorted(value_counts)]


    def _generate_chart_views(self, transposed: List[List]) -> None:
        """Generate chart views based on configuration."""
        if self.describe_3d == '' and self.classify_id == -1:
            self._generate_2d_views(transposed)
        elif self.describe_3d:
            self._generate_3d_views(transposed)
        else:
            self._generate_classified_views(transposed)


    def _generate_classified_views(self, transposed: List[List]) -> None:
        """Generate scatter plot views for numerical column pairs."""
        for i in range(self.column_num):
            for j in range(self.column_num):
                if i >= j or self.types[i] != ColumnType.NUMERICAL or self.types[j] != ColumnType.NUMERICAL:
                    continue
                
                X, Y = [], []
                current_idx = 0
                for k in range(self.classify_num):
                    next_idx = current_idx + self.classes[k][1]
                    X.append(transposed[i][current_idx:next_idx])
                    Y.append(transposed[j][current_idx:next_idx])
                    current_idx = next_idx
                
                view = View(self, i, j, self.classify_id, self.classify_num, X, Y, ChartType.scatter)
                self.views.append(view)
                self.view_num += 1


    def _generate_3d_views(self, transposed: List[List]) -> None:
        """Generate 3D chart views."""
        for i in range(self.column_num):
            for j in range(self.column_num):
                
                charts = self._determine_3d_chart_types(i, j)

                # Create views for the determined chart types
                for chart in charts:
                    # Delta is the number of rows for each classification
                    delta = self.tuple_num // self.classify_num
                    # Iterate count: number of classifications. for each iteration, a slice of the list transposed[j] is taken
                    # Slice starts at series*delta and ends at (series+1)*delta,
                    # effectively dividing the transposed[j] into classify_num sublists, each containing delta elements
                    series_data = [transposed[j][series * delta:(series + 1) * delta] for series in range(self.classify_num)]
                    v = View(self, i, j, self.classify_id, self.classify_num, [transposed[i][0:delta]], series_data, chart)
                    self.views.append(v)
                    self.view_num += 1
    

    def _determine_3d_chart_types(self, i: int, j: int) -> List[ChartType]:
        """Determine appropriate chart types for 3D views."""
        fi, fj = self.features[i], self.features[j]

        if fi.type == ColumnType.CATEGORICAL and fj.type == ColumnType.NUMERICAL:
           return [ChartType.bar]
        elif fi.type == ColumnType.TEMPORAL and fj.type == ColumnType.NUMERICAL:
            return self._get_temporal_numerical_charts(self.tuple_num / self.classify_num)
        return []
    

    def _generate_2d_views(self, transposed: List[List]) -> None:
        """Generate 2D chart views."""
        for i in range(self.column_num):
            for j in range(self.column_num):
                if i == j: # all combinations of 2 columns except the same column
                    continue
                    
                charts = self._determine_2d_chart_types(i, j)

                # Create views for the determined chart types
                for chart in charts:
                    view = View(self, i, j, -1, 1, [transposed[i]], [transposed[j]], chart)
                    self.views.append(view)
                    self.view_num += 1


    def _determine_2d_chart_types(self, i: int, j: int) -> List[ChartType]:
        """Determine appropriate chart types for 2D views."""
        fi, fj = self.features[i], self.features[j]
        
        if fi.type == ColumnType.CATEGORICAL and fj.type == ColumnType.NUMERICAL and fi.ratio == 1.0:
            return self._get_categorical_numerical_charts(fi, fj)
        elif fi.type == ColumnType.TEMPORAL and fj.type == ColumnType.NUMERICAL and fi.ratio == 1.0:
            return self._get_temporal_numerical_charts(fi.distinct)
        elif (not self.transformed) and fi.type == ColumnType.NUMERICAL and fj.type == ColumnType.NUMERICAL and i < j:
            return [ChartType.scatter]
        return []


    def _get_categorical_numerical_charts(self, fi: Features, fj: Features) -> List[ChartType]:
        """Get syntactically correct chart types for categorical vs numerical data."""
        charts = []
        if fj.min > 0 and fi.distinct <= 5 and not self._is_avg_column(fj.name):
            charts.append(ChartType.pie)
        if fi.distinct <= 20:
            charts.append(ChartType.bar)
        return charts


    def _get_temporal_numerical_charts(self, metric: int) -> List[ChartType]:
        """Get syntactically correct chart types for temporal vs numerical data."""
        return [ChartType.bar] if metric < 7 else [ChartType.line]


    def _is_avg_column(self, name: str) -> bool:
        """Check if column name indicates an average calculation."""
        return len(name) >= 6 and name[0:4] == 'AVG(' and name[-1] == ')'


    def group_by_distinct_bin(self, column_id: int, begin: int, end: int) -> 'Table':
        """
        Generates a new table by grouping data and calculating aggregate statistics.

        Creates a grouped table with counts, sums, and averages for numerical columns
        based on unique values in the specified column.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            column_id: Index of the column to group by
            begin: Starting row index for processing
            end: Ending row index for processing (exclusive)

        Returns:
            A new Table containing grouped data with aggregate statistics
        """
        def _initialize_groups() -> dict:
            """Initialize dictionary with groups and their count arrays."""
            groups = {}
            for i in range(self.features[column_id].distinct):
                groups[self.features[column_id].distinct_values[i][0]] = [0]
            return groups

        def _count_group_occurrences(groups: dict) -> None:
            """Count occurrences of each group in the data."""
            for i in range(begin, end):
                groups[self.source[i][column_id]][0] += 1

        def _calculate_aggregates(groups: dict) -> None:
            """Calculate sums for numerical columns."""
            for row_idx in range(begin, end):
                group_key = self.source[row_idx][column_id]
                sum_col_idx = 1
                
                for col_idx in range(self.column_num):
                    if self.types[col_idx] != ColumnType.NUMERICAL:
                        continue
                        
                    value = self.source[row_idx][col_idx]
                    if self._is_numeric_value(value):
                        groups[group_key][sum_col_idx] += int(value)
                    sum_col_idx += 2

        def _calculate_averages(groups: dict, table: 'Table') -> None:
            """Calculate averages from sums."""
            for group in groups.values():
                count = group[0]
                if count:
                    for col_idx in range(1, table.column_num, 2):
                        group[col_idx + 1] = group[col_idx] / count

        def _finalize_table(table: 'Table', groups: dict) -> None:
            """Add group labels and sort if temporal."""
            for group_key, group_data in groups.items():
                group_data.append(group_key)
                table.source.append(group_data)

            table.column_num += 1
            table.names.append(self.names[column_id])
            table.types.append(self.types[column_id])
            table.origins.append(column_id)

            if self.features[column_id].type == ColumnType.TEMPORAL:
                table.source.sort(key=lambda x: x[-1])

        # Execute the grouping process
        groups = _initialize_groups()
        _count_group_occurrences(groups)

        # Initialize a new table
        column_name = self.names[column_id]
        new_table = Table(self.viewManager, True, f'GROUP BY {column_name}', '') 
        new_table.column_num = 1
        new_table.tuple_num = self.features[column_id].distinct
        new_table.names = [f'COUNT({column_name})']
        new_table.types = [ColumnType.NUMERICAL]
        new_table.origins = [column_id]
        
        new_table = self._add_numerical_columns(new_table, groups.values())
        _calculate_aggregates(groups)
        _calculate_averages(groups, new_table)
        _finalize_table(new_table, groups)

        return new_table
  

    def group_by_interval_bin(self, column_id: int, begin: int, end: int) -> 'Table':
        """
        Groups data by time intervals and calculates aggregated statistics.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            column_id: Index of the datetime column to bin
            begin: Starting row index for processing
            end: Ending row index for processing (exclusive)

        Returns:
            A new Table containing interval-binned data with statistics
        """
        # Initialize new table
        bins = self.features[column_id].interval_bins
        bin_num = self.features[column_id].bin_num
        interval = self.features[column_id].interval
        column_name = self.names[column_id]
        new_table = Table(self.viewManager, True, f'BIN {column_name} BY {interval}', '')
        new_table.tuple_num = bin_num
        new_table.source = [[] for _ in range(bin_num)]

        def _normalize_date(date: datetime) -> datetime.date:
            """Convert datetime to date if needed."""
            if type(date) != type(bins[0][1]):
                return datetime.date(date.year, date.month, date.day)
            return date

        def _process_rows(table: 'Table') -> None:
            """Process each row and update bin statistics."""
            for row_idx in range(begin, end):
                date = _normalize_date(self.source[row_idx][column_id])
                
                for bin_idx in range(bin_num):
                    if bins[bin_idx][1] <= date <= bins[bin_idx][2]:
                        bins[bin_idx][3] += 1
                        sum_col_idx = 0
                        
                        for col_idx in range(self.column_num):
                            if self.types[col_idx] != ColumnType.NUMERICAL:
                                continue
                                
                            value = self.source[row_idx][col_idx]
                            if self._is_numeric_value(value):
                                table.source[bin_idx][sum_col_idx] += int(value)
                            sum_col_idx += 2
                        break

        def _calculate_statistics(table: 'Table') -> None:
            """Calculate averages and add final columns."""
            for bin_idx in range(bin_num):
                bin_count = bins[bin_idx][3]
                if bin_count:
                    for col_idx in range(0, table.column_num, 2):
                        bin_data = table.source[bin_idx]
                        bin_data[col_idx + 1] = bin_data[col_idx] / bin_count
                        
                bin_data.extend([bin_count, bins[bin_idx][0]])

        # Execute the binning process
        new_table = self._add_numerical_columns(new_table, new_table.source)
        _process_rows(new_table)
        _calculate_statistics(new_table)

        # Add final columns
        new_table.column_num += 2
        new_table.names.extend([f'COUNT({column_name})', f'{column_name}/({interval})'])
        new_table.types.extend([ColumnType.NUMERICAL, ColumnType.TEMPORAL])
        new_table.origins.extend([column_id, column_id])

        return new_table


    def group_by_hour_bin(self, column_id: int, begin: int, end: int) -> 'Table':
        """
        Groups data by hour (0-23) and calculates counts, sums, and averages for numerical columns.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            column_id: Index of the datetime column to bin by hour
            begin: Starting row index for processing
            end: Ending row index for processing (exclusive)

        Returns:
            A new Table containing hourly-binned data with aggregated statistics
        """
        HOURS_IN_DAY = 24

        # Initialize new table
        column_name = self.names[column_id]
        new_table = Table(self.viewManager, True, f'BIN {column_name} BY HOUR', '')
        new_table.source = [[str(i), 0] for i in range(HOURS_IN_DAY)]
        new_table.column_num = 2
        new_table.tuple_num = HOURS_IN_DAY
        new_table.names = [f"{column_name} oclock", f"COUNT({column_name})"]
        new_table.types = [ColumnType.CATEGORICAL, ColumnType.NUMERICAL]
        new_table.origins = [column_id, column_id]
        
        def _process_rows(table: 'Table') -> None:
            """Process each row and update statistics."""
            for row_idx in range(begin, end):
                # datetime.hour extracts the hour for a datetime object
                hour = self.source[row_idx][column_id].hour
                table.source[hour][1] += 1  # Increment count
                
                sum_col_idx = 2
                for col_idx in range(self.column_num):
                    if self.types[col_idx] != ColumnType.NUMERICAL:
                        continue

                    table.source[hour][sum_col_idx] += self.source[row_idx][col_idx]
                    sum_col_idx += 2

        # Execute the binning process
        new_table = self._add_numerical_columns(new_table, new_table.source)
        _process_rows(new_table)
        new_table = self._calculate_averages(new_table)

        return new_table
    

    def group_by_weekday_bin(self, column_id: int, begin: int, end: int) -> 'Table':
        """
        Groups data by weekday and calculates counts, sums, and averages for numerical columns.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            column_id: Index of the datetime column to bin by weekday
            begin: Starting row index for processing
            end: Ending row index for processing (exclusive)

        Returns:
            A new Table containing weekday-binned data with aggregated statistics
        """
        WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thur', 'Fri', 'Sat', 'Sun']
        
        # Initialize new table
        column_name = self.names[column_id]
        new_table = Table(self.viewManager, True, f'BIN {column_name} BY WEEKDAY', '')
        new_table.source = [[day, 0] for day in WEEKDAYS]
        new_table.tuple_num = len(WEEKDAYS)
        new_table.names = [column_name, f'COUNT({column_name})']
        new_table.types = [ColumnType.CATEGORICAL, ColumnType.NUMERICAL]
        new_table.origins = [column_id, column_id]
        new_table.column_num = 2

        def _process_rows(table: 'Table') -> None:
            """Process each row and update statistics."""
            for row_idx in range(begin, end):
                # datetime.weekday() extracts the day of week for a datetime object
                weekday = self.source[row_idx][column_id].weekday()
                table.source[weekday][1] += 1 # Increment count
                
                sum_col_idx = 2
                for col_idx in range(self.column_num):
                    if self.types[col_idx] != ColumnType.NUMERICAL:
                        continue
                        
                    value = self.source[row_idx][col_idx]

                    if self._is_numeric_value(value):
                        table.source[weekday][sum_col_idx] += int(value)
                    sum_col_idx += 2

        # Execute the binning process
        new_table = self._add_numerical_columns(new_table, new_table.source)
        _process_rows(new_table)
        new_table = self._calculate_averages(new_table)

        return new_table


    def _has_negative_min(self, col_idx: int) -> bool:
        """Check if a column has a negative minimum value."""
        return (self.features[col_idx].min < 0)


    def _is_numeric_value(self, value: Union[int, float, str]) -> bool:
        """Check if a value can be treated as numeric."""
        return (isinstance(value, (int, float)) or 
                (isinstance(value, str) and value.isdigit()))

    
    def _add_numerical_columns(self, table: 'Table', iter: list) -> 'Table':
        """Add additional columns for numerical data statistics."""
        for col_idx in range(self.column_num):
            if self.types[col_idx] != ColumnType.NUMERICAL:
                continue
                
            col_name = self.names[col_idx]
            table.column_num += 2
            table.names.extend([f'SUM({col_name})', f'AVG({col_name})'])
            
            # Set column types
            col_types = ([ColumnType.NONE, ColumnType.NUMERICAL] 
                        if self._has_negative_min(col_idx)
                        else [ColumnType.NUMERICAL, ColumnType.NUMERICAL])
            table.types.extend(col_types)
            table.origins.extend([col_idx, col_idx])

            # Initialize new columns with zeros
            for i in iter:
                i.extend([0, 0])
        
        return table


    def _calculate_averages(self, table: 'Table') -> 'Table':
        """Calculate averages for numerical columns."""
        for row in table.source:
            count = row[1]   
            if count:   
                for col_idx in range(2, table.column_num, 2):
                    row[col_idx + 1] = row[col_idx] / count
        return table


    def group_by_positive_negative_bins(self, column_id: int, begin: int, end: int) -> 'Table':
        """
        Creates a binary classification table by binning values as positive (>0) or non-positive (<=0).
        
        Generates a new table with two columns:
        1. Category: ">0" or "<=0"
        2. Count: Number of values in each category

        Args:
            column_id: Index of the column to be binned
            begin: Starting row index for processing
            end: Ending row index for processing (exclusive)

        Returns:
            A new Table containing the binned data with counts

        """
        POSITIVE = ">0"
        NON_POSITIVE = "<=0"      
        
        # Initialize table
        column_name = self.names[column_id]
        new_table = Table(self.viewManager, True, f'BIN {column_name} BY ZERO', '')
        new_table.source = [[POSITIVE, 0], [NON_POSITIVE, 0]]
        new_table.column_num = new_table.tuple_num = 2
        new_table.names.extend([column_name, f'COUNT({column_name})'])
        new_table.types.extend([ColumnType.CATEGORICAL, ColumnType.NUMERICAL])
        new_table.origins.extend([column_id, column_id])

        # Count values in each bin
        for row_idx in range(begin, end):
            bin_idx = 0 if self.source[row_idx][column_id] > 0 else 1
            new_table.source[bin_idx][1] += 1

        return new_table


    def get_grouped_table(self, classify_id: int, x_id: int, grouping_function: Callable) -> 'Table':
        """
        Creates a new grouped table by applying a grouping function to specified columns.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            classify_id: Column ID used for grouping
            x_id: Column ID to apply the grouping function to
            group_function: Function that performs the grouping operation

        Returns:
            A new Table instance containing the grouped data

        """
        # Get initial group
        initial = grouping_function(x_id, 0, self.features[classify_id].distinct_values[0][1])

        # Initialize new table with metadata
        new_table = Table(self.viewManager, True, f'GROUP BY {self.names[classify_id]}', initial.describe_2d)
        new_table.tuple_num = initial.tuple_num * self.features[classify_id].distinct
        new_table.column_num = initial.column_num
        new_table.names = initial.names[:]
        new_table.types = initial.types[:]
        new_table.origins = initial.origins[:]
        new_table.classify_id = classify_id
        new_table.classify_num = self.features[classify_id].distinct
        new_table.classes = self.features[classify_id].distinct_values

        # Process each group
        current_idx = 0
        for group_idx in range(self.features[classify_id].distinct):
            end_idx = current_idx + self.features[classify_id].distinct_values[group_idx][1]
            group_result = grouping_function(x_id, current_idx, end_idx)
            new_table.source.extend(group_result.source)
            current_idx = end_idx

        return new_table


    def get_transformed_tables(self) -> List['Table']:
        """
        Generates transformed views of the data tables based on column types and features.
        
        Returns:
            list: Collection of transformed tables based on various transformations
                like grouping, binning by interval/hour/week, and classification.
        """
        new_tables = []

        self.generate_views()
        
        if self.transformed:
            return new_tables

        new_tables.extend(self._generate_basic_transformations())
        new_tables.extend(self._generate_grouping_transformations())
        
        return new_tables
 

    def _generate_basic_transformations(self) -> List['Table']:
        """Generate basic transformations for each column based on its type."""
        tables = []
        
        for col_idx in range(self.column_num):
            if self._should_apply_grouping(col_idx):
                tables.append(self.group_by_distinct_bin(col_idx, 0, self.tuple_num))
        
            if self.types[col_idx] == ColumnType.TEMPORAL:
                tables.append(self.group_by_interval_bin(col_idx, 0, self.tuple_num))
                tables.append(self.group_by_weekday_bin(col_idx, 0, self.tuple_num))
                if self._contains_time_info(col_idx):
                    tables.append(self.group_by_hour_bin(col_idx, 0, self.tuple_num))
                
            if self._should_apply_pn_binning(col_idx):
                tables.append(self.group_by_positive_negative_bins(col_idx, 0, self.tuple_num))
        
        return tables


    def _generate_grouping_transformations(self) -> List['Table']:
        """Generate grouping transformations."""
        tables = []
        
        for col_idx in range(self.column_num):
            if self._not_simple_categorical(col_idx):
                continue  
            tables.extend(self._process_cross_columns(col_idx))
        
        return tables

    
    def _process_cross_columns(self, col_idx: int) -> List['Table']:
        """Process a column and generate related transformations."""
        tables = []
        
        new_table = self._create_base_table(col_idx)

        for other_col_idx in range(self.column_num):
            if self.types[other_col_idx] == ColumnType.NUMERICAL:
                new_table.names.append(self.names[other_col_idx])
                new_table.types.append(ColumnType.NUMERICAL)
                new_table.origins.append(other_col_idx)
                new_table.column_num += 1
                for k in range(self.tuple_num):
                    new_table.source[k].append(self.source[k][other_col_idx])

        tables.append(new_table)

        # Generate additional transformations
        for other_col_idx in range(self.column_num):
            if col_idx == other_col_idx:
                continue
            tables.extend(self._generate_cross_column_transformations(col_idx, other_col_idx))
        
        return tables

    
    def _generate_cross_column_transformations(self, col_idx: int, other_col_idx: int) -> List['Table']:
        """Generate transformations based on two columns."""
        tables = []
        
        if self.types[other_col_idx] == ColumnType.CATEGORICAL or self.types[other_col_idx] == ColumnType.TEMPORAL:
            column_pairs = set()

            for k in range(self.tuple_num):
                column_pairs.add((self.source[k][col_idx], self.source[k][other_col_idx]))

            length = len(column_pairs)

            if self._should_apply_pair_grouping(length, col_idx, other_col_idx):
                new_table = self.get_grouped_table(col_idx, other_col_idx, self.group_by_distinct_bin)

                if length == self.viewManager.tuple_num:
                    for k in range(new_table.column_num):
                        if new_table.names[k][0:4] == 'SUM(':
                            new_table.names[k] = new_table.names[k][4:-1]
                            new_table.types[k] = ColumnType.NUMERICAL
                        elif new_table.names[k][0:4] == 'AVG(':
                            new_table.types[k] = ColumnType.NONE
                tables.append(new_table)
        
        if self.types[other_col_idx] == ColumnType.TEMPORAL:
            tables.append(self.get_grouped_table(col_idx, other_col_idx, self.group_by_interval_bin))
            tables.append(self.get_grouped_table(col_idx, other_col_idx, self.group_by_weekday_bin))
            if self._contains_time_info(other_col_idx):
                tables.append(self.get_grouped_table(col_idx, other_col_idx, self.group_by_hour_bin))
        
        if self._should_apply_pn_binning(other_col_idx):
            tables.append(self.get_grouped_table(col_idx, other_col_idx, self.group_by_positive_negative_bins))
        
        return tables


    def _contains_time_info(self, col_idx: int) -> bool:
        """Check if it contains time information by comparing against an arbitrary pure date."""
        return (type(self.features[col_idx].min) != type(datetime.date(2020, 10, 10)))


    def _should_apply_grouping(self, col_idx: int) -> bool:
        """Check if grouping should be applied to the column."""
        return ((self.types[col_idx] == ColumnType.TEMPORAL or self.types[col_idx] == ColumnType.CATEGORICAL) 
                and self.features[col_idx].ratio < 1.0)


    def _should_apply_pair_grouping(self, length: int, col_idx: int, other_col_idx: int) -> bool:
        """Check if pair grouping should be applied."""
        return length > self.features[other_col_idx].distinct and ((self.types[other_col_idx] == ColumnType.CATEGORICAL and self.features[col_idx].distinct <= self.features[other_col_idx].distinct) or self.types[other_col_idx] == ColumnType.TEMPORAL)


    def _should_apply_pn_binning(self, col_idx: int) -> bool:
        """Check if positive/negative binning should be applied."""
        return (self.types[col_idx] == ColumnType.NUMERICAL 
                and self.features[col_idx].min != '' 
                and self.features[col_idx].min < 0)


    def _not_simple_categorical(self, col_idx: int) -> bool:
        """Check if column is categorical with few distinct values."""
        return (self.types[col_idx] != ColumnType.CATEGORICAL or self.features[col_idx].distinct > 5)


    def _create_base_table(self, col_idx: int) -> 'Table':
        """Create the base table for grouped transformations."""
        self.source.sort(key=lambda tuple: tuple[col_idx])
        base_table = Table(self.viewManager, True, f'GROUP BY {self.names[col_idx]}', '')
        base_table.tuple_num = self.tuple_num
        base_table.source = [[] for _ in range(self.tuple_num)]
        base_table.classify_id = col_idx
        base_table.classify_num = self.features[col_idx].distinct
        base_table.classes = self.features[col_idx].distinct_values
        return base_table

    
  