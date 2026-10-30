"""FinanceLens - explore Indian companies, understand ratios, see delayed live prices."""
import pandas as pd
import streamlit as st
from calc import (load_data, peer_average, pe_ratio, START_CASH, new_portfolio,
                  buy, sell, portfolio_value, holdings_table)

try:
    import yfinance as yf
except ImportError:  # the app still works (without prices) if yfinance is missing
    yf = None

st.set_page_config(page_title="FinanceLens", page_icon="🔍", layout="wide")
st.markdown(
    "<style>[data-testid='stMetricValue']{font-family:ui-monospace,Menlo,Consolas,monospace}</style>",
    unsafe_allow_html=True,
)

df = load_data()
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


@st.cache_data(ttl=300)  # remember the result for 5 minutes so we don't hit Yahoo on every click
def get_market(ticker):
    """Delayed price history (1 year) and market cap in ₹ crore from Yahoo Finance."""
    if yf is None:
        return None, None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")["Close"].dropna()
        try:
            cap = t.fast_info["marketCap"] / 1e7  # rupees -> crore
        except Exception:
            cap = None
        return (hist if len(hist) > 1 else None), cap
    except Exception:
        return None, None


st.title("Finance🔍Lens")
st.caption("Prices: Yahoo Finance, delayed about 15 minutes, refreshed every 5 minutes. "
           "Financials: FY26 annual results, ₹ crore.")

# ---- Price strip: green/red comes from the day's change ----
cols = st.columns(len(df))
got_any = False
for col, (name, row) in zip(cols, df.iterrows()):
    hist, _ = get_market(row["Ticker"])
    if hist is not None:
        got_any = True
        last, prev = hist.iloc[-1], hist.iloc[-2]
        col.metric(name, f"₹{last:,.2f}", f"{(last / prev - 1) * 100:+.2f}%")
    else:
        col.metric(name, "n/a")
if not got_any:
    st.warning("Live prices could not be loaded right now. Ratios below still work.")

tab1, tab2, tab3, tab4 = st.tabs(["Explore", "Compare", "Learn", "Practice"])

# ---- Explore one company ----
with tab1:
    name = st.selectbox("Choose a company", list(df.index))
    row = df.loc[name]
    hist, cap = get_market(row["Ticker"])
    left, right = st.columns([2, 1])
    with left:
        if hist is not None:
            st.line_chart(hist, height=280, color="#ffb000")
        else:
            st.info("Price chart not available right now.")
    with right:
        pe = pe_ratio(cap, row["Net Profit"])
        st.metric("P/E (market value ÷ yearly profit)", f"{pe:.1f}" if pe else "n/a")
        st.caption(f"Sector: {row['Sector']}")
    st.subheader("Ratios")
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

# ---- Compare several companies ----
with tab2:
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

        def colour(s):  # green = best in the group, red = lowest
            if s.name == "Sector":
                return [""] * len(s)
            return ["color:#00e676;font-weight:700" if v == s.max()
                    else "color:#ff3b4e" if v == s.min() else "" for v in s]

        st.dataframe(sub.style.apply(colour).format({k: "{:.1%}" for k in KEYS}))
        metric = st.selectbox("Chart this ratio", KEYS)
        st.bar_chart(sub[metric] * 100, color="#ffb000")
        st.caption(f"{metric} in %")

# ---- Learn ----
with tab3:
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

# ---- Practice: fake money, real (delayed) prices ----
with tab4:
    st.write(f"Practice investing with ₹{START_CASH:,.0f} of fake money at real, delayed prices. "
             "Nothing here is real money or investment advice.")
    st.caption("NSE trades Monday to Friday, 9:15 to 15:30 IST. Outside those hours the price is the last close. "
               "Your practice account resets if you refresh the page, so download your trades to keep a record.")
    if "pf" not in st.session_state:
        st.session_state.pf = new_portfolio()
    pf = st.session_state.pf
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))

    prices = {}
    for n, r in df.iterrows():
        h, _ = get_market(r["Ticker"])
        prices[n] = float(h.iloc[-1]) if h is not None else None
    value = portfolio_value(pf, prices)
    m1, m2, m3 = st.columns(3)
    m1.metric("Portfolio value", f"₹{value:,.0f}", f"{(value / START_CASH - 1) * 100:+.2f}%")
    m2.metric("Cash", f"₹{pf['cash']:,.0f}")
    m3.metric("Invested", f"₹{value - pf['cash']:,.0f}")

    st.subheader("Place an order")
    a, b = st.columns(2)
    pick = a.selectbox("Company", list(df.index), key="pf_company")
    qty = int(b.number_input("Shares", min_value=1, value=10, step=1))
    price = prices[pick]
    if price is None:
        st.info("Price not available right now, so orders are paused.")
    else:
        r = df.loc[pick]
        st.write(f"Latest delayed price: **₹{price:,.2f}**  ·  Order value: ₹{qty * price:,.0f}")
        st.caption(f"Before you trade: operating margin {r['Operating margin'] * 100:.1f}%, "
                   f"net margin {r['Net margin'] * 100:.1f}%, ROE {r['ROE'] * 100:.1f}%.")
        note = st.text_input("Why this trade? (optional, it helps you learn)")
        bcol, scol, _ = st.columns([1, 1, 4])
        for label, action, col in (("Buy", buy, bcol), ("Sell", sell, scol)):
            if col.button(label, use_container_width=True):
                err = action(pf, pick, qty, price, note)
                if err:
                    st.error(err)
                else:
                    st.session_state.flash = f"{label} order done: {qty} shares of {pick} at ₹{price:,.2f}."
                    st.rerun()

    st.subheader("Your holdings")
    tbl = holdings_table(pf, prices)
    if tbl.empty:
        st.info("You don't own anything yet.")
    else:
        def pl_colour(v):
            return "color:#00e676" if v > 0 else "color:#ff3b4e" if v < 0 else ""
        st.dataframe(tbl.style.map(pl_colour, subset=["P&L (₹)", "P&L (%)"]).format({
            "Shares": "{:,.0f}", "Avg cost": "{:,.2f}", "Price": "{:,.2f}", "Value": "{:,.0f}",
            "P&L (₹)": "{:+,.0f}", "P&L (%)": "{:+.2f}%"}), hide_index=True)

    st.subheader("Trade history")
    if pf["trades"]:
        hist_df = pd.DataFrame(pf["trades"][::-1])
        st.dataframe(hist_df, hide_index=True)
        st.download_button("Download trade history (CSV)", hist_df.to_csv(index=False), "trades.csv")
    else:
        st.caption("No trades yet.")
    if st.button("Reset practice account"):
        st.session_state.pf = new_portfolio()
        st.rerun()

st.divider()
st.caption("Operating profit = each company's reported EBIT. Net profit = profit attributable to "
           "shareholders. ROE uses year-end equity. FinanceLens is an educational project, not "
           "investment advice.")
