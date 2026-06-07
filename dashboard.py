from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# ── CONSTANTS ──────────────────────────────────────────────────────────────────
DATA_DIR = Path("data")
TRADES_FILE = DATA_DIR / "paper_trades.csv"
INITIAL_BANKROLL = 10_000.0

TRADE_COLS = [
    "logged_at", "market_id", "title", "category", "side",
    "entry_prob", "model_prob", "edge", "stake",
    "kelly_fraction_used", "outcome", "pnl",
    "settled", "settled_at", "notes",
]

# ── DATA STRUCTURES ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Market:
    market_id: str
    title: str
    category: str
    implied_probability: float
    model_probability: float
    liquidity: float
    volume_24h: float
    spread: float
    cluster_id: int

    @property
    def edge(self) -> float:
        return self.model_probability - self.implied_probability


# ── PERSISTENCE ────────────────────────────────────────────────────────────────
def ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def load_trade_history() -> pd.DataFrame:
    if TRADES_FILE.exists():
        df = pd.read_csv(TRADES_FILE)
        if "settled" in df.columns:
            df["settled"] = df["settled"].astype(bool)
        return df
    return pd.DataFrame(columns=TRADE_COLS)


def save_trade_history(history: pd.DataFrame) -> None:
    ensure_data_dir()
    history.to_csv(TRADES_FILE, index=False)


