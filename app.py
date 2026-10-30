"""FinanceLens - a stock market simulator (fake money, real delayed prices) plus company research."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from calc import (load_data, peer_average, pe_ratio, START_CASH, new_portfolio,
                  buy, sell, portfolio_value, holdings_table)

try:
    import yfinance as yf
except ImportError:  # the app still opens (without prices) if yfinance is missing
    yf = None

st.set_page_config(page_title="FinanceLens", page_icon="🔍", layout="wide")
st.markdown(
    "<style>[data-testid='stMetricValue']{font-family:ui-monospace,Menlo,Consolas,monospace}</style>",
    unsafe_allow_html=True,
)

df = load_data()                      # ratios for the six researched companies
stocks = pd.read_csv("stocks.csv")    # every stock you can trade
NAME_TO_TICKER = dict(zip(stocks["Name"], stocks["Ticker"]))
TICKERS = tuple(stocks["Ticker"])
RATIOS = {
    "Operating margin": {
        "formula": "Operating profit ÷ Revenue",
        "what": "Out of every ₹100 of sales, how much is left after the costs of running the business, before interest and tax.",
        "read": "Higher is better. In IT services, above 20% is strong. Electronics manufacturers usually earn far less.",
    },
    "Net margin": {
        "formula": "Net profit ÷ Revenue",
        "what": "Out of every ₹100 of sales, how much finally becomes profit for shareholders.",
        "read": "Compare it with operating margin. A big gap means tax, interest or one-off items are eating into profit.",
    },
    "ROE": {
        "formula": "Net profit ÷ Total equity",
        "what": "How much profit the company earns for every ₹100 of shareholders' money invested in it.",
        "read": "Higher is better, but a very high ROE can also mean the company pays out most of its cash, keeping equity low.",
    },
}
KEYS = list(RATIOS)

if "pf" not in st.session_state:
    st.session_state.pf = new_portfolio()


# ---------------- data helpers ----------------
@st.cache_data(ttl=30)  # prices are reused for 30 seconds so we don't hit Yahoo too often
def get_quotes(tickers):
    """{ticker: (latest price, previous close)} for all stocks in one request."""
    if yf is None:
        return {}
    try:
        close = yf.download(list(tickers), period="5d", interval="1d",
                            progress=False, threads=True)["Close"].ffill()
        out = {}
        for t in tickers:
            s = close[t].dropna()
            if len(s) >= 2:
                out[t] = (float(s.iloc[-1]), float(s.iloc[-2]))
        return out
    except Exception:
        return {}


@st.cache_data(ttl=300)
def get_history(ticker):
    """One year of daily closing prices for a chart."""
    if yf is None:
        return None
    try:
        h = yf.Ticker(ticker).history(period="1y")["Close"].dropna()
        return h if len(h) > 1 else None
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_market_cap(ticker):
    """Market value in ₹ crore (used for P/E)."""
    if yf is None:
        return None
    try:
        return yf.Ticker(ticker).fast_info["marketCap"] / 1e7
    except Exception:
        return None


def price_map(quotes):
    return {n: (quotes[t][0] if t in quotes else None) for n, t in NAME_TO_TICKER.items()}


def market_status():
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    is_open = now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30)
    return is_open, now.strftime("%H:%M IST")


def colour(v):  # green for gains, red for losses
    return "color:#00e676" if v > 0 else "color:#ff3b4e" if v < 0 else ""


# ---------------- live sections (they refresh themselves every 30 seconds) ----------------
@st.fragment(run_every="30s")
def live_summary():
    p = st.session_state.pf
    prices = price_map(get_quotes(TICKERS))
    value = portfolio_value(p, prices)
    is_open, t = market_status()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Portfolio value", f"₹{value:,.0f}", f"{(value / START_CASH - 1) * 100:+.2f}%")
    m2.metric("Cash", f"₹{p['cash']:,.0f}")
    m3.metric("Invested", f"₹{value - p['cash']:,.0f}")
    m4.metric("NSE market", "Open" if is_open else "Closed", f"updated {t}", delta_color="off")


@st.fragment(run_every="30s")
def live_tables():
    p = st.session_state.pf
    quotes = get_quotes(TICKERS)
    prices = price_map(quotes)

    st.subheader("Your holdings")
    tbl = holdings_table(p, prices)
    if tbl.empty:
        st.info("You don't own anything yet. Place your first order above.")
    else:
        st.dataframe(tbl.style.map(colour, subset=["P&L (₹)", "P&L (%)"]).format({
            "Shares": "{:,.0f}", "Avg cost": "{:,.2f}", "Price": "{:,.2f}", "Value": "{:,.0f}",
            "P&L (₹)": "{:+,.0f}", "P&L (%)": "{:+.2f}%"}), hide_index=True)

    st.subheader("Market watch")
    rows = []
    for n, t in NAME_TO_TICKER.items():
        if t in quotes:
            last, prev = quotes[t]
            rows.append({"Stock": n, "Price": last, "Change %": (last / prev - 1) * 100})
        else:
            rows.append({"Stock": n, "Price": None, "Change %": None})
    st.dataframe(pd.DataFrame(rows).style.map(colour, subset=["Change %"]).format(
        {"Price": "₹{:,.2f}", "Change %": "{:+.2f}%"}, na_rep="n/a"), hide_index=True)
    st.caption("Prices come from Yahoo Finance, delayed by up to about 15 minutes, and refresh every 30 seconds. "
               "Change % compares with the previous close.")


def order_form():
    quotes = get_quotes(TICKERS)
    prices = price_map(quotes)
    available = [n for n in NAME_TO_TICKER if prices[n] is not None]
    if not available:
        st.warning("Prices could not be loaded right now, so trading is paused. Try again in a minute.")
        return
    st.subheader("Place an order")
    a, b = st.columns(2)
    pick = a.selectbox("Stock", available, key="pf_company")
    qty = int(b.number_input("Shares", min_value=1, value=10, step=1))
    price = prices[pick]
    st.write(f"Latest price: **₹{price:,.2f}**  ·  Order value: ₹{qty * price:,.0f}")
    if pick in df.index:
        r = df.loc[pick]
        st.caption(f"Before you trade: operating margin {r['Operating margin'] * 100:.1f}%, "
                   f"net margin {r['Net margin'] * 100:.1f}%, ROE {r['ROE'] * 100:.1f}%.")
    hist = get_history(NAME_TO_TICKER[pick])
    if hist is not None:
        st.line_chart(hist, height=200, color="#ffb000")
    note = st.text_input("Why this trade? (optional, it helps you learn)")
    bcol, scol, _ = st.columns([1, 1, 4])
    for label, action, col in (("Buy", buy, bcol), ("Sell", sell, scol)):
        if col.button(label, use_container_width=True):
            err = action(st.session_state.pf, pick, qty, price, note)
            if err:
                st.error(err)
            else:
                st.session_state.flash = f"{label} order done: {qty} shares of {pick} at ₹{price:,.2f}."
                st.rerun()


# ---------------- page ----------------
st.title("Finance🔍Lens")
st.caption(f"Practice investing with ₹{START_CASH:,.0f} of fake money at real stock prices. "
           "Educational only, not investment advice.")

tab1, tab2, tab3 = st.tabs(["Trade", "Research", "Learn"])

with tab1:
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    live_summary()
    order_form()
    live_tables()
    st.subheader("Trade history")
    trades = st.session_state.pf["trades"]
    if trades:
        hist_df = pd.DataFrame(trades[::-1])
        st.dataframe(hist_df, hide_index=True)
        st.download_button("Download trade history (CSV)", hist_df.to_csv(index=False), "trades.csv")
    else:
        st.caption("No trades yet.")
    st.caption("Your practice account resets if you refresh the page, so download your trades to keep a record.")
    if st.button("Reset practice account"):
        st.session_state.pf = new_portfolio()
        st.rerun()

with tab2:
    t_explore, t_compare = st.tabs(["Explore a company", "Compare companies"])
    with t_explore:
        name = st.selectbox("Choose a company", list(df.index))
        row = df.loc[name]
        ticker = NAME_TO_TICKER[name]
        left, right = st.columns([2, 1])
        with left:
            hist = get_history(ticker)
            if hist is not None:
                st.line_chart(hist, height=280, color="#ffb000")
            else:
                st.info("Price chart not available right now.")
        with right:
            pe = pe_ratio(get_market_cap(ticker), row["Net Profit"])
            st.metric("P/E (market value ÷ yearly profit)", f"{pe:.1f}" if pe else "n/a")
            st.caption(f"Sector: {row['Sector']}")
        st.subheader("Ratios (FY26)")
        for col, key in zip(st.columns(3), KEYS):
            avg, label = peer_average(df, name, key)
            col.metric(key, f"{row[key] * 100:.1f}%", f"{(row[key] - avg) * 100:+.1f} pts vs {label}")
            col.caption(RATIOS[key]["formula"])
        for key in KEYS:
            with st.expander(f"What is {key}?"):
                st.write(RATIOS[key]["what"])
                st.write(RATIOS[key]["read"])
        st.subheader("Reported numbers (₹ crore, FY26)")
        st.dataframe(row[["Revenue", "Operating Profit", "Net Profit", "Total Equity"]]
                     .astype(float).to_frame("₹ crore").style.format("{:,.0f}"))
    with t_compare:
        picks = st.multiselect("Companies to compare", list(df.index),
                               default=["TCS", "Infosys", "Syrma SGS"])
        if len(picks) < 2:
            st.info("Pick at least two companies.")
        else:
            sub = df.loc[picks, ["Sector"] + KEYS]
            if sub["Sector"].nunique() > 1:
                st.warning("These companies are in different sectors. Syrma SGS makes electronics "
                           "(a thin-margin business), so its margins are not directly comparable "
                           "with IT services companies.")

            def best_worst(s):  # green = best in the group, red = lowest
                if s.name == "Sector":
                    return [""] * len(s)
                return ["color:#00e676;font-weight:700" if v == s.max()
                        else "color:#ff3b4e" if v == s.min() else "" for v in s]

            st.dataframe(sub.style.apply(best_worst).format({k: "{:.1%}" for k in KEYS}))
            metric = st.selectbox("Chart this ratio", KEYS)
            st.bar_chart(sub[metric] * 100, color="#ffb000")
            st.caption(f"{metric} in %")
    st.caption("Ratios are available for the six companies with FY26 data. Operating profit = reported EBIT; "
               "net profit = profit attributable to shareholders; ROE uses year-end equity.")

with tab3:
    st.subheader("How the simulator works")
    st.write("You start with fake cash and buy or sell whole shares at the latest price. "
             "Prices are real, so your profit or loss follows what the market actually does. "
             "Your holdings and total return update every 30 seconds.")
    for key in KEYS:
        st.subheader(key)
        st.code(RATIOS[key]["formula"], language=None)
        st.write(RATIOS[key]["what"])
        st.write(RATIOS[key]["read"])
    st.subheader("P/E ratio")
    st.code("Market value (price × shares) ÷ Net profit", language=None)
    st.write("How many years of the company's current profit you pay for at today's price. "
             "A high P/E means investors expect strong growth, or the stock is expensive.")
    st.subheader("Why no debt ratio?")
    st.write("Most large IT companies hold little debt and plenty of cash, so debt-to-equity "
             "says little about them.")
