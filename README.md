# FinanceLens

A stock market simulator: buy and sell Indian stocks with fake money at real (delayed) prices. A Research tab explains ratios for six companies.

## Run it on your computer
1. Install Python 3.10 or newer.
2. In this folder run: `pip install -r requirements.txt`
3. Then run: `streamlit run app.py`

## Put it online (free)
1. Upload this folder to a GitHub repository.
2. Go to share.streamlit.io, sign in with GitHub, choose the repository and set the main file to `app.py`.

## Practice tab
Buy and sell with fake money at real, delayed prices. The account lives in the browser session, so it resets when the page is refreshed; use the download button to keep a record. Saving accounts and a leaderboard would need a database and logins (next step).

## Files
- `stocks.csv`: every stock you can trade (name and Yahoo ticker). Add a row to add a stock.
- `data.csv`: FY26 company numbers (₹ crore) for the Research tab.
- `calc.py`: the ratio calculations.
- `app.py`: the website.
- `.streamlit/config.toml`: the black theme.

## Data notes (check before sharing)
- Prices come from Yahoo Finance through `yfinance` (an unofficial library). They are delayed and can occasionally fail.
- Syrma SGS (electronics manufacturing, not IT services): revenue is revenue from operations; operating profit is about EBITDA 545 minus depreciation, from a data aggregator; net profit is profit attributable to owners (total profit after tax was about 346); equity is attributable to owners (NSE filing). Verify against the company's results.
- Wipro operating profit and equity, and Infosys equity, also need checking against company filings.
- Not investment advice.
