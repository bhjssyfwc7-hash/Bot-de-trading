"""
Simple event-driven backtester using the RSI strategy.

Usage:
    python backtest.py
"""

import pandas as pd
import matplotlib.pyplot as plt
from data import get_exchange, fetch_ohlcv
from strategy import compute_rsi
from risk import position_size, stop_loss_price, take_profit_price
from config import config
from logger import logger


def run_backtest(df: pd.DataFrame, initial_balance: float = None) -> dict:
    initial_balance = initial_balance or config.INITIAL_BALANCE

    df = df.copy()
    df["rsi"] = compute_rsi(df)
    df.dropna(inplace=True)

    balance = initial_balance
    position = 0.0       # current crypto held
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    trades: list[dict] = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        price = row["close"]

        # Check exits first if we hold a position
        if position > 0:
            if price <= sl_price:
                pnl = (price - entry_price) * position
                balance += position * price
                trades.append({"type": "SELL", "reason": "STOP_LOSS", "price": price,
                                "qty": position, "pnl": pnl, "balance": balance,
                                "timestamp": row.name})
                position = 0.0
                continue

            if price >= tp_price:
                pnl = (price - entry_price) * position
                balance += position * price
                trades.append({"type": "SELL", "reason": "TAKE_PROFIT", "price": price,
                                "qty": position, "pnl": pnl, "balance": balance,
                                "timestamp": row.name})
                position = 0.0
                continue

        # RSI crossover signals
        rsi_now = row["rsi"]
        rsi_prev = prev["rsi"]

        if position == 0 and rsi_prev >= config.RSI_OVERSOLD and rsi_now < config.RSI_OVERSOLD:
            qty = position_size(balance, price)
            cost = qty * price
            if cost <= balance:
                balance -= cost
                position = qty
                entry_price = price
                sl_price = stop_loss_price(price)
                tp_price = take_profit_price(price)
                trades.append({"type": "BUY", "reason": "RSI_OVERSOLD", "price": price,
                                "qty": qty, "pnl": 0.0, "balance": balance,
                                "timestamp": row.name})

        elif position > 0 and rsi_prev <= config.RSI_OVERBOUGHT and rsi_now > config.RSI_OVERBOUGHT:
            pnl = (price - entry_price) * position
            balance += position * price
            trades.append({"type": "SELL", "reason": "RSI_OVERBOUGHT", "price": price,
                           "qty": position, "pnl": pnl, "balance": balance,
                           "timestamp": row.name})
            position = 0.0

    # Close open position at last candle
    if position > 0:
        price = df.iloc[-1]["close"]
        pnl = (price - entry_price) * position
        balance += position * price
        trades.append({"type": "SELL", "reason": "END_OF_DATA", "price": price,
                       "qty": position, "pnl": pnl, "balance": balance,
                       "timestamp": df.iloc[-1].name})

    trades_df = pd.DataFrame(trades)
    total_pnl = balance - initial_balance
    n_trades = len(trades_df[trades_df["type"] == "BUY"]) if not trades_df.empty else 0
    win_trades = trades_df[(trades_df["type"] == "SELL") & (trades_df["pnl"] > 0)] if not trades_df.empty else pd.DataFrame()
    win_rate = len(win_trades) / n_trades * 100 if n_trades > 0 else 0.0

    results = {
        "initial_balance": initial_balance,
        "final_balance": balance,
        "total_pnl": total_pnl,
        "return_pct": total_pnl / initial_balance * 100,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "trades": trades_df,
    }

    logger.info(
        "Backtest complete | PnL: %.2f USDT (%.2f%%) | Trades: %d | Win rate: %.1f%%",
        total_pnl,
        results["return_pct"],
        n_trades,
        win_rate,
    )
    return results


def plot_results(df: pd.DataFrame, results: dict) -> None:
    trades_df = results["trades"]
    if trades_df.empty:
        print("No trades to plot.")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    ax1.plot(df.index, df["close"], label="Price", linewidth=1)
    buys = trades_df[trades_df["type"] == "BUY"]
    sells = trades_df[trades_df["type"] == "SELL"]
    ax1.scatter(buys["timestamp"], buys["price"], marker="^", color="green", s=80, label="Buy", zorder=5)
    ax1.scatter(sells["timestamp"], sells["price"], marker="v", color="red", s=80, label="Sell", zorder=5)
    ax1.set_title(f"{config.SYMBOL} — RSI Backtest")
    ax1.set_ylabel("Price (USDT)")
    ax1.legend()
    ax1.grid(alpha=0.3)

    rsi = df["rsi"]
    ax2.plot(df.index, rsi, label="RSI", color="purple", linewidth=1)
    ax2.axhline(config.RSI_OVERSOLD, color="green", linestyle="--", alpha=0.7, label=f"Oversold ({config.RSI_OVERSOLD})")
    ax2.axhline(config.RSI_OVERBOUGHT, color="red", linestyle="--", alpha=0.7, label=f"Overbought ({config.RSI_OVERBOUGHT})")
    ax2.set_ylabel("RSI")
    ax2.set_xlabel("Date")
    ax2.legend()
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("backtest_results.png", dpi=150)
    print("Chart saved to backtest_results.png")
    plt.show()


if __name__ == "__main__":
    exchange = get_exchange()
    print(f"Fetching {config.LIMIT} candles for {config.SYMBOL} ({config.TIMEFRAME})...")
    df = fetch_ohlcv(exchange, limit=500)

    results = run_backtest(df)

    print("\n=== Backtest Results ===")
    print(f"  Initial balance : {results['initial_balance']:.2f} USDT")
    print(f"  Final balance   : {results['final_balance']:.2f} USDT")
    print(f"  Total PnL       : {results['total_pnl']:+.2f} USDT ({results['return_pct']:+.2f}%)")
    print(f"  Number of trades: {results['n_trades']}")
    print(f"  Win rate        : {results['win_rate']:.1f}%")

    if not results["trades"].empty:
        print("\n=== Trade Log ===")
        print(results["trades"].to_string(index=False))

    plot_results(df, results)