# ── SYNTHETIC MARKET SCANNER ───────────────────────────────────────────────────
def scan_markets(limit: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    categories = np.array(["politics", "sports", "economics", "weather", "crypto", "culture"])
    rows = []

    for i in range(limit):
        implied = float(np.clip(rng.beta(2.5, 2.5), 0.02, 0.98))
        model_noise = rng.normal(0.035, 0.07)
        model = float(np.clip(implied + model_noise, 0.01, 0.99))
        liquidity = float(rng.lognormal(mean=11.0, sigma=0.65))
        volume = float(liquidity * rng.uniform(0.08, 0.55))
        spread = float(np.clip(rng.normal(0.025, 0.012), 0.005, 0.08))
        category = str(rng.choice(categories))
        edge = model - implied

        block_reasons = []
        if abs(edge) < 0.03:
            block_reasons.append("edge below threshold")
        if liquidity < 25_000:
            block_reasons.append("liquidity below floor")
        if spread > 0.05:
            block_reasons.append("spread too wide")

        rows.append(
            {
                "market_id": f"MKT-{seed}-{i:04d}",
                "title": f"{category.title()} probability contract #{i + 1}",
                "category": category,
                "implied_probability": implied,
                "model_probability": model,
                "edge": edge,
                "liquidity": liquidity,
                "volume_24h": volume,
                "spread": spread,
                "cluster_id": i // 8,
                "passed_filters": not block_reasons,
                "block_reason": "; ".join(block_reasons) if block_reasons else "PASS",
            }
        )

    return pd.DataFrame(rows).sort_values("edge", ascending=False)


# ── RISK ENGINE ────────────────────────────────────────────────────────────────
def fractional_kelly_fraction(
    market_price: float,
    model_prob: float,
    kelly_fraction: float,
    max_risk_per_trade: float,
    min_edge_threshold: float,
) -> float:
    edge = model_prob - market_price
    if edge <= min_edge_threshold:
        return 0.0
    # YES binary: payout ratio b = (1 − price) / price
    b = (1.0 - market_price) / market_price
    p = model_prob
    q = 1.0 - p
    full_kelly = max(0.0, (b * p - q) / b)
    return float(np.clip(kelly_fraction * full_kelly, 0.0, max_risk_per_trade))


def recommended_stake(bankroll: float, market_price: float, model_prob: float,
                      kelly_fraction: float, max_risk_per_trade: float,
                      min_edge_threshold: float) -> float:
    frac = fractional_kelly_fraction(market_price, model_prob, kelly_fraction,
                                     max_risk_per_trade, min_edge_threshold)
    return round(bankroll * frac, 2)


def check_guardrails(bankroll: float, stake: float,
                     trades_df: pd.DataFrame) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    blocked = False

    # Hard cap: 5% per trade
    cap = bankroll * 0.05
    if stake > cap:
        msgs.append(f"🚫 Stake ${stake:.2f} exceeds 5% hard cap (${cap:.2f})")
        blocked = True

    if not trades_df.empty and "settled" in trades_df.columns:
        settled = trades_df[trades_df["settled"] == True]

        # 3-loss streak
        if len(settled) >= 3:
            last3 = settled.tail(3)["outcome"].tolist()
            if all(o == "loss" for o in last3):
                msgs.append("⚠️ 3-loss streak — reduce size 50% until session recovers")

        # Daily drawdown
        if "pnl" in settled.columns and "logged_at" in settled.columns:
            today = dt.date.today().isoformat()
            today_pnl = settled[settled["settled_at"].astype(str).str.startswith(today)]["pnl"].sum()
            if today_pnl < -(bankroll * 0.05):
                msgs.append(f"🚫 Daily loss limit hit: ${today_pnl:.2f} (limit: -${bankroll*0.05:.2f})")
                blocked = True

    if not msgs:
        msgs.append("✅ All guardrails clear")

    return not blocked, msgs


# ── MONTE CARLO SIMULATION ─────────────────────────────────────────────────────
def run_monte_carlo(bankroll: float, win_prob: float, avg_win: float,
                    avg_loss: float, n_trades: int, n_paths: int,
                    seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    paths = np.zeros((n_paths, n_trades + 1))
    paths[:, 0] = bankroll

    for p in range(n_paths):
        bal = bankroll
        for t in range(n_trades):
            bal = max(0.0, bal + (avg_win if rng.random() < win_prob else -avg_loss))
            paths[p, t + 1] = bal

    return paths


# ── CALIBRATION ────────────────────────────────────────────────────────────────
def calculate_calibration(trades_df: pd.DataFrame) -> pd.DataFrame:
    bins = np.linspace(0.0, 1.0, 11)
    bin_labels = [f"{int(bins[i]*100)}–{int(bins[i+1]*100)}%" for i in range(len(bins) - 1)]
    mids = [(bins[i] + bins[i + 1]) / 2 for i in range(len(bins) - 1)]

    empty = pd.DataFrame({
        "bin": bin_labels,
        "actual_win_rate": [np.nan] * 10,
        "predicted_midpoint": mids,
        "count": [0] * 10,
    })

    if trades_df.empty or "settled" not in trades_df.columns:
        return empty

    settled = trades_df[trades_df["settled"] == True].copy()
    if settled.empty or "model_prob" not in settled.columns or "outcome" not in settled.columns:
        return empty

    settled["win"] = (settled["outcome"] == "win").astype(int)
    settled["bin"] = pd.cut(settled["model_prob"], bins=bins, labels=bin_labels, include_lowest=True)

    cal = (
        settled.groupby("bin", observed=True)
        .agg(actual_win_rate=("win", "mean"), count=("win", "count"))
        .reset_index()
    )
    cal = cal.rename(columns={"bin": "bin"})
    cal["predicted_midpoint"] = mids[: len(cal)]
    return cal


# ── PORTFOLIO METRICS ──────────────────────────────────────────────────────────
def portfolio_metrics(trades_df: pd.DataFrame, initial_bankroll: float) -> dict:
    base = dict(total=0, settled=0, win_rate=0.0, total_pnl=0.0,
                bankroll=initial_bankroll, profit_factor=0.0,
                max_drawdown=0.0, avg_edge=0.0, sharpe=0.0,
                avg_win=0.0, avg_loss=0.0)

    if trades_df.empty:
        return base

    base["total"] = len(trades_df)
    base["avg_edge"] = float(trades_df["edge"].mean()) if "edge" in trades_df.columns else 0.0

    if "settled" not in trades_df.columns:
        return base

    settled = trades_df[trades_df["settled"] == True]
    if settled.empty:
        return base

    wins   = settled[settled["outcome"] == "win"]
    losses = settled[settled["outcome"] == "loss"]
    pnl    = settled["pnl"] if "pnl" in settled.columns else pd.Series(dtype=float)

    gross_win  = float(wins["pnl"].sum())  if not wins.empty   else 0.0
    gross_loss = float(abs(losses["pnl"].sum())) if not losses.empty else 0.0

    cum   = pnl.cumsum()
    dd    = float((cum.cummax() - cum).max())
    std   = float(pnl.std())
    sharpe = float(pnl.mean() / std * np.sqrt(252)) if std > 0 and len(settled) > 1 else 0.0

    base.update(
        settled=len(settled),
        win_rate=float(len(wins) / len(settled)),
        total_pnl=float(pnl.sum()),
        bankroll=initial_bankroll + float(pnl.sum()),
        profit_factor=gross_win / gross_loss if gross_loss > 0 else float("inf"),
        max_drawdown=dd,
        avg_win=float(wins["pnl"].mean())          if not wins.empty   else 0.0,
        avg_loss=float(abs(losses["pnl"].mean()))  if not losses.empty else 0.0,
        sharpe=sharpe,
    )
    return base


# ══════════════════════════════════════════════════════════════════════════════
#  STREAMLIT TABS
# ══════════════════════════════════════════════════════════════════════════════

def tab_scanner(cfg: dict) -> None:
    st.subheader("📡 Market Scanner")

    c1, c2 = st.columns([4, 1])
    c1.caption(f"Synthetic scanner · {cfg['n_markets']} markets · seed {cfg['scan_seed']}")
    with c2:
        if st.button("🔄 Rescan", use_container_width=True):
            st.session_state.pop("scan_df", None)

    if "scan_df" not in st.session_state:
        st.session_state.scan_df = scan_markets(cfg["n_markets"], cfg["scan_seed"])

    df = st.session_state.scan_df.copy()

    # Filters
    f1, f2, f3 = st.columns(3)
    passed_only = f1.checkbox("Passed filters only", value=True)
    cats = ["All"] + sorted(df["category"].unique().tolist())
    cat  = f2.selectbox("Category", cats)
    min_e = f3.slider("Min |edge|", 0, 30, 3) / 100

    if passed_only:
        df = df[df["passed_filters"]]
    if cat != "All":
        df = df[df["category"] == cat]
    df = df[df["edge"].abs() >= min_e]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Scanned",        cfg["n_markets"])
    m2.metric("Passed filters", int(st.session_state.scan_df["passed_filters"].sum()))
    m3.metric("Showing",        len(df))
    m4.metric("Avg edge",       f"{df['edge'].mean()*100:.1f}%" if not df.empty else "—")

    st.divider()

    if df.empty:
        st.warning("No markets match current filters.")
        return

    view = df[[
        "market_id", "title", "category",
        "implied_probability", "model_probability", "edge",
        "spread", "liquidity", "block_reason",
    ]].copy()

    for col, fmt in [
        ("implied_probability", lambda x: f"{x*100:.1f}%"),
        ("model_probability",   lambda x: f"{x*100:.1f}%"),
        ("edge",                lambda x: f"{x*100:+.1f}%"),
        ("spread",              lambda x: f"{x*100:.1f}%"),
        ("liquidity",           lambda x: f"${x/1000:.0f}k"),
    ]:
        view[col] = view[col].apply(fmt)

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "market_id":           "ID",
            "title":               "Market",
            "category":            "Type",
            "implied_probability": "Mkt Price",
            "model_probability":   "Model Est.",
            "edge":                "Edge",
            "spread":              "Spread",
            "liquidity":           "Liquidity",
            "block_reason":        "Status",
        },
    )

    st.subheader("Edge distribution")
    edge_vals = st.session_state.scan_df["edge"].copy()
    hist, edges = np.histogram(edge_vals, bins=20)
    edge_df = pd.DataFrame({"edge": [(edges[i]+edges[i+1])/2 for i in range(len(hist))], "count": hist})
    st.bar_chart(edge_df.set_index("edge"))


