# AutoChart
AutoChart automatically turns your file into charts, without manually choosing columns, all within your browser.

This means your uploaded csv file never leaves your computer.

AutoChart is a Svelte single-page application using DuckDB-Wasm for the in-browser SQL database and Plotly.js for chart rendering.


## Known issues
- add filter to remove chart if data has null
- add model's ranking of charts
- show category name, not internal int id
- certain multi-series charts show stacked (instead of grouped) bar without series legend