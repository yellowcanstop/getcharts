import os
import sys
import traceback
import pandas as pd
import datetime
import re 
import math
from typing import List
from pathlib import Path
import logging

import plotly.graph_objects as go

from .manager import ViewManager
from .table import Table
from .view import ChartType
from .types import ColumnType

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class recommender(object):
    
    @staticmethod
    def is_valid_datetime(date_string: str) -> bool:
        """Validates if a string can be parsed as a datetime."""
        if not isinstance(date_string, str):
            return False
        try:
            datetime.datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')
            pd.to_datetime(date_string)
            return True
        except (ValueError, TypeError):
            return False
        
    @staticmethod
    def _get_data_path(filepath: str) -> Path:
        """Get the correct path for data files"""
        base_path = Path(filepath)
        return base_path.parent / base_path.stem
    

    def _validate_column_types(self) -> None:        
        """
        Validates that all column types for the input dataset are supported.
        
        Raises:
            ValueError: If any column type is not supported, with details about the invalid column.
        """
        for column_name, column_type in zip(self.column_names, self.column_types):
            if ColumnType.from_string(column_type) == ColumnType.NONE:
                raise ValueError(
                    f"Unsupported column type '{column_type}' for column '{column_name}'"
                )
    

    def replace_nan_with_null(self, data):
        """
        Recursively replaces NaN values with None in nested data structures for valid JSON tokens.
        
        Args:
            data: Input data that can be a dict, list, float, or other type
            
        Returns:
            Data structure with NaN values replaced by None
        """
        if isinstance(data, dict):
            return {k: self.replace_nan_with_null(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.replace_nan_with_null(v) for v in data]
        elif isinstance(data, float) and math.isnan(data):
            return None
        else:
            return data


    def _csv_to_dataframe(self, filepath: str) -> pd.DataFrame:
        """Reads a CSV file into a pandas dataframe, dropping rows with any NaN values."""
        try:
            dataframe = pd.read_csv(filepath, header=0, keep_default_na=False).dropna(how='any')
            return dataframe
        except FileNotFoundError:
            print("Error: File not found -", filepath)
        except pd.errors.EmptyDataError:
            print("Error: No data - File is empty")
        except Exception as e:
            print("Error:", e)

    
    def _get_dataset_name(self, filepath: str) -> str:
        """Extracts the dataset name from the file path."""
        # return filepath.rsplit('/', 1)[-1][:-4].replace('$', '')
        return Path(filepath).stem.replace('$', '')


    def _get_column_names(self) -> list:
        """
        Extracts the processed column names from the dataframe.
        
        Returns:
            list: List of column names
        """
        self.dataframe.columns = [column.replace(' ', '-').replace('_', '-').replace('$', '') for column in self.dataframe.columns]
        return self.dataframe.columns.tolist()
        

    def parse_input(self, filepath: str) -> None:
        """Parses the input CSV file to extract the dataset name, column names, and column types."""
        try:
            # Convert to Path object and resolve to absolute path
            file_path = Path(filepath).resolve()
            logger.debug(f"Processing file at: {file_path}")
            
            # Read and process the dataframe
            self.dataframe = self._csv_to_dataframe(str(file_path))
            
            # Extract dataset name from path (without extension)
            self.dataset_name = file_path.stem
            logger.debug(f"Dataset name: {self.dataset_name}")
            
            # Process column names and types
            self.column_names = self._get_column_names()
            self.column_types = [
                self._get_column_type(self.dataframe[column_name], column_name) 
                for column_name in self.column_names
            ]
            
            # Generate feature file path
            feature_path = file_path.parent / f"{self.dataset_name}.feature"
            logger.debug(f"Feature file will be generated at: {feature_path}")
            
            # Validate column types
            self._validate_column_types()
            
        except Exception as e:
            logger.error(f"Error in parse_input: {str(e)}")
            raise RuntimeError(f"Failed to parse input file: {str(e)}") from e
    

    def _get_column_type(self, series: pd.Series, column_name: str) -> str:
        """
        Determines the data type of a DataFrame column.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).

        Args:
            series: DataFrame column as pandas Series
            column_name: Name of the column
            
        Returns:
            str: Inferred column type ('float', 'year', 'varchar', 'datetime', or 'date')
        """
        DATE_PATTERN = (
            r'^((((1[6-9]|[2-9]\d)\d{2})(\/|\-)(0?[13578]|1[02])(\/|\-)(0?[1-9]|[12]\d|3[01]))|'
            r'(((1[6-9]|[2-9]\d)\d{2})(\/|\-)(0?[13456789]|1[012])(\/|\-)(0?[1-9]|[12]\d|30))|'
            r'(((1[6-9]|[2-9]\d)\d{2})(\/|\-)0?2(\/|\-)(0?[1-9]|1\d|2[0-8]))|'
            r'(((1[6-9]|[2-9]\d)(0[48]|[2468][048]|[13579][26])|'
            r'((16|[2468][048]|[3579][26])00))-0?2-29-))$'
        )
        
        def clean_column_name(name: str) -> str:
            return name.replace('\'', '').replace('"', '') if name[0] in ('"', "'") else name
        
        def is_year_value(value) -> bool:
            return 1000 < value < 2100
        
        def has_letters(value: str) -> bool:
            pattern = re.compile(r'[A-Za-z]', re.S)
            return bool(re.findall(pattern, str(value)))
        
        def is_date_format(value: str) -> bool:
            return bool(re.search(DATE_PATTERN, str(value)))

        column_type = series.dtype.name
        column_name = clean_column_name(column_name)

        # Handle numeric types
        if column_type.startswith(('int', 'float')):
            for value in series:
                if (not is_year_value(value)) or isinstance(value, float):
                    return 'float'
                else:
                    return 'year'

        # Handle object or boolean types
        if column_type.startswith(('object', 'bool')):
            for value in series:
                if not recommender.is_valid_datetime(value) and (value != 0 or value is False) and (not is_date_format(value) or has_letters(value)):
                    return 'varchar'
                else:
                    if recommender.is_valid_datetime(value):
                        return 'datetime'
                    else:
                        return 'date'


    def _configure_view_manager(self, view_manager: ViewManager) -> ViewManager:
        """
        Configure ViewManager with dataset metadata.

        Args:
            view_manager (ViewManager): The ViewManager instance to configure

        Returns:
            ViewManager: Configured ViewManager with dataset metadata
        """
        def _update_column_metadata(table_view, names: List[str], types: List[str], count: int):
            """Update column names, types and origins in table view."""
            table_view.column_num = count
            table_view.names.extend(names)
            table_view.types.extend(ColumnType.from_string(t) for t in types)
            table_view.origins = list(range(count))
        
        def _update_table_data(table_view, dataframe: pd.DataFrame):
            """Update table data and row count."""
            table_view.tuple_num = len(dataframe)
            table_view.source = dataframe.values.tolist()

        try:
            # Get reference to first table
            table = view_manager.tables[0]
            
            # Configure column metadata
            _update_column_metadata(
                table,
                self.column_names,
                self.column_types, 
                len(self.column_names)
            )
            # Convert date columns to datetime
            for i, col_type in enumerate(table.types):
                if col_type == ColumnType.TEMPORAL: # 'date' type
                    col_name = self.dataframe.columns[i]
                    self._column_to_datetime(col_name, self.column_types[i])

            # Update column names
            renamed_columns = dict(zip(
                self.dataframe.columns,
                self.column_names
            ))
            self.dataframe.rename(columns=renamed_columns, inplace=True)

            # Update table data
            _update_table_data(table, self.dataframe)
            
            # Sync main view manager properties
            view_manager.column_num = table.column_num
            view_manager.tuple_num = table.tuple_num

            return view_manager
        
        except Exception as e:
            raise RuntimeError(f"Failed to configure view manager: {str(e)}") from e


    def _column_to_datetime(self, column_name: str, column_type: str) -> None:
        """Convert to datetime format for the specified column using pandas to_datetime method."""
        table = self.dataframe
        if column_type == 'date':
            table[column_name] = pd.to_datetime(table[column_name]).dt.date
        elif column_type == 'datetime':
            table[column_name] = pd.to_datetime(table[column_name]).dt.to_pydatetime()
        elif column_type == 'year':
            table[column_name] = pd.to_datetime(table[column_name].apply(lambda x: str(x))).dt.date


    def generate_views(self, view_manager: ViewManager) -> ViewManager:
        """
        Generate views for all tables in the ViewManager.
        
        Args:
            view_manager (ViewManager): The ViewManager instance containing tables
            
        Returns:
            ViewManager: Updated ViewManager with generated views
        """
        def _validate_source_table(table):
            if not table.source:
                print("Error: Source table contains no data")
        
        def _process_tables(manager: ViewManager):
            # Get new transformed tables from the initial table and add them to the ViewManager
            new_tables = manager.tables[0].get_transformed_tables()
            manager.add_tables(new_tables)
            
            # Process remaining tables
            for table in manager.tables[1:]:
                table.get_transformed_tables()
            
            if manager.view_num == 0:
                print("Error: No charts could be generated")
        
        try:
            _validate_source_table(view_manager.tables[0])
            _process_tables(view_manager)
            return view_manager
            
        except Exception as e:
            print(f"Unexpected error during view generation: {str(e)}")
            raise RuntimeError("Failed to generate views") from e
 

    def rank(self):
        """Generate and rank charts for the dataset."""
        self.viewManager = ViewManager(self.dataset_name)
        self.viewManager.add_table(Table(self.viewManager, False, '', ''))
        self.viewManager = self._configure_view_manager(self.viewManager)  
        self.viewManager = self.generate_views(self.viewManager)
        self.viewManager.get_score()


    def filter_direct(self, table_name: str) -> None:
        
        HTML_OUTPUT_DIR = 'html'
        
        # Ensure output directory exists
        output_path = os.path.join(os.getcwd(), HTML_OUTPUT_DIR)
        os.makedirs(output_path, exist_ok=True)
        
        self.figures = []
        chart_count = 1

        for view_index in range(len(self.viewManager.views)):
            current_view = self._get_view_for_index(view_index)

            if self._should_skip_view(current_view):
                continue
           
            if not current_view.table.transformed:
                self.visualise_chart(current_view, table_name, chart_count)
                chart_count += 1

        output_file = os.path.join(output_path, f'{table_name}_filter.html')
        self.render_charts(output_file) if chart_count > 1 else self.render_none(output_file)


    def filter_by_chart(self, table_name: str, chart_type: str) -> None:
        
        HTML_OUTPUT_DIR = 'html'
        
        # Ensure output directory exists
        output_path = os.path.join(os.getcwd(), HTML_OUTPUT_DIR)
        os.makedirs(output_path, exist_ok=True)
        
        self.figures = []
        chart_count = 1

        for view_index in range(len(self.viewManager.views)):
            current_view = self._get_view_for_index(view_index)

            if self._should_skip_view(current_view):
                continue
           
            if ChartType.chart[current_view.chart] == chart_type:
                self.visualise_chart(current_view, table_name, chart_count)
                chart_count += 1

        output_file = os.path.join(output_path, f'{table_name}_filter.html')
        self.render_charts(output_file) if chart_count > 1 else self.render_none(output_file)
    

    def render_none(self, output_file: str) -> None:
        """Render an HTML file with a message indicating no charts were generated."""
        html_content = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>No Charts Generated</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            h2 {
                color: #666;
                text-align: center;
            }
        </style>
    </head>
    <body>
        <h2>No charts were generated for the inputs specified.</h2>
    </body>
    </html>"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content.strip())  # Add strip() to remove any extra whitespace
                print(f"Writing content (length: {len(html_content)}) to {output_file}")
        except Exception as e:
            print(f"Error writing to {output_file}: {e}")
            traceback.print_exc()
   

    def render_charts(self, output_file: str) -> None:
        """Render the generated charts to an HTML file using Plotly."""
        try:
            with open(output_file, 'w') as f:
                for idx, fig in enumerate(self.figures):
                    if idx == 0:
                        # only load javascript once
                        f.write(fig.to_html(full_html=False, include_plotlyjs='cdn'))
                    else:
                        f.write(fig.to_html(full_html=False, include_plotlyjs=False))
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()


    def show_filtered_charts(self, table_name: str, filter_column: str) -> None:
        
        HTML_OUTPUT_DIR = 'html'
        
        # Ensure output directory exists
        output_path = os.path.join(os.getcwd(), HTML_OUTPUT_DIR)
        os.makedirs(output_path, exist_ok=True)
        
        self.figures = []
        chart_count = 1

        for view_index in range(len(self.viewManager.views)):
            current_view = self._get_view_for_index(view_index)

            if self._should_skip_view(current_view):
                continue
            
            if filter_column in current_view.fx.name or filter_column in current_view.fy.name:
                self.visualise_chart(current_view, table_name, chart_count)
                chart_count += 1

        output_file = os.path.join(output_path, f'{table_name}_filter.html')
        self.render_charts(output_file) if chart_count > 1 else self.render_none(output_file)
   

    def show_top_ranked_charts(self, table_name: str) -> None:
        """
        Generate and render HTML visualizations for top-ranked charts.
        
        Args:
            table_name (str): Name of the table to generate charts for
        """
        HTML_OUTPUT_DIR = 'html'
        MAX_CHARTS = 20
        
        # Ensure output directory exists
        output_path = os.path.join(os.getcwd(), HTML_OUTPUT_DIR)
        os.makedirs(output_path, exist_ok=True)
        
        self.figures = []
        chart_count = 1
        
        for view_index in range(MAX_CHARTS):
            if view_index >= len(self.viewManager.views):
                print(f"Limited dataset: will only display {view_index} scored charts.")
                break
                
            current_view = self._get_view_for_index(view_index)
            
            if self._should_skip_view(current_view):
                continue
                
            self.visualise_chart(current_view, table_name, chart_count)
            chart_count += 1

        output_file = os.path.join(output_path, f'{table_name}_all.html')
        self.render_charts(output_file) if chart_count > 1 else self.render_none(output_file)


    def _get_view_for_index(self, index: int):
        """Get the view object for a given index from the view manager."""
        view_reference = self.viewManager.views[index]
        return self.viewManager.tables[view_reference.table_pos].views[view_reference.view_pos]


    def _should_skip_view(self, view) -> bool:
        """Determine if a view should be skipped based on y-axis name."""
        name = view.y_name.lower()
        return ("count(date" in name or "count(time" in name)
    

    def _get_chart_heading(self, data: dict) -> str:
        """Generate appropriate subtitle for the chart."""
        if not data['describe']:
            return f"{data['x_name']} against {data['y_name']}"
            
        base_text = (f"{data['x_name']} against {data['y_name']}" 
                    if data['chart'] == 'scatter' 
                    else data['y_name'])
        return f"{base_text} {data['describe'].lower()}"
    

    def visualise_chart(self, view, table_name: str, chart_number: int) -> None:
        """
        Create and add a chart visualization to the page.

        CREDIT: This function adapts the code from 'HAIChart: Human and AI Paired Visualization System' by Xie et al. (VLDB Endowment 2024).
        
        Args:
            view: View object containing chart data
            table_name: Name of the table
            chart_number: Number to identify the chart
        """
        try:
            data = {}
            data['chartname'] = str(chart_number) + "、" + table_name
            data['describe'] = view.table.describe
            data['x_name'] = view.fx.name
            data['y_name'] = view.fy.name
            data['chart'] = ChartType.chart[view.chart]
            data['classify'] = [v[0] for v in view.table.classes]
            data['x_data'] = view.X
            data['y_data'] = view.Y
            data['score'] = view.score
            chart = self._draw_chart(data, view.table.source, self._get_chart_heading(data))
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()  
            sys.exit()

        self.figures.append(chart)


    def _draw_chart(self, data: dict, table_data: list, chart_heading: str) -> go.Figure:
        """
        Draw a chart using Plotly.

        Args:
            data: Chart data
            table_data: Source table
            chart_heading: Chart heading
        
        Returns:
            go.Figure: Plotly figure object
        """
        score = f"Score: {data['score']:.2f}"
        title = chart_heading + "<br><sup>" + score + "</sup>"

        common_layout = go.Layout(
                    title={
                        'text': title,
                        'x': 0.5, 
                        'xanchor': 'center'
                    },
                    xaxis=dict(title=data['x_name']),
                    yaxis=dict(title=data['y_name']),
                    margin=dict(t=100)  # Adjust top margin for title
                )

        # if there are transformations
        if data["classify"]:
            # get base chart
            if data['chart'] == 'bar':
                chart = go.Bar()
                fig = go.Figure(data=[chart], layout=common_layout)

            elif data['chart'] == 'line':
                chart = go.Scatter()
                fig = go.Figure(data=[chart], layout=common_layout)

            elif data['chart'] == 'scatter':
                chart = go.Scatter()
                fig = go.Figure(data=[chart], layout=common_layout)

            else:
                print("Error: invalid chart")
                return None
            
            # add trace to base chart
            for i in range(len(data["classify"])):
                name = data["classify"][i][0] if isinstance(data["classify"][i], tuple) else data["classify"][i]
                
                if data['chart'] == 'bar':
                    fig.add_trace(go.Bar(
                        x=data["x_data"][0],
                        y=data["y_data"][i],
                        name=name
                    ))
                elif data['chart'] == 'line':
                    fig.add_trace(go.Scatter(
                        x=data["x_data"][0],
                        y=data["y_data"][i],
                        mode='lines',
                        name=name
                    ))
                elif data['chart'] == 'scatter':
                    fig.add_trace(go.Scatter(
                        x=data["x_data"][i],
                        y=data["y_data"][i],
                        mode='markers',
                        name=name
                    ))
        # if no transformations
        else:
            if data['chart'] == 'bar':
                chart = go.Bar(
                    x=data["x_data"][0],
                    y=data["y_data"][0],
                    name="",
                    textposition='auto',
                )
                fig = go.Figure(data=[chart], layout=common_layout)

            elif data['chart'] == 'pie':
                chart = go.Pie(
                    labels=data["x_data"][0],
                    values=data["y_data"][0],
                    name="",
                    textinfo='percent',
                    hoverinfo='label+percent',
                )
                layout = go.Layout(
                    title_text=title,
                    margin=dict(t=100)  # Adjust top margin for title
                )
                fig = go.Figure(data=[chart], layout=layout)

            elif data['chart'] == 'line':
                chart = go.Scatter(
                    x=data["x_data"][0],
                    y=data["y_data"][0],
                    mode='lines',
                    name="",
                )
                fig = go.Figure(data=[chart], layout=common_layout)

            elif data['chart'] == 'scatter':
                chart = go.Scatter(
                    x=data["x_data"][0],
                    y=data["y_data"][0],
                    mode='markers',
                    name="",
                )
                fig = go.Figure(data=[chart], layout=common_layout)

            else:
                print("Error: invalid chart")
                return None

        return fig