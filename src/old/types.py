class ColumnType(object):
    """Represents the type classification for dataset columns"""
    NONE = 0
    CATEGORICAL = 1
    NUMERICAL = 2
    TEMPORAL = 3

    @staticmethod
    def from_string(type_string: str) -> 'ColumnType':
        """
        Determines column type from a string data type description.

        Args:
            type_string: Data type string (e.g., 'varchar', 'int', 'datetime')

        Returns:
            ColumnType: The corresponding column type classification
        """
        s = type_string.lower()

        # Categorical types
        if s.startswith('varchar') or s.startswith('char'):
            return ColumnType.CATEGORICAL

        # Numerical types
        if s.startswith('int') or s == 'double' or s == 'float':
            return ColumnType.NUMERICAL

        # Temporal types
        if s == 'datetime' or s == 'date' or s == 'year':
            return ColumnType.TEMPORAL

        return ColumnType.NONE
