# AutoChart
AutoChart automatically turns your file into charts, without manually choosing columns, all within your browser.

This means your uploaded csv file never leaves your computer.

AutoChart is a Svelte single-page application using DuckDB-Wasm for the in-browser SQL database and Plotly.js for chart rendering.

## TODO
- add model's ranking of charts

## Known issues
1. certain charts (group_by) show the internal enum representation for categories instead of original varchar
- explicit casting of groupCol::VARCHAR in sql query builder function
- manual mapping from Apache Arrow vectors (const fieldNames = result.schema.fields.map(f => f.name);)

2. certain multi-series charts show stacked (instead of grouped) bar without series legend