# Stock Portfolio Performance Tracker

A local Python 3 web app for tracking stock holdings and performance. It uses
only the Python standard library; no package installation is required.

## Start the application

Open a terminal in this folder and run:

```powershell
python server.py
```

Then open <http://127.0.0.1:8000> in your browser. Use **Add holding** to enter
a ticker, shares, and buy price. Holdings are saved locally in
`portfolio_positions.csv`; repeated additions to a ticker are combined using
their weighted-average buy price. Remove a position with the × button.

The app loads current quotes when it opens and whenever **Refresh** is clicked.
Each successful refresh appends one timestamped row per holding to
`portfolio_summary.csv`. If a quote cannot be retrieved, the app displays an
error instead of writing an incomplete snapshot. Use Ctrl+C in the terminal to
stop the server.

## Files

- `server.py` — local web server and JSON API.
- `static/index.html`, `static/styles.css`, `static/app.js` — responsive
  portfolio dashboard.
- `portfolio.py` — portfolio calculations, quote lookup, and CSV persistence.
- `portfolio_positions.csv` — created when the first holding is saved.
- `portfolio_summary.csv` — performance history, initialized with headers.
- `constituents.csv` — S&P 500 reference data used for company names when a
  ticker matches.

## Market data

The app fetches quotes from Yahoo Finance's chart endpoint and requires an
internet connection. Quote availability and delay depend on the provider and
market; prices are not guaranteed to be streaming real-time quotes.

The bundled S&P 500 ticker list is from
<https://github.com/datasets/s-and-p-500-companies/blob/master/data/constituents.csv>.

## Tests

```powershell
python -m unittest -v
```
