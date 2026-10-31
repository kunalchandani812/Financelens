"""FinanceLens - a stock market simulator (fake money, real delayed prices) plus sector research."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from calc import (NUMBERS, load_verified, add_ratios, pe_ratio, pb_ratio, START_CASH,
                  new_portfolio, buy, sell, portfolio_value, holdings_table,
                  review_trade, nifty_trend, position_in_range, now_ist, build_ai_prompt)

try:
    import yfinance as yf
except ImportError:  # the app still opens (without prices) if yfinance is missing
    yf = None

st.set_page_config(page_title="FinanceLens", page_icon="🔍", layout="wide")
st.markdown(
    "<style>[data-testid='stMetricValue']{font-family:ui-monospace,Menlo,Consolas,monospace}</style>",
    unsafe_allow_html=True,
)

# ---------------- data ----------------
companies = pd.read_csv("companies.csv")           # Sector, Name, Ticker, About, Watch
verified = load_verified()                         # hand-checked FY26 numbers for six companies
SECTORS = list(dict.fromkeys(companies["Sector"]))
NAME_TO_TICKER = dict(zip(companies["Name"], companies["Ticker"]))
NAME_TO_SECTOR = dict(zip(companies["Name"], companies["Sector"]))
TICKERS = tuple(companies["Ticker"])
QUOTE_TICKERS = TICKERS + ("^NSEI",)               # plus the Nifty 50 index, used to judge trades
FINANCIAL = {"Banking", "Trading (capital markets)"}   # sectors where operating margin makes no sense

RATIOS = {
    "Operating margin": {
        "formula": "Operating profit ÷ Revenue",
        "what": "Out of every ₹100 of sales, how much is left after the costs of running the business, before interest and tax.",
        "read": "Higher is better. It is not used for banks and brokers, because their income and costs are structured differently.",
    },
    "Net margin": {
        "formula": "Net profit ÷ Revenue",
        "what": "Out of every ₹100 of sales (or total income), how much finally becomes profit for shareholders.",
        "read": "Compare it with operating margin. A big gap means tax, interest or one-off items are eating into profit.",
    },
    "ROE": {
        "formula": "Net profit ÷ Total equity",
        "what": "How much profit the company earns for every ₹100 of shareholders' money invested in it.",
        "read": "Higher is better, but a very high ROE can also mean the company pays out most of its cash, keeping equity low.",
    },
}
SECTOR_INFO = {
    "Banking": ("Banks earn the gap between the interest they charge on loans and the interest they pay on deposits, plus fees.",
                "ROE, net interest margin, bad loans (NPAs) and price-to-book (P/B). Operating margin is not meaningful."),
    "IT services": ("They sell software, consulting and outsourcing, mostly to overseas clients and paid in dollars, so the rupee and global tech spending matter.",
                    "Operating margin, revenue growth in constant currency, ROE and free cash flow."),
    "FMCG": ("They sell everyday products such as soap, food and snacks in huge volumes at small margins. Strong brands let them raise prices.",
             "Volume growth, operating margin, raw-material costs and ROE (often very high)."),
    "Pharma": ("They sell medicines in India and abroad. The US generics market is a big profit source, and regulators must approve products and inspect factories.",
               "Operating margin, research spending, US exposure and inspection history."),
    "Automobiles": ("A cyclical business: sales rise and fall with interest rates, fuel prices and consumer confidence, and margins depend on steel and other input costs.",
                    "Volume growth, operating margin and the shift to electric vehicles."),
    "Energy & power": ("Oil, gas and coal producers earn money from commodity prices. Power companies earn regulated returns on their plants and networks.",
                       "Margins, debt levels, dividend payouts and government policy."),
    "Trading (capital markets)": ("Brokers and exchanges earn fees whenever investors trade, so profits rise in busy markets and fall when activity slows.",
                                  "Trading volumes, net margin, ROE and regulatory changes."),
    "Electronics manufacturing": ("These companies build products for other brands under contract. Margins are thin and they need a lot of working capital.",
                                  "Operating margin, order book, customer concentration and working capital."),
}

if "pf" not in st.session_state:
    st.session_state.pf = new_portfolio()


def sector_keys(sector):
    return ["Net margin", "ROE"] if sector in FINANCIAL else list(RATIOS)


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
    """Market value in ₹ crore (used for P/E and P/B)."""
    if yf is None:
        return None
    try:
        return yf.Ticker(ticker).fast_info["marketCap"] / 1e7
    except Exception:
        return None


def latest(frame, labels):
    """First matching row label from a Yahoo statement -> (latest value, its date)."""
    for lab in labels:
        if lab in frame.index:
            v = frame.loc[lab].dropna()
            if len(v):
                return float(v.iloc[0]), v.index[0]
    return None, None


@st.cache_data(ttl=86400)
def fetch_fundamentals(ticker):
    """Latest annual numbers (₹ crore) from Yahoo Finance, or None if they are missing."""
    if yf is None:
        return None
    try:
        t = yf.Ticker(ticker)
        fin, bs = t.financials, t.balance_sheet
        rev, date = latest(fin, ["Total Revenue", "Operating Revenue"])
        op, _ = latest(fin, ["Operating Income", "EBIT"])
        net, _ = latest(fin, ["Net Income Common Stockholders", "Net Income"])
        eq, _ = latest(bs, ["Common Stock Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"])
        if rev is None or net is None or eq is None:
            return None
        c = 1e7  # rupees -> crore
        return {"Revenue": rev / c, "Operating Profit": op / c if op is not None else None,
                "Net Profit": net / c, "Total Equity": eq / c, "Period": str(date)[:10]}
    except Exception:
        return None


def sector_table(sector):
    """Numbers and ratios for the five companies in a sector."""
    rows = {}
    for _, c in companies[companies["Sector"] == sector].iterrows():
        if c["Name"] in verified.index:
            d = {k: float(verified.loc[c["Name"], k]) for k in NUMBERS}
            d.update(Period="FY26 (31 Mar 2026)", Source="Checked against FY26 results")
        else:
            d = fetch_fundamentals(c["Ticker"])
            if d is None:
                continue
            d = dict(d, Source="Yahoo Finance (automatic)")
        rows[c["Name"]] = d
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame.from_dict(rows, orient="index")
    t[NUMBERS] = t[NUMBERS].astype(float)
    return add_ratios(t)


def price_map(quotes):
    return {n: (quotes[t][0] if t in quotes else None) for n, t in NAME_TO_TICKER.items()}


def market_status():
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    is_open = now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) <= (15, 30)
    return is_open, now.strftime("%H:%M IST")


def colour(v):  # green for gains, red for losses (blank if there is no number)
    if pd.isna(v):
        return ""
    return "color:#00e676" if v > 0 else "color:#ff3b4e" if v < 0 else ""


def best_worst(s):  # green = best in the group, red = lowest
    return ["color:#00e676;font-weight:700" if v == s.max()
            else "color:#ff3b4e" if v == s.min() else "" for v in s]


def pct(x):
    return "n/a" if pd.isna(x) else f"{x * 100:.1f}%"


def make_ctx(sector, pick, prices, quotes, price):
    """Snapshot of the market at the moment of a trade, used later to review it."""
    nifty = quotes["^NSEI"][0] if "^NSEI" in quotes else None
    nifty_hist = get_history("^NSEI")
    peers = {n: prices[n] for n in companies.loc[companies["Sector"] == sector, "Name"]
             if prices.get(n) is not None}
    return {"nifty": nifty, "sector": sector, "sector_prices": peers,
            "nifty_trend": nifty_trend(nifty_hist, nifty),
            "pos52": position_in_range(get_history(NAME_TO_TICKER[pick]), price)}


# ---------------- live sections (they refresh themselves every 30 seconds) ----------------
@st.fragment(run_every="30s")
def live_summary():
    p = st.session_state.pf
    prices = price_map(get_quotes(QUOTE_TICKERS))
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
    quotes = get_quotes(QUOTE_TICKERS)
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
    chosen = st.selectbox("Sector", ["All sectors"] + SECTORS, key="watch_sector")
    rows = []
    for _, c in companies.iterrows():
        if chosen != "All sectors" and c["Sector"] != chosen:
            continue
        q = quotes.get(c["Ticker"])
        rows.append({"Sector": c["Sector"], "Stock": c["Name"],
                     "Price": q[0] if q else None,
                     "Change %": (q[0] / q[1] - 1) * 100 if q else None})
    st.dataframe(pd.DataFrame(rows).style.map(colour, subset=["Change %"]).format(
        {"Price": "₹{:,.2f}", "Change %": "{:+.2f}%"}, na_rep="n/a"), hide_index=True)
    st.caption("Prices come from Yahoo Finance, delayed by up to about 15 minutes, and refresh every 30 seconds. "
               "Change % compares with the previous close.")


def order_form():
    quotes = get_quotes(QUOTE_TICKERS)
    prices = price_map(quotes)
    if not any(v is not None for v in prices.values()):
        st.warning("Prices could not be loaded right now, so trading is paused. Try again in a minute.")
        return
    st.subheader("Place an order")
    a, b, c = st.columns(3)
    sector = a.selectbox("Sector", SECTORS, key="pf_sector")
    names = [n for n in companies.loc[companies["Sector"] == sector, "Name"] if prices[n] is not None]
    if not names:
        st.info("No prices for this sector right now. Try another sector.")
        return
    pick = b.selectbox("Stock", names, key="pf_company")
    qty = int(c.number_input("Shares", min_value=1, value=10, step=1))
    price = prices[pick]
    st.write(f"Latest price: **₹{price:,.2f}**  ·  Order value: ₹{qty * price:,.0f}")
    if pick in verified.index:
        r = add_ratios(verified).loc[pick]
        st.caption(f"Before you trade: operating margin {pct(r['Operating margin'])}, "
                   f"net margin {pct(r['Net margin'])}, ROE {pct(r['ROE'])}. More in the Research tab.")
    hist = get_history(NAME_TO_TICKER[pick])
    if hist is not None:
        st.line_chart(hist, height=200, color="#ffb000")
    note = st.text_input("Why this trade? (optional, it helps you learn)")
    bcol, scol, _ = st.columns([1, 1, 4])
    for label, action, col in (("Buy", buy, bcol), ("Sell", sell, scol)):
        if col.button(label, use_container_width=True):
            ctx = make_ctx(sector, pick, prices, quotes, price)
            err = action(st.session_state.pf, pick, qty, price, note, ctx)
            if err:
                st.error(err)
            else:
                st.session_state.flash = f"{label} order done: {qty} shares of {pick} at ₹{price:,.2f}."
                st.rerun()



# ---------------- AI explanation (optional: needs ANTHROPIC_API_KEY in Streamlit secrets) ----------------
MAX_AI_PER_SESSION = 5   # explanations one visitor can request
DAILY_AI_CAP = 100       # explanations the whole site will write per day


def secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


@st.cache_resource
def ai_usage():  # one shared counter for all visitors (resets when the app restarts)
    return {"day": None, "n": 0}


def ai_allowed():
    u, today = ai_usage(), now_ist().date().isoformat()
    if u["day"] != today:
        u["day"], u["n"] = today, 0
    return u["n"] < DAILY_AI_CAP


def ask_ai(trade, review):
    """Ask Claude to explain one trade. Returns text, or None if anything goes wrong."""
    try:
        import anthropic
        system, user = build_ai_prompt(trade, review)
        client = anthropic.Anthropic(api_key=secret("ANTHROPIC_API_KEY"), timeout=30, max_retries=1)
        msg = client.messages.create(model=secret("ANTHROPIC_MODEL", "claude-haiku-5-5"), max_tokens=350,
                                     system=system, messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text").strip() or None
    except Exception:
        return None


def ai_box(i, trade, review):
    store = st.session_state.setdefault("ai_text", {})
    if i in store:
        st.markdown(store[i]["text"])
        st.caption(f"AI explanation written at {store[i]['at']} using the prices at that time.")
        return
    if not secret("ANTHROPIC_API_KEY"):
        return  # AI is switched off: the automatic review above is all visitors see
    if len(store) >= MAX_AI_PER_SESSION:
        st.caption("You have used all your AI explanations for this visit.")
        return
    if st.button("Explain with AI", key=f"ai_btn_{i}"):
        if not ai_allowed():
            st.warning("The site's AI limit for today has been reached. Please try again tomorrow.")
            return
        with st.spinner("Writing the explanation..."):
            text = ask_ai(trade, review)
        if text:
            ai_usage()["n"] += 1
            store[i] = {"text": text, "at": now_ist().strftime("%H:%M")}
            st.markdown(text)
            st.caption(f"AI explanation written at {store[i]['at']} using the prices at that time.")
        else:
            st.error("The AI explanation is not available right now. The automatic review above still applies.")
    else:
        st.caption(f"Optional: a written explanation from AI ({MAX_AI_PER_SESSION - len(store)} left this visit).")


def verdict_colour(v):
    return ("color:#00e676;font-weight:700" if v == "Good call"
            else "color:#ff3b4e;font-weight:700" if v == "Bad call" else "color:#ffb000")


@st.fragment(run_every="30s")
def review_section():
    p = st.session_state.pf
    trades = p["trades"]
    if not trades:
        st.info("Place a trade first. Every trade is reviewed here against the Nifty 50 and its sector.")
        return
    quotes = get_quotes(QUOTE_TICKERS)
    prices = price_map(quotes)
    now_nifty = quotes["^NSEI"][0] if "^NSEI" in quotes else None
    now = now_ist()
    reviews = [review_trade(t, prices, now_nifty, now) for t in trades]

    first = next((t["_ctx"] for t in trades if t.get("_ctx") and t["_ctx"].get("nifty")), None)
    port_ret = portfolio_value(p, prices) / START_CASH - 1
    nifty_ret = now_nifty / first["nifty"] - 1 if first and now_nifty else None
    judged = [r for r in reviews if r["Verdict"] in
              ("Good call", "Bad call", "Market-driven gain", "Unlucky (market moved against it)")]
    good = sum(r["Verdict"] == "Good call" for r in reviews)
    c1, c2, c3 = st.columns(3)
    c1.metric("Your portfolio since the start", f"{port_ret * 100:+.2f}%")
    c2.metric("Nifty 50 since your first trade", f"{nifty_ret * 100:+.2f}%" if nifty_ret is not None else "n/a")
    c3.metric("Good calls", f"{good} of {len(judged)}" if judged else "none judged yet")

    rows = []
    for t, r in zip(trades, reviews):
        rows.append({"Time": t["Time"][11:16], "Action": t["Action"], "Stock": t["Company"],
                     "Trade price": t["Price"], "Price now": prices.get(t["Company"]),
                     "Held": r["Held"], "Stock move %": r["Stock move %"],
                     "Nifty move %": r["Nifty move %"], "Sector move %": r["Sector move %"],
                     "Edge vs Nifty (pts)": r["Edge vs Nifty (pts)"], "Verdict": r["Verdict"]})
    table = pd.DataFrame(rows[::-1])
    moves = ["Stock move %", "Nifty move %", "Sector move %", "Edge vs Nifty (pts)"]
    st.dataframe(table.style.map(verdict_colour, subset=["Verdict"]).map(colour, subset=["Edge vs Nifty (pts)"])
                 .format({"Trade price": "₹{:,.2f}", "Price now": "₹{:,.2f}",
                          **{k: "{:+.2f}" for k in moves}}, na_rep="n/a"), hide_index=True)
    st.caption("Edge vs Nifty = how much better (+) or worse (-) your decision did than the index. "
               "For a sale, a fall after you sold counts as a good result.")

    st.subheader("Why each trade got its verdict")
    for i, (t, r) in reversed(list(enumerate(zip(trades, reviews)))):
        with st.expander(f"{t['Time'][11:16]} · {t['Action']} {t['Company']}"):
            st.write(f"**Verdict: {r['Verdict']}**")
            st.write(r["Explanation"])
            st.write(f"**Lesson:** {r['Lesson']}")
            ai_box(i, t, r)
    st.caption("This is an automatic review using price data, not news, and short holding periods are mostly noise. "
               "A good result does not prove a good decision. Educational only, not investment advice.")


# ---------------- page ----------------
st.title("Finance🔍Lens")
st.caption(f"Practice investing with ₹{START_CASH:,.0f} of fake money at real stock prices. "
           "Educational only, not investment advice.")

tab1, tab_review, tab2, tab3 = st.tabs(["Trade", "Review", "Research", "Learn"])

with tab1:
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    live_summary()
    order_form()
    live_tables()
    st.subheader("Trade history")
    trades = st.session_state.pf["trades"]
    if trades:
        hist_df = pd.DataFrame(trades[::-1]).drop(columns=["_ctx"], errors="ignore")
        st.dataframe(hist_df, hide_index=True)
        st.download_button("Download trade history (CSV)", hist_df.to_csv(index=False), "trades.csv")
    else:
        st.caption("No trades yet.")
    st.caption("Your practice account resets if you refresh the page, so download your trades to keep a record.")
    if st.button("Reset practice account"):
        st.session_state.pf = new_portfolio()
        st.rerun()

with tab_review:
    review_section()

with tab2:
    sector = st.selectbox("Sector", SECTORS, key="rs_sector")
    keys = sector_keys(sector)
    with st.spinner("Loading company financials..."):
        tbl = sector_table(sector)
    if tbl.empty:
        st.warning("Financial data could not be loaded for this sector right now. Try again in a minute.")
    else:
        st.subheader(f"{sector}: how the companies compare")
        st.dataframe(tbl[keys + ["Period", "Source"]].style.apply(best_worst, subset=keys)
                     .format({k: "{:.1%}" for k in keys}, na_rep="n/a"))
        if sector in FINANCIAL:
            st.caption("Operating margin is left out for this sector, because it is not meaningful here.")
        metric = st.selectbox("Chart this ratio", keys)
        st.bar_chart(tbl[metric] * 100, color="#ffb000")
        st.caption(f"{metric} in %. Green = best in the sector, red = lowest.")

        st.subheader("Look closer at one company")
        name = st.selectbox("Company", list(tbl.index))
        row = tbl.loc[name]
        ticker = NAME_TO_TICKER[name]
        left, right = st.columns([2, 1])
        with left:
            hist = get_history(ticker)
            if hist is not None:
                st.line_chart(hist, height=260, color="#ffb000")
            else:
                st.info("Price chart not available right now.")
        with right:
            cap = get_market_cap(ticker)
            pe, pb = pe_ratio(cap, row["Net Profit"]), pb_ratio(cap, row["Total Equity"])
            st.metric("P/E (market value ÷ yearly profit)", f"{pe:.1f}" if pe else "n/a")
            st.metric("P/B (market value ÷ equity)", f"{pb:.1f}" if pb else "n/a")
        for col, key in zip(st.columns(len(keys)), keys):
            avg = tbl[key].mean()
            delta = None if pd.isna(row[key]) or pd.isna(avg) else f"{(row[key] - avg) * 100:+.1f} pts vs sector average"
            col.metric(key, pct(row[key]), delta)
            col.caption(RATIOS[key]["formula"])
        st.write("**Reported numbers (₹ crore)**")
        st.dataframe(row[NUMBERS].astype(float).to_frame("₹ crore")
                     .style.format("{:,.0f}", na_rep="n/a"))
        st.caption(f"Period: {row['Period']}. Source: {row['Source']}.")
    st.caption("Numbers marked 'Yahoo Finance (automatic)' are fetched live and can be missing or defined "
               "differently from the company's own report. Check them before relying on them.")

with tab3:
    st.subheader("Learn about a sector and its companies")
    l1, l2 = st.columns(2)
    sec = l1.selectbox("Sector", SECTORS, key="ln_sector")
    names = list(companies.loc[companies["Sector"] == sec, "Name"])
    who = l2.selectbox("Company", names, key="ln_company")
    how, watch = SECTOR_INFO[sec]
    st.markdown(f"**How the {sec} sector makes money.** {how}")
    st.markdown(f"**What to look at.** {watch}")
    c = companies[companies["Name"] == who].iloc[0]
    st.markdown(f"### {who}")
    st.write(c["About"])
    st.write(f"**What to watch:** {c['Watch']}")
    st.caption(f"Yahoo ticker: {c['Ticker']}. Descriptions are general summaries, not investment advice.")

    st.subheader("How the simulator works")
    st.write("You start with fake cash and buy or sell whole shares at the latest price. "
             "Prices are real, so your profit or loss follows what the market actually does. "
             "Your holdings and total return update every 30 seconds.")
    st.write("The Review tab compares each trade with the Nifty 50 and the other companies in its sector, "
             "and labels it as a good call, a market-driven gain, bad luck or a bad call. "
             + ("An optional AI explanation can describe the result in more detail, using only the price data."
                if secret("ANTHROPIC_API_KEY") else ""))
    st.subheader("Key ratios")
    for key in RATIOS:
        with st.expander(key):
            st.code(RATIOS[key]["formula"], language=None)
            st.write(RATIOS[key]["what"])
            st.write(RATIOS[key]["read"])
    with st.expander("P/E ratio"):
        st.code("Market value ÷ Net profit", language=None)
        st.write("How many years of the company's current profit you pay for at today's price. "
                 "A high P/E means investors expect strong growth, or the stock is expensive.")
    with st.expander("P/B ratio"):
        st.code("Market value ÷ Shareholders' equity", language=None)
        st.write("Compares the price with the company's book value. It is especially common for banks.")
