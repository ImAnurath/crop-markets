# Hazelnut Market Data

A data platform for the Turkish hazelnut market: daily prices, exchange rates, weather in the
growing regions, and production and export figures, collected into one warehouse and turned
into analysis, a dashboard, a weekly Excel summary, and a price forecast.

Turkey grows roughly two thirds of the world's hazelnuts, and Ordu is the centre of it.
Traders, cooperatives and exporters make pricing and stocking decisions on exactly this data,
mostly from memory and WhatsApp groups.

## Status

Raw data is collected and explored (`notebooks/01_first_look.py`). The price forecasting
comparison is done: see [reports/forecast_results.md](reports/forecast_results.md).

## Planned parts

| Part      | What it does                                                              |
|-----------|---------------------------------------------------------------------------|
| Ingestion | Scheduled Python jobs pulling prices, exchange rates, weather, production |
| Warehouse | PostgreSQL with raw, cleaned and reporting layers                         |
| Analysis  | Notebooks answering real questions about price movements                  |
| Dashboard | Power BI report on price trends, regions and export destinations          |
| Excel     | Automated weekly summary workbook                                         |
| ML        | Price forecast with a baseline comparison and backtest: [results](reports/forecast_results.md) |
