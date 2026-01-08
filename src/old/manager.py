import time
import subprocess
from typing import List
from dataclasses import dataclass
from pathlib import Path
from .table import Table

@dataclass
class ViewPosition:
    """Represents the position of a view in the table hierarchy"""
    table_pos: int
    view_pos: int


class ViewManager(object):
    """Manages tables and views for visualization ranking"""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.column_num: int = 0
        self.tuple_num: int = 0 # number of rows or number of columns after transformation
        self.table_num: int = 0
        self.view_num: int = 0
        self.tables: List[Table] = []
        self.views: List[ViewPosition] = []


    def add_table(self, table: Table) -> None:
        """Add a single table"""
        self.tables.append(table)
        self.table_num += 1


    def add_tables(self, tables: List) -> None:
        """Add multiple tables"""
        for table in tables:
            self.add_table(table)


    def _write_feature_to_file(self, feature_path: Path) -> None:
        """
        Write features to file.
        """
        self.views.extend(
            ViewPosition(table_pos, view_pos) 
            for table_pos in range(self.table_num)
            for view_pos in range(self.tables[table_pos].view_num)
        )

        with open(feature_path, 'w') as f:
            for view_pos in self.views:
                view = self.tables[view_pos.table_pos].views[view_pos.view_pos]
                f.write(f"{view.get_features()}\n")
    

    def _run_ranking_model(self, paths: dict) -> None:
        """Execute command to run model."""
        cmd = [
            'java', '-jar', str(paths['ranklib']),
            '-load', str(paths['model']),
            '-rank', str(paths['features']),
            '-score', str(paths['scores'])
        ]
        
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Ranking model execution failed: {e}")


    def _assign_scores(self, score_path: Path) -> None:
        """Read scores and assign to views"""
        if not score_path.exists():
            raise FileNotFoundError(f"Score file not found: {score_path}")
            
        with open(score_path) as f:
            for i, line in enumerate(f):
                view_pos = self.views[i]
                score = float(line.strip().split()[-1])
                self.tables[view_pos.table_pos].views[view_pos.view_pos].score = score


    def get_score(self) -> None:
        """
        Use LambdaMART model and RankLib to score views.

        The saved model (jars/rank.model) is trained by Xie et al., the authors of 'HAIChart: Human and AI Paired Visualization System' (VLDB Endowment 2024) on a private dataset 
        annotated by real users with 285k scored visualizations from 42 different domains. 14 core features are extracted to train the model.

        The model is trained using the LambdaMART algorithm to map relationships between features and scores using decision trees.
        (see: https://github.com/codelibs/ranklib/blob/master/src/main/java/ciir/umass/edu/learning/tree/LambdaMART.java)
        
        The RankLib library from the Lemur Project (see: https://sourceforge.net/p/lemur/wiki/RankLib/) is used.

        Scores are assigned to views and sorted in descending order.

        """
        # Setup paths
        base_path = Path.cwd()
        paths = {
            'ranklib': base_path / 'tools/jars/RankLib.jar',
            'model': base_path / 'tools/jars/rank.model',
            'features': base_path / f'data/{self.table_name}.feature',
            'scores': base_path / f'data/{self.table_name}.score'
        }

        try:
            # Generate feature file
            self._write_feature_to_file(paths['features'])

            # Run ranking model
            self._run_ranking_model(paths)

            # Wait for score file with timeout
            timeout = time.time() + 60
            while not paths['scores'].exists() and time.time() < timeout:
                time.sleep(0.1)

            # Assign scores to views
            self._assign_scores(paths['scores'])

            # Sort views by score in descending order
            self.views.sort(
                key=lambda v: self.tables[v.table_pos].views[v.view_pos].score,
                reverse=True
            )

        except Exception as e:
            print(f"Error during scoring: {e}")
            raise

