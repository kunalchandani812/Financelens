"""Finance calculations for FinanceLens (no Streamlit code here, so it is easy to test)."""
import pandas as pd

NUMBERS = ["Revenue", "Operating Profit", "Net Profit", "Total Equity"]


def load_verified(path="data.csv"):
    """FY26 numbers (₹ crore) that were checked by hand, one row per company."""
    return pd.read_csv(path).set_index("Company")


def add_ratios(df):
    """Add the three ratios to a table that has the four NUMBERS columns."""
    df = df.copy()
    df["Operating margin"] = df["Operating Profit"] / df["Revenue"]
    df["Net margin"] = df["Net Profit"] / df["Revenue"]
    df["ROE"] = df["Net Profit"] / df["Total Equity"]
    return df


def pe_ratio(market_cap_cr, net_profit_cr):
    """P/E = market value of the company ÷ its yearly profit (both in ₹ crore)."""
    if not market_cap_cr or not net_profit_cr or net_profit_cr <= 0:
        return None
    return market_cap_cr / net_profit_cr


def pb_ratio(market_cap_cr, equity_cr):
    """P/B = market value of the company ÷ shareholders' equity."""
    if not market_cap_cr or not equity_cr or equity_cr <= 0:
        return None
    return market_cap_cr / equity_cr


# ---------------- Practice portfolio (fake money) ----------------
START_CASH = 1_000_000  # ₹10 lakh of fake money


def new_portfolio():
    return {"cash": float(START_CASH), "holdings": {}, "trades": []}


def buy(p, name, shares, price, note=""):
    """Buy whole shares. Returns None if it worked, or an error message."""
    if shares < 1:
        return "Enter at least 1 share."
    cost = shares * price
    if cost > p["cash"]:
        return "Not enough cash for this order."
    h = p["holdings"].get(name, {"shares": 0, "avg_cost": 0.0})
    total = h["shares"] + shares
    h["avg_cost"] = (h["shares"] * h["avg_cost"] + cost) / total
    h["shares"] = total
    p["holdings"][name] = h
    p["cash"] -= cost
    p["trades"].append({"Action": "BUY", "Company": name, "Shares": shares,
                        "Price": round(price, 2), "Realised P&L": None, "Note": note})
    return None


def sell(p, name, shares, price, note=""):
    """Sell shares you own. Returns None if it worked, or an error message."""
    h = p["holdings"].get(name)
    if shares < 1:
        return "Enter at least 1 share."
    if not h or h["shares"] < shares:
        return "You don't own that many shares."
    pnl = (price - h["avg_cost"]) * shares
    h["shares"] -= shares
    if h["shares"] == 0:
        del p["holdings"][name]
    p["cash"] += shares * price
    p["trades"].append({"Action": "SELL", "Company": name, "Shares": shares,
                        "Price": round(price, 2), "Realised P&L": round(pnl, 2), "Note": note})
    return None


def portfolio_value(p, prices):
    """Cash plus the current value of everything owned."""
    total = p["cash"]
    for name, h in p["holdings"].items():
        total += h["shares"] * (prices.get(name) or h["avg_cost"])
    return total


def holdings_table(p, prices):
    rows = []
    for name, h in p["holdings"].items():
        price = prices.get(name) or h["avg_cost"]
        value = h["shares"] * price
        rows.append({"Company": name, "Shares": h["shares"], "Avg cost": h["avg_cost"],
                     "Price": price, "Value": value,
                     "P&L (₹)": value - h["shares"] * h["avg_cost"],
                     "P&L (%)": (price / h["avg_cost"] - 1) * 100})
    return pd.DataFrame(rows)
