from dataclasses import dataclass, field
from typing import List, Any, Tuple
from .types import ColumnType

@dataclass
class Features:
    """Store the attributes of a column in the dataset.
    
    Args:
        name: The name of the corresponding column
        type: The type of the corresponding column 
        origin: The column where the data is from
        
    Attributes:
        min: Minimum value in column
        max: Maximum value in column
        distinct: Number of distinct values
        ratio: Ratio of distinct values to total number of rows
        bin_num: Number of bins for binned data
        interval: Type of interval for temporal data
        distinct_values: List of distinct values and their counts
        interval_bins: Bins for interval data
    """
    name: str
    type: ColumnType  
    origin: Any
    min: Any = 0
    max: Any = 0
    distinct: int = 0
    ratio: float = 0.0
    bin_num: int = 0
    interval: str = ''
    distinct_values: List[Tuple[Any, int]] = field(default_factory=list)
    interval_bins: List[Any] = field(default_factory=list)
