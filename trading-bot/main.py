"""
Crypto Trading Bot — Paper Trading Mode by default.

Usage:
    python main.py
"""

import time
import sys
from config import config
from data import get_exchange, fetch_ohlcv, fetch_ticker
from strategy import get_signal, SIGNAL_BUY, SIGNAL_SELL
from risk import position_size, stop_loss_price, take_profit_price, check_exit
from logger import logger, log_trade


class PaperTrader:
    """Simulated portfolio for paper trading."""

    def __init__(self, initial_balance: float):
        self.balance = initial_balance
        self.position = 0.0    # crypto held
        self.entry_price = 0.0
        self.sl_price = 0.0
        self.tp_price = 0.0
        self.trade_count = 0

    @property
    def in_position(self) -> bool:
        return self.position > 0

    def buy(self, price: float) -> None:
        qty = position_size(self.balance, price)
        cost = qty * price
        if cost > self.balance:
            logger.warning("Insufficient balance to buy. balance=%.2f cost=%.2f", self.balance, cost)
            return
        self.balance -= cost
        self.position = qty
        self.entry_price = price
        self.sl_price = stop_loss_price(price)
        self.tp_price = take_profit_price(price)
        self.trade_count += 1
        log_trade("BUY", config.SYMBOL, price, qty, self.balance)
        logger.info("  SL=%.4f | TP=%.4f", self.sl_price, self.tp_price)

    def sell(self, price: float, reason: str = "SIGNAL") -> None:
        proceeds = self.position * price
        pnl = (price - self.entry_price) * self.position
        self.balance += proceeds
        log_trade("SELL", config.SYMBOL, price, self.position, self.balance)
        logger.info("  Reason=%-12s | PnL=%+.2f USDT", reason, pnl)
        self.position = 0.0
        self.entry_price = 0.0

    def portfolio_value(self, current_price: float) -> float:
        return self.balance + self.position * current_price

    def status(self, current_price: float) -> str:
        pv = self.portfolio_value(current_price)
        if self.in_position:
            unrealized = (current_price - self.entry_price) * self.position
            return (
                f"balance={self.balance:.2f} USDT | "
                f"position={self.position:.6f} {config.SYMBOL.split('/')[0]} | "
                f"entry={self.entry_price:.4f} | unrealized PnL={unrealized:+.2f} USDT | "
                f"portfolio={pv:.2f} USDT"
            )
        return f"balance={self.balance:.2f} USDT | no position | portfolio={pv:.2f} USDT"


def run_bot() -> None:
    config.validate()

    mode_label = "PAPER TRADING" if config.IS_PAPER else "LIVE TRADING"
    logger.info("=" * 60)
    logger.info("Starting bot in %s mode", mode_label)
    logger.info("Symbol: %s | Timeframe: %s", config.SYMBOL, config.TIMEFRAME)
    logger.info("RSI period=%d | oversold=%s | overbought=%s",
                config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
    logger.info("Risk per trade=%.0f%% | SL=%.0f%% | TP=%.0f%%",
                config.RISK_PER_TRADE * 100, config.STOP_LOSS_PCT * 100, config.TAKE_PROFIT_PCT * 100)
    logger.info("=" * 60)

    exchange = get_exchange()
    trader = PaperTrader(config.INITIAL_BALANCE) if config.IS_PAPER else None

    if not config.IS_PAPER:
        logger.error("Live trading is not yet enabled. Set TRADING_MODE=paper in .env.")
        sys.exit(1)

    logger.info("Initial balance: %.2f USDT", trader.balance)

    while True:
        try:
            df = fetch_ohlcv(exchange)
            ticker = fetch_ticker(exchange)
            current_price = ticker["last"]

            # Check stop-loss / take-profit for open position
            if trader.in_position:
                exit_reason = check_exit(current_price, trader.entry_price)
                if exit_reason:
                    trader.sell(current_price, reason=exit_reason)

            # Evaluate strategy signal
            if not trader.in_position:
                signal = get_signal(df)
                if signal == SIGNAL_BUY:
                    trader.buy(current_price)
            else:
                signal = get_signal(df)
                if signal == SIGNAL_SELL:
                    trader.sell(current_price, reason="RSI_SIGNAL")

            logger.info("Status | %s", trader.status(current_price))

        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            if trader:
                ticker = fetch_ticker(exchange)
                logger.info("Final portfolio value: %.2f USDT", trader.portfolio_value(ticker["last"]))
            break
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)

        time.sleep(config.LOOP_INTERVAL)


if __name__ == "__main__":
    run_bot()
