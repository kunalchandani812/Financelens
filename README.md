# FinanceLens

A stock market simulator: buy and sell Indian stocks with fake money at real (delayed) prices. Companies are grouped into 8 sectors with 5 companies each. A Research tab compares them by sector and a Learn tab explains each company.

## Run it on your computer
1. Install Python 3.10 or newer.
2. In this folder run: `pip install -r requirements.txt`
3. Then run: `streamlit run app.py`

## Put it online (free)
1. Upload this folder to a GitHub repository.
2. Go to share.streamlit.io, sign in with GitHub, choose the repository and set the main file to `app.py`.

## Review tab
Each trade is compared with the Nifty 50 and its sector peers since the trade, then labelled (good call, market-driven gain, unlucky, bad call) with a plain-English explanation. It is rule-based, not AI.

## Practice tab
Buy and sell with fake money at real, delayed prices. The account lives in the browser session, so it resets when the page is refreshed; use the download button to keep a record. Saving accounts and a leaderboard would need a database and logins (next step).

## Files
- `companies.csv`: all 40 companies by sector (name, Yahoo ticker, description). Used by Trade, Research and Learn. Add a row to add a company.
- `data.csv`: hand-checked FY26 numbers (₹ crore) for six companies. Other companies' numbers are fetched automatically from Yahoo Finance.
- `calc.py`: the ratio calculations.
- `app.py`: the website.
- `.streamlit/config.toml`: the black theme.

## Data notes (check before sharing)
- Prices come from Yahoo Finance through `yfinance` (an unofficial library). They are delayed and can occasionally fail.
- Syrma SGS (electronics manufacturing, not IT services): revenue is revenue from operations; operating profit is about EBITDA 545 minus depreciation, from a data aggregator; net profit is profit attributable to owners (total profit after tax was about 346); equity is attributable to owners (NSE filing). Verify against the company's results.
- Wipro operating profit and equity, and Infosys equity, also need checking against company filings.
- Not investment advice.

## Optional: AI explanations in the Review tab (off by default)
The Review tab works without AI, and AI is currently off: visitors see only the automatic, rule-based review. To switch on the "Explain with AI" button, first add the line `anthropic` to `requirements.txt`, then:
1. Create an account at console.anthropic.com, add a small amount of credit, and set a monthly spending limit.
2. Create an API key.
3. On Streamlit Community Cloud, open your app, then the three dots, Settings, Secrets, and paste:
   `ANTHROPIC_API_KEY = "your-key-here"`
   Optional: `ANTHROPIC_MODEL = "claude-haiku-5-5"` (the default, a low-cost model).
4. Save, and the app restarts.

Never put the key in GitHub or in any file in this folder. For local testing only, put it in `.streamlit/secrets.toml` (already ignored by `.gitignore`).

Limits: 5 explanations per visitor and 100 per day for the whole site (change `MAX_AI_PER_SESSION` and `DAILY_AI_CAP` in `app.py`). The daily counter resets when the app restarts, so the spending limit on your key is the real safety net.
