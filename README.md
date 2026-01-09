## TODO
- add aggregate: MEDIAN(), MIN, MAX, STDDEV, VARIANCE (maybe in box plot?)
- add group by month, quarter, year for time-series (but still linear)
- add MoM, QoQ or YoY change transformation
- 7-day moving average (window function using over):
SELECT 
    date, 
    sales, 
    AVG(sales) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as moving_avg
FROM sales_table;

- not sure why COUNT(date), when date for other charts is binned correctly. see avocado
- no pie chart if categories > x
- cache chart html
- add model's ranking of charts
- show category name, not internal int id
- add user's ability to select the charts they want and export 
- add user's ability to edit charts
