"""
Event-driven backtester — RSI strategy on BTC/USDT.

Usage:
    python backtest.py
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend (no display required)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from data import get_exchange, fetch_ohlcv
from strategy import compute_rsi
from risk import position_size, stop_loss_price, take_profit_price
from config import config
from logger import logger


# ── Core backtest engine ─────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, initial_balance: float = None) -> dict:
    initial_balance = initial_balance or config.INITIAL_BALANCE

    df = df.copy()
    df["rsi"] = compute_rsi(df)
    df.dropna(inplace=True)

    balance = initial_balance
    position = 0.0
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    trades: list[dict] = []
    equity_curve: list[dict] = []  # portfolio value at each candle close

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        price = row["close"]

        # ── Check SL / TP before signal ──────────────────────────────────────
        if position > 0:
            if price <= sl_price:
                pnl = (price - entry_price) * position
                balance += position * price
                trades.append({
                    "type": "SELL", "reason": "STOP_LOSS",
                    "price": price, "qty": position,
                    "pnl": pnl, "balance": balance, "timestamp": row.name,
                })
                position = 0.0

            elif price >= tp_price:
                pnl = (price - entry_price) * position
                balance += position * price
                trades.append({
                    "type": "SELL", "reason": "TAKE_PROFIT",
                    "price": price, "qty": position,
                    "pnl": pnl, "balance": balance, "timestamp": row.name,
                })
                position = 0.0

        # ── RSI crossover signals ─────────────────────────────────────────────
        rsi_now  = row["rsi"]
        rsi_prev = prev["rsi"]

        if position == 0 and rsi_prev < config.RSI_OVERSOLD and rsi_now >= config.RSI_OVERSOLD:
            qty  = position_size(balance, price)
            cost = qty * price
            if cost <= balance:
                balance -= cost
                position    = qty
                entry_price = price
                sl_price    = stop_loss_price(price)
                tp_price    = take_profit_price(price)
                trades.append({
                    "type": "BUY", "reason": "RSI_OVERSOLD",
                    "price": price, "qty": qty,
                    "pnl": 0.0, "balance": balance, "timestamp": row.name,
                })

        elif position > 0 and rsi_prev > config.RSI_OVERBOUGHT and rsi_now <= config.RSI_OVERBOUGHT:
            pnl = (price - entry_price) * position
            balance += position * price
            trades.append({
                "type": "SELL", "reason": "RSI_OVERBOUGHT",
                "price": price, "qty": position,
                "pnl": pnl, "balance": balance, "timestamp": row.name,
            })
            position = 0.0

        # ── Record portfolio value at this candle ─────────────────────────────
        equity_curve.append({
            "timestamp": row.name,
            "equity": balance + position * price,
        })

    # ── Force-close open position at last candle ──────────────────────────────
    if position > 0:
        price = df.iloc[-1]["close"]
        pnl   = (price - entry_price) * position
        balance += position * price
        trades.append({
            "type": "SELL", "reason": "END_OF_DATA",
            "price": price, "qty": position,
            "pnl": pnl, "balance": balance, "timestamp": df.iloc[-1].name,
        })
        if equity_curve:
            equity_curve[-1]["equity"] = balance

    # ── Metrics ───────────────────────────────────────────────────────────────
    trades_df  = pd.DataFrame(trades)
    equity_df  = pd.DataFrame(equity_curve).set_index("timestamp")

    sells      = trades_df[trades_df["type"] == "SELL"] if not trades_df.empty else pd.DataFrame()
    n_trades   = len(trades_df[trades_df["type"] == "BUY"]) if not trades_df.empty else 0
    win_trades = sells[sells["pnl"] > 0] if not sells.empty else pd.DataFrame()
    win_rate   = len(win_trades) / n_trades * 100 if n_trades > 0 else 0.0

    avg_win  = win_trades["pnl"].mean()  if not win_trades.empty  else 0.0
    avg_loss = sells[sells["pnl"] <= 0]["pnl"].mean() if not sells.empty and len(sells[sells["pnl"] <= 0]) > 0 else 0.0
    best_trade  = sells["pnl"].max() if not sells.empty else 0.0
    worst_trade = sells["pnl"].min() if not sells.empty else 0.0

    # Max drawdown from equity curve
    max_drawdown_pct = 0.0
    max_drawdown_abs = 0.0
    if not equity_df.empty:
        eq   = equity_df["equity"]
        peak = eq.cummax()
        dd   = (eq - peak) / peak * 100
        max_drawdown_pct = dd.min()          # negative value
        max_drawdown_abs = (eq - peak).min() # negative value in USDT

    total_pnl = balance - initial_balance

    results = {
        "initial_balance":  initial_balance,
        "final_balance":    balance,
        "total_pnl":        total_pnl,
        "return_pct":       total_pnl / initial_balance * 100,
        "n_trades":         n_trades,
        "win_rate":         win_rate,
        "avg_win":          avg_win,
        "avg_loss":         avg_loss,
        "best_trade":       best_trade,
        "worst_trade":      worst_trade,
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_abs": max_drawdown_abs,
        "trades":           trades_df,
        "equity":           equity_df,
    }

    logger.info(
        "Backtest | PnL %+.2f USDT (%+.2f%%) | %d trades | WR %.1f%% | MaxDD %.2f%%",
        total_pnl, results["return_pct"], n_trades, win_rate, max_drawdown_pct,
    )
    return results


# ── Chart ─────────────────────────────────────────────────────────────────────

def plot_results(df: pd.DataFrame, results: dict, save_path: str = "backtest_results.png") -> None:
    df = df.copy()
    if "rsi" not in df.columns:
        df["rsi"] = compute_rsi(df)

    trades_df = results["trades"]
    equity_df = results["equity"]

    fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1.2, 1.5]})
    fig.suptitle(
        f"{config.SYMBOL} — RSI({config.RSI_PERIOD}) Backtest  |  "
        f"PnL {results['return_pct']:+.2f}%  |  "
        f"WR {results['win_rate']:.1f}%  |  "
        f"MaxDD {results['max_drawdown_pct']:.2f}%",
        fontsize=12, fontweight="bold",
    )

    # ── Panel 1: price + trade markers ───────────────────────────────────────
    ax1 = axes[0]
    ax1.plot(df.index, df["close"], color="#1f77b4", linewidth=1, label="BTC/USDT")
    if not trades_df.empty:
        buys  = trades_df[trades_df["type"] == "BUY"]
        sells = trades_df[trades_df["type"] == "SELL"]
        ax1.scatter(buys["timestamp"],  buys["price"],  marker="^", color="limegreen",
                    s=90, zorder=5, label="BUY")
        ax1.scatter(sells["timestamp"], sells["price"], marker="v", color="tomato",
                    s=90, zorder=5, label="SELL")
    ax1.set_ylabel("Price (USDT)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.2)

    # ── Panel 2: RSI ─────────────────────────────────────────────────────────
    ax2 = axes[1]
    rsi = df["rsi"]
    ax2.plot(df.index, rsi, color="purple", linewidth=1, label="RSI(14)")
    ax2.axhline(config.RSI_OVERSOLD,  color="limegreen", linestyle="--", alpha=0.8,
                label=f"Oversold {config.RSI_OVERSOLD}")
    ax2.axhline(config.RSI_OVERBOUGHT, color="tomato",   linestyle="--", alpha=0.8,
                label=f"Overbought {config.RSI_OVERBOUGHT}")
    ax2.fill_between(df.index, rsi, config.RSI_OVERSOLD,
                     where=(rsi < config.RSI_OVERSOLD), alpha=0.15, color="limegreen")
    ax2.fill_between(df.index, rsi, config.RSI_OVERBOUGHT,
                     where=(rsi > config.RSI_OVERBOUGHT), alpha=0.15, color="tomato")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.2)

    # ── Panel 3: equity curve ─────────────────────────────────────────────────
    ax3 = axes[2]
    if not equity_df.empty:
        eq   = equity_df["equity"]
        peak = eq.cummax()
        ax3.plot(equity_df.index, eq,   color="steelblue", linewidth=1.2, label="Portfolio")
        ax3.plot(equity_df.index, peak, color="gray",      linewidth=0.8,
                 linestyle="--", alpha=0.6, label="Peak")
        ax3.fill_between(equity_df.index, eq, peak, alpha=0.2, color="tomato", label="Drawdown")
    ax3.axhline(results["initial_balance"], color="orange", linestyle=":", linewidth=1,
                label=f"Start {results['initial_balance']:.0f} USDT")
    ax3.set_ylabel("Portfolio (USDT)")
    ax3.set_xlabel("Date")
    ax3.legend(loc="upper left", fontsize=8)
    ax3.grid(alpha=0.2)

    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved → {save_path}")


# ── CLI entry point ────────────────────────────────────────────────────────────

def print_report(results: dict) -> None:
    t = results["trades"]
    sells = t[t["type"] == "SELL"] if not t.empty else pd.DataFrame()

    exits = sells["reason"].value_counts().to_dict() if not sells.empty else {}
    sl_hits = exits.get("STOP_LOSS", 0)
    tp_hits = exits.get("TAKE_PROFIT", 0)
    sig_exits = exits.get("RSI_OVERBOUGHT", 0) + exits.get("END_OF_DATA", 0)

    sep = "─" * 48
    print(f"\n{'═'*48}")
    print(f"  BACKTEST  {config.SYMBOL}  {config.TIMEFRAME}  —  RSI({config.RSI_PERIOD})")
    print(f"{'═'*48}")
    print(f"  Period          {results['equity'].index[0].strftime('%Y-%m-%d') if not results['equity'].empty else 'N/A'}"
          f"  →  {results['equity'].index[-1].strftime('%Y-%m-%d') if not results['equity'].empty else 'N/A'}")
    print(sep)
    print(f"  Initial balance   {results['initial_balance']:>10.2f} USDT")
    print(f"  Final balance     {results['final_balance']:>10.2f} USDT")
    print(f"  Total PnL         {results['total_pnl']:>+10.2f} USDT  ({results['return_pct']:+.2f}%)")
    print(sep)
    print(f"  Number of trades  {results['n_trades']:>10d}")
    print(f"  Win rate          {results['win_rate']:>9.1f}%")
    print(f"  Avg win           {results['avg_win']:>+10.2f} USDT")
    print(f"  Avg loss          {results['avg_loss']:>+10.2f} USDT")
    print(f"  Best trade        {results['best_trade']:>+10.2f} USDT")
    print(f"  Worst trade       {results['worst_trade']:>+10.2f} USDT")
    print(sep)
    print(f"  Max drawdown      {results['max_drawdown_pct']:>9.2f}%  ({results['max_drawdown_abs']:+.2f} USDT)")
    print(sep)
    print(f"  Exit reasons      SL={sl_hits}  TP={tp_hits}  Signal/End={sig_exits}")
    print(f"{'═'*48}\n")

    if not t.empty:
        detail = t[t["type"] == "SELL"][["timestamp", "reason", "price", "pnl"]].copy()
        detail["timestamp"] = detail["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
        detail["price"] = detail["price"].map("{:.2f}".format)
        detail["pnl"]   = detail["pnl"].map("{:+.2f}".format)
        print("  Trade-by-trade breakdown (SELL only):")
        print(detail.to_string(index=False))
        print()


if __name__ == "__main__":
    exchange = get_exchange()
    print(f"Fetching 500 candles — {config.SYMBOL} {config.TIMEFRAME} ...")
    df = fetch_ohlcv(exchange, limit=500)
    print(f"Candles received : {len(df)}  ({df.index[0]}  →  {df.index[-1]})")

    results = run_backtest(df)
    print_report(results)
    plot_results(df, results)