# ─────────────────────────────────────────────────────────────────────────────
def tab_trade_log(cfg: dict) -> None:
    st.subheader("📝 Paper Trade Log")
    trades_df = load_trade_history()

    # ── Log new trade ─────────────────────────────────────────────────────────
    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            market_id = st.text_input("Market ID", placeholder="MKT-42-0001 or custom")
            title     = st.text_input("Market Title", placeholder="BTC above $65k by EOD")
            category  = st.selectbox("Category",
                ["crypto","sports","economics","weather","politics","culture","other"])
        with c2:
            side       = st.selectbox("Side", ["YES", "NO"])
            entry_prob = st.number_input("Entry Price (%)", 1.0, 99.0, 55.0, 0.5) / 100
            model_prob = st.number_input("Model Probability (%)", 1.0, 99.0, 62.0, 0.5) / 100
        with c3:
            edge_val  = model_prob - entry_prob
            kelly_f   = fractional_kelly_fraction(entry_prob, model_prob,
                                                  cfg["kelly_frac"], cfg["max_risk"], cfg["min_edge"])
            rec_stake = round(cfg["bankroll"] * kelly_f, 2)

            st.metric("Calculated Edge",    f"{edge_val*100:+.1f}%")
            st.metric("Rec. Stake (Kelly)", f"${rec_stake:,.2f}")
            stake = st.number_input("Actual Stake ($)", 0.0, cfg["bankroll"],
                                    float(rec_stake), 5.0)

        notes = st.text_area("Notes / Reasoning",
            placeholder="Why do you have edge here? What's the market missing?", height=70)

        ok, guard_msgs = check_guardrails(cfg["bankroll"], stake, trades_df)
        for msg in guard_msgs:
            (st.error if "🚫" in msg else st.warning if "⚠️" in msg else st.success)(msg)

        if st.button("📌 Log Trade", disabled=not ok, use_container_width=True):
            new_row = {
                "logged_at":           dt.datetime.now().isoformat(timespec="seconds"),
                "market_id":           market_id or f"MANUAL-{dt.datetime.now().strftime('%H%M%S')}",
                "title":               title or "Untitled",
                "category":            category,
                "side":                side,
                "entry_prob":          entry_prob,
                "model_prob":          model_prob,
                "edge":                edge_val,
                "stake":               stake,
                "kelly_fraction_used": kelly_f,
                "outcome":             None,
                "pnl":                 None,
                "settled":             False,
                "settled_at":          None,
                "notes":               notes,
            }
            trades_df = pd.concat([trades_df, pd.DataFrame([new_row])], ignore_index=True)
            save_trade_history(trades_df)
            st.success(f"Trade logged: {new_row['market_id']}")
            st.rerun()

    # ── Batch settle ──────────────────────────────────────────────────────────
    if "settled" in trades_df.columns:
        unsettled = trades_df[~trades_df["settled"]]
    else:
        unsettled = pd.DataFrame()

    if not unsettled.empty:
        with st.expander(f"⚖️ Settle Open Trades ({len(unsettled)})", expanded=False):
            settle_rows: list[tuple] = []
            for idx, row in unsettled.iterrows():
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.write(f"**{row.get('title','?')}** | stake ${row.get('stake',0):.2f} | edge {row.get('edge',0)*100:+.1f}%")
                outcome = c2.selectbox("", ["—","win","loss","push"], key=f"out_{idx}")
                if outcome != "—":
                    ep = float(row.get("entry_prob", 0.5))
                    sk = float(row.get("stake", 0))
                    sd = str(row.get("side", "YES"))
                    if outcome == "win":
                        default_pnl = (sk * (1-ep)/ep) if sd == "YES" else (sk * ep/(1-ep))
                    elif outcome == "loss":
                        default_pnl = -sk
                    else:
                        default_pnl = 0.0
                    pnl = c3.number_input("P/L ($)", value=round(default_pnl,2), key=f"pnl_{idx}")
                    settle_rows.append((idx, outcome, pnl))

            if st.button("✅ Settle Selected", use_container_width=True) and settle_rows:
                for idx, outcome, pnl in settle_rows:
                    trades_df.loc[idx, "outcome"]    = outcome
                    trades_df.loc[idx, "pnl"]        = pnl
                    trades_df.loc[idx, "settled"]     = True
                    trades_df.loc[idx, "settled_at"]  = dt.datetime.now().isoformat(timespec="seconds")
                save_trade_history(trades_df)
                st.success(f"Settled {len(settle_rows)} trade(s)")
                st.rerun()

    # ── History table ─────────────────────────────────────────────────────────
    st.subheader("Trade History")
    if trades_df.empty:
        st.info("No trades yet. Use the form above to log your first trade.")
        return

    display = trades_df.copy().sort_values("logged_at", ascending=False)
    for col in ("entry_prob", "model_prob"):
        if col in display.columns:
            display[col] = display[col].apply(lambda x: f"{x*100:.1f}%" if pd.notnull(x) else "—")
    if "edge" in display.columns:
        display["edge"] = display["edge"].apply(lambda x: f"{x*100:+.1f}%" if pd.notnull(x) else "—")
    if "pnl" in display.columns:
        display["pnl"] = display["pnl"].apply(lambda x: f"${x:+.2f}" if pd.notnull(x) else "—")

    st.dataframe(display, use_container_width=True, hide_index=True, height=380)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear All Trades", type="secondary"):
            if st.session_state.get("_confirm_clear"):
                save_trade_history(pd.DataFrame(columns=TRADE_COLS))
                st.session_state._confirm_clear = False
                st.rerun()
            else:
                st.session_state._confirm_clear = True
                st.warning("Click again to confirm — this deletes all trade history.")
    with col2:
        st.download_button("📥 Export CSV", trades_df.to_csv(index=False),
                           "paper_trades.csv", "text/csv", use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def tab_analytics(cfg: dict) -> None:
    st.subheader("📈 Portfolio Analytics")
    trades_df = load_trade_history()
    m = portfolio_metrics(trades_df, cfg["bankroll"])

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Total Trades",  m["total"])
    c2.metric("Settled",       m["settled"])
    c3.metric("Win Rate",      f"{m['win_rate']*100:.1f}%",
              delta=f"{(m['win_rate']-0.5)*100:+.1f}% vs 50%")
    c4.metric("Total P/L",     f"${m['total_pnl']:+,.2f}",
              delta=f"{m['total_pnl']/cfg['bankroll']*100:+.1f}% ROI")
    pf = m["profit_factor"]
    c5.metric("Profit Factor", f"{pf:.2f}x" if np.isfinite(pf) else "∞")
    c6.metric("Sharpe (ann.)", f"{m['sharpe']:.2f}")

    st.divider()

    if "settled" not in trades_df.columns:
        st.info("No data yet.")
        return
    settled = trades_df[trades_df["settled"] == True]
    if settled.empty:
        st.info("No settled trades yet. Settle trades in the Trade Log tab to see analytics.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cumulative P/L")
        cum = settled["pnl"].cumsum().reset_index(drop=True)
        cum_df = pd.DataFrame({"Cumulative P/L ($)": cum})
        cum_df.index.name = "Trade #"
        st.line_chart(cum_df)

    with col2:
        st.subheader("P/L by Category")
        if "category" in settled.columns:
            cat_pnl = settled.groupby("category")["pnl"].sum().sort_values()
            st.bar_chart(cat_pnl.rename("P/L ($)"))

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Avg Win vs Avg Loss")
        bar_df = pd.DataFrame({
            "Amount": [m["avg_win"], -m["avg_loss"]],
        }, index=["Avg Win", "Avg Loss"])
        st.bar_chart(bar_df)

    with col4:
        st.subheader("Win Rate by Category")
        if "category" in settled.columns and "outcome" in settled.columns:
            wr = (
                settled.groupby("category")["outcome"]
                .apply(lambda x: (x == "win").mean() * 100)
                .round(1)
                .rename("Win Rate (%)")
            )
            st.bar_chart(wr)

    st.divider()
    st.subheader("Key Stats")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Avg Win",      f"${m['avg_win']:,.2f}")
    s2.metric("Avg Loss",     f"${m['avg_loss']:,.2f}")
    s3.metric("Max Drawdown", f"${m['max_drawdown']:,.2f}")
    s4.metric("Avg Edge",     f"{m['avg_edge']*100:.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
def tab_monte_carlo(cfg: dict) -> None:
    st.subheader("🎲 Monte Carlo Wealth Simulation")

    trades_df = load_trade_history()
    m = portfolio_metrics(trades_df, cfg["bankroll"])

    # Seed inputs from real history when available
    def_wr   = m["win_rate"] * 100  if m["settled"] >= 10 else 55.0
    def_win  = m["avg_win"]         if m["settled"] >= 10 else 35.0
    def_loss = m["avg_loss"]        if m["settled"] >= 10 else 25.0

    c1, c2, c3 = st.columns(3)
    with c1:
        win_prob = st.slider("Win Rate (%)", 30, 80, int(def_wr), 1) / 100
        n_trades = st.slider("Trades to simulate", 20, 500, 100, 10)
    with c2:
        avg_win  = st.number_input("Avg Win ($)",  1.0, value=round(def_win,  2), step=1.0)
        avg_loss = st.number_input("Avg Loss ($)", 1.0, value=round(def_loss, 2), step=1.0)
    with c3:
        n_paths  = st.slider("Simulated paths", 50, 1000, 300, 50)
        mc_seed  = st.number_input("RNG Seed", 0, 9999, 99)

    if m["settled"] >= 10:
        st.caption("✅ Inputs seeded from your real trade history")
    else:
        st.caption("Using default inputs — log and settle ≥ 10 trades to seed from real data")

    paths = run_monte_carlo(cfg["bankroll"], win_prob, avg_win, avg_loss,
                            n_trades, n_paths, int(mc_seed))

    pcts = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    perc_df = pd.DataFrame({
        "p5 (worst 5%)":   pcts[0],
        "p25":             pcts[1],
        "p50 (median)":    pcts[2],
        "p75":             pcts[3],
        "p95 (best 5%)":   pcts[4],
    })

    st.subheader("Wealth Path — Percentile Bands")
    st.line_chart(perc_df)

    final = paths[:, -1]
    r1,r2,r3,r4,r5 = st.columns(5)
    r1.metric("Median Final",    f"${np.median(final):,.0f}")
    r2.metric("5th percentile",  f"${np.percentile(final, 5):,.0f}")
    r3.metric("95th percentile", f"${np.percentile(final, 95):,.0f}")
    r4.metric("Ruin rate",       f"{(final < cfg['bankroll']*0.1).mean()*100:.1f}%",
              help="Paths ending below 10% of starting bankroll")
    r5.metric("2x+ rate",        f"{(final > cfg['bankroll']*2).mean()*100:.1f}%")

    ev = win_prob * avg_win - (1 - win_prob) * avg_loss
    color = "green" if ev > 0 else "red"
    st.markdown(
        f"**Expected value/trade:** :{color}[${ev:+.2f}]  →  after {n_trades} trades: :{color}[${ev*n_trades:+,.2f}]"
    )


# ─────────────────────────────────────────────────────────────────────────────
def tab_calibration(cfg: dict) -> None:
    st.subheader("🎯 Calibration Analysis")
    st.caption(
        "A well-calibrated model wins ~X% of the time when it assigns X% probability. "
        "Bars above the diagonal = you're underconfident. Below = overconfident."
    )

    trades_df = load_trade_history()
    cal = calculate_calibration(trades_df)

    valid = cal.dropna(subset=["actual_win_rate"])
    if valid.empty:
        st.info("No settled trades yet. Log and settle trades to see calibration.")

        ideal = pd.DataFrame({
            "Predicted Bucket":    [f"{i*10}–{i*10+10}%" for i in range(10)],
            "Well-Calibrated At":  [f"{i*10+5}%" for i in range(10)],
        })
        st.caption("What perfect calibration looks like:")
        st.dataframe(ideal, use_container_width=True, hide_index=True)
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Predicted vs Actual Win Rate")
        chart_df = (
            valid.set_index("bin")[["actual_win_rate", "predicted_midpoint"]]
            .rename(columns={"actual_win_rate": "Actual Win Rate",
                             "predicted_midpoint": "Perfect Calibration"})
        )
        st.line_chart(chart_df)

    with col2:
        st.subheader("Calibration Table")
        tbl = cal[["bin", "actual_win_rate", "count"]].copy()
        tbl["actual_win_rate"] = tbl["actual_win_rate"].apply(
            lambda x: f"{x*100:.1f}%" if pd.notnull(x) else "—"
        )
        tbl.columns = ["Bucket", "Actual Win%", "n"]
        st.dataframe(tbl, use_container_width=True, hide_index=True)

    if not valid.empty and "predicted_midpoint" in valid.columns:
        brier = float(((valid["predicted_midpoint"] - valid["actual_win_rate"]) ** 2).mean())
        b1, b2, b3 = st.columns(3)
        b1.metric("Brier Score",   f"{brier:.4f}", help="Lower = better. 0 = perfect, 0.25 = coin flip")
        b2.metric("Settled Trades", int(cal["count"].sum()))
        b3.metric("Covered Bins",   int((cal["count"] > 0).sum()))


# ─────────────────────────────────────────────────────────────────────────────
def tab_risk_engine(cfg: dict) -> None:
    st.subheader("⚖️ Risk Engine")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Kelly Calculator")
        kc1, kc2 = st.columns(2)
        entry  = kc1.number_input("Entry Price (%)", 1.0, 99.0, 55.0, 0.5, key="rk_entry") / 100
        model  = kc1.number_input("Model Prob (%)",  1.0, 99.0, 63.0, 0.5, key="rk_model") / 100
        kf     = kc2.slider("Kelly Fraction", 0.05, 1.0, cfg["kelly_frac"], 0.05, key="rk_kf")
        bank   = kc2.number_input("Bankroll ($)", 100.0, 1_000_000.0, cfg["bankroll"], 100.0, key="rk_bank")

        edge_v = model - entry
        frac   = fractional_kelly_fraction(entry, model, kf, cfg["max_risk"], cfg["min_edge"])
        stake  = bank * frac

        r1, r2, r3 = st.columns(3)
        r1.metric("Edge",           f"{edge_v*100:+.1f}%")
        r2.metric(f"{kf:.0%} Kelly", f"{frac*100:.2f}%")
        r3.metric("Rec. Stake",     f"${stake:,.2f}")

        # Sizing reference table
        st.divider()
        st.subheader("Sizing Reference")
        ref = pd.DataFrame([
            {"Edge":   "< 3%",   "Win Rate":  "Any",     "Kelly Fraction": "Skip",           "Notes": "Below noise floor"},
            {"Edge":   "3–5%",   "Win Rate":  "< 52%",   "Kelly Fraction": "1/8 Kelly",      "Notes": "Weak signal"},
            {"Edge":   "5–10%",  "Win Rate":  "52–56%",  "Kelly Fraction": "1/4 Kelly",      "Notes": "Standard edge"},
            {"Edge":   "10–15%", "Win Rate":  "56–60%",  "Kelly Fraction": "1/4–1/2 Kelly",  "Notes": "Strong edge"},
            {"Edge":   "> 15%",  "Win Rate":  "> 60%",   "Kelly Fraction": "1/2 Kelly max",  "Notes": "Hard cap at half-K"},
        ])
        st.dataframe(ref, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Guardrail Checker")
        trades_df = load_trade_history()
        test_stake = st.number_input("Test Stake ($)", 0.0, cfg["bankroll"],
                                     round(cfg["bankroll"] * 0.03, 2), 5.0)
        ok, msgs = check_guardrails(cfg["bankroll"], test_stake, trades_df)
        for msg in msgs:
            (st.error if "🚫" in msg else st.warning if "⚠️" in msg else st.success)(msg)

        st.divider()
        st.subheader("Hard Rules")
        for rule in [
            "🚫 Never exceed 5% of bankroll per trade",
            "📉 3-loss streak → cut size 50% until session recovers",
            "⏸️ Daily drawdown > 5% → stop for 24 h, review edge",
            "🔗 Correlated markets → halve each position",
            "🔬 < 30 settled trades in category → use 1/8 Kelly",
            "✍️ Log reasoning BEFORE entry, not after",
            "🧮 Always use model probability, not gut feel, for sizing",
        ]:
            st.write(rule)


# ─────────────────────────────────────────────────────────────────────────────
def tab_recommendations(cfg: dict) -> None:
    st.subheader("💡 Recommendations")
    st.caption("Top actionable markets from the last scan, ranked by adjusted edge after spread.")

    if "scan_df" not in st.session_state:
        st.info("Run the Scanner tab first to generate recommendations.")
        return

    df = st.session_state.scan_df.copy()
    trades_df = load_trade_history()
    m = portfolio_metrics(trades_df, cfg["bankroll"])

    # Adjusted edge = raw edge − spread / 2
    df["adj_edge"] = df["edge"] - df["spread"] / 2

    top = (
        df[df["passed_filters"] & (df["adj_edge"] > cfg["min_edge"])]
        .sort_values("adj_edge", ascending=False)
        .head(8)
    )

    if top.empty:
        st.warning("No markets cleared all filters at the current settings. "
                   "Lower the edge threshold or rescan with a different seed.")
        return

    # Portfolio context banner
    bc1, bc2, bc3 = st.columns(3)
    bc1.metric("Current Bankroll", f"${m['bankroll']:,.2f}")
    bc2.metric("Win Rate (settled)", f"{m['win_rate']*100:.1f}%" if m["settled"] else "—")
    bc3.metric("Avg Edge (history)", f"{m['avg_edge']*100:.1f}%" if m["total"] else "—")

    st.divider()

    for _, row in top.iterrows():
        edge_pct  = row["adj_edge"] * 100
        frac      = fractional_kelly_fraction(
                        row["implied_probability"], row["model_probability"],
                        cfg["kelly_frac"], cfg["max_risk"], cfg["min_edge"])
        stake_rec = round(cfg["bankroll"] * frac, 2)

        # Tier label
        if edge_pct >= 15:
            tier, tier_color = "FAT PITCH", "🟢"
        elif edge_pct >= 10:
            tier, tier_color = "STRONG",    "🟢"
        elif edge_pct >= 5:
            tier, tier_color = "STANDARD",  "🔵"
        else:
            tier, tier_color = "MARGINAL",  "🟡"

        with st.container():
            h1, h2, h3, h4, h5 = st.columns([4, 1, 1, 1, 1])
            h1.markdown(f"**{row['title']}**  `{row['category']}`")
            h2.metric("Adj Edge",   f"{edge_pct:+.1f}%")
            h3.metric("Mkt Price",  f"{row['implied_probability']*100:.1f}%")
            h4.metric("Model Est.", f"{row['model_probability']*100:.1f}%")
            h5.metric("Rec Stake",  f"${stake_rec:,.2f}")

            st.caption(
                f"{tier_color} **{tier}** · "
                f"Spread {row['spread']*100:.1f}% · "
                f"Liquidity ${row['liquidity']/1000:.0f}k · "
                f"ID: `{row['market_id']}`"
            )
            st.divider()

    st.caption(
        f"Showing top {len(top)} markets. "
        f"Stake recommendations use {cfg['kelly_frac']:.0%} Kelly on ${cfg['bankroll']:,.0f} bankroll. "
        "Always verify edge with your own model before trading."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR & MAIN
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar() -> dict:
    st.sidebar.title("▲ Tr@deMet")
    st.sidebar.caption("Prediction Market Research Lab")
    st.sidebar.divider()

    st.sidebar.subheader("⚙️ Global Settings")
    bankroll   = st.sidebar.number_input("Bankroll ($)", 100.0, 1_000_000.0, INITIAL_BANKROLL, 100.0)
    kelly_frac = st.sidebar.slider("Kelly Fraction", 0.05, 1.0, 0.25, 0.05,
                                   help="0.25 = quarter Kelly (recommended). 1.0 = full Kelly.")
    max_risk   = st.sidebar.slider("Max Risk / Trade (%)", 1, 10, 5, 1) / 100.0
    min_edge   = st.sidebar.slider("Min Edge Threshold (%)", 1, 10, 3, 1) / 100.0

    st.sidebar.divider()
    st.sidebar.subheader("🔬 Scanner")
    n_markets  = st.sidebar.slider("Markets to scan", 20, 200, 80, 10)
    scan_seed  = st.sidebar.number_input("RNG Seed", 0, 9999, 42)

    trades_df = load_trade_history()
    m = portfolio_metrics(trades_df, bankroll)

    st.sidebar.divider()
    st.sidebar.subheader("📊 Quick Stats")
    st.sidebar.metric("Bankroll",   f"${m['bankroll']:,.2f}")
    st.sidebar.metric("Total P/L",  f"${m['total_pnl']:+,.2f}")
    st.sidebar.metric("Win Rate",   f"{m['win_rate']*100:.1f}%" if m["settled"] else "—")
    st.sidebar.metric("Open trades", int(m["total"] - m["settled"]))

    return dict(
        bankroll=bankroll,
        kelly_frac=kelly_frac,
        max_risk=max_risk,
        min_edge=min_edge,
        n_markets=n_markets,
        scan_seed=int(scan_seed),
    )


def main() -> None:
    st.set_page_config(
        page_title="Tr@deMet Dashboard",
        page_icon="▲",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    cfg = render_sidebar()

    tabs = st.tabs([
        "📡 Scanner",
        "📝 Trade Log",
        "📈 Analytics",
        "🎲 Monte Carlo",
        "🎯 Calibration",
        "⚖️ Risk Engine",
        "💡 Recommendations",
    ])

    with tabs[0]: tab_scanner(cfg)
    with tabs[1]: tab_trade_log(cfg)
    with tabs[2]: tab_analytics(cfg)
    with tabs[3]: tab_monte_carlo(cfg)
    with tabs[4]: tab_calibration(cfg)
    with tabs[5]: tab_risk_engine(cfg)
    with tabs[6]: tab_recommendations(cfg)


if __name__ == "__main__":
    main()
