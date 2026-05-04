"""
Crypto Trading Bot — Paper Trading Mode.
RSI(14) strategy on BTC/USDT | Kraken public feed | loop every 5 min.

Usage:
    python main.py
"""

import time
from datetime import datetime, timezone, timedelta

from config import config
from data import fetch_ohlcv, fetch_ticker
from strategy import get_signal, get_latest_rsi, SIGNAL_BUY, SIGNAL_SELL
from risk import position_size, stop_loss_price, take_profit_price, check_exit
from logger import logger, log_trade, quiet_console

# ── ANSI palette ──────────────────────────────────────────────────────────────
_G   = "\033[92m"   # green
_R   = "\033[91m"   # red
_Y   = "\033[93m"   # yellow
_C   = "\033[96m"   # cyan
_B   = "\033[1m"    # bold
_D   = "\033[2m"    # dim
_RST = "\033[0m"    # reset


# ── RSI helpers ───────────────────────────────────────────────────────────────

def _rsi_zone(rsi: float) -> tuple[str, str]:
    if rsi < 30:    return "SURVENTE", _G
    if rsi > 70:    return "SURACHAT", _R
    if rsi < 45:    return "baissier", _Y
    if rsi > 55:    return "haussier", _C
    return "neutre", _D


def _rsi_bar(rsi: float, w: int = 50) -> str:
    pos = min(int(rsi / 100 * w), w - 1)
    lo  = int(30 / 100 * w)    # = 15
    hi  = int(70 / 100 * w)    # = 35
    _, col = _rsi_zone(rsi)

    chars = []
    for i in range(w):
        if i == pos:
            chars.append(f"{col}{_B}█{_RST}")
        elif i in (lo, hi):
            chars.append(f"{_D}│{_RST}")
        elif i < pos:
            chars.append("▒")
        else:
            chars.append(f"{_D}░{_RST}")

    lo_pad  = lo - 2
    gap_pad = hi - lo - len(" 30% ") + 1
    hi_pad  = w - hi - len(" 70%") - 1

    axis = f"{_D}  {'0%':{lo_pad}} 30%{'':{gap_pad}} 70%{'':{hi_pad}} 100%{_RST}"
    return "  [" + "".join(chars) + "]\n" + axis


# ── Paper trader ──────────────────────────────────────────────────────────────

class PaperTrader:
    def __init__(self, initial_balance: float) -> None:
        self.balance     = initial_balance
        self.position    = 0.0
        self.entry_price = 0.0
        self.sl_price    = 0.0
        self.tp_price    = 0.0
        self.trade_count = 0

    @property
    def in_position(self) -> bool:
        return self.position > 0

    def buy(self, price: float) -> None:
        qty  = position_size(self.balance, price)
        cost = qty * price
        if cost > self.balance:
            logger.warning("Balance insuffisante: %.2f USDT requis, %.2f disponible", cost, self.balance)
            return
        self.balance     -= cost
        self.position     = qty
        self.entry_price  = price
        self.sl_price     = stop_loss_price(price)
        self.tp_price     = take_profit_price(price)
        self.trade_count += 1
        log_trade("BUY", config.SYMBOL, price, qty, self.balance)
        logger.info("  SL=%.2f  |  TP=%.2f", self.sl_price, self.tp_price)

    def sell(self, price: float, reason: str = "SIGNAL") -> None:
        pnl = (price - self.entry_price) * self.position
        self.balance += self.position * price
        log_trade("SELL", config.SYMBOL, price, self.position, self.balance)
        logger.info("  Exit=%-12s  PnL=%+.2f USDT", reason, pnl)
        self.position    = 0.0
        self.entry_price = 0.0

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.entry_price) * self.position if self.in_position else 0.0

    def portfolio_value(self, price: float) -> float:
        return self.balance + self.position * price


# ── Dashboard display ─────────────────────────────────────────────────────────

def _pct_str(pct: float) -> str:
    col = _G if pct >= 0 else _R
    sign = "+" if pct >= 0 else ""
    return f"{col}{sign}{pct:.2f}%{_RST}"


def display_dashboard(
    price:      float,
    prev_price: float,
    rsi:        float,
    signal:     str,
    action:     str,
    trader:     PaperTrader,
) -> None:
    now = datetime.now(timezone.utc)
    nxt = now + timedelta(seconds=config.LOOP_INTERVAL)
    now_s = now.strftime("%Y-%m-%d  %H:%M:%S UTC")
    nxt_s = nxt.strftime("%H:%M UTC")

    zone_lbl, zone_col = _rsi_zone(rsi)
    price_pct  = (price - prev_price) / prev_price * 100 if prev_price else 0.0
    price_col  = _G if price_pct >= 0 else _R
    pnl        = trader.unrealized_pnl(price)
    portfolio  = trader.portfolio_value(price)
    total_ret  = (portfolio - config.INITIAL_BALANCE) / config.INITIAL_BALANCE * 100

    # Signal color
    sig_col = {SIGNAL_BUY: _G, SIGNAL_SELL: _R}.get(signal, _D)

    # Action text + color
    _action_map = {
        "BUY":          (_G, ">>> BUY  — position ouverte <<<"),
        "SELL":         (_R, ">>> SELL — position fermée  <<<"),
        "STOP LOSS":    (_R, ">>> STOP LOSS  déclenché    <<<"),
        "TAKE PROFIT":  (_G, ">>> TAKE PROFIT atteint     <<<"),
    }
    act_col, act_txt = _action_map.get(action, (_D, "—  en attente"))

    W   = 54
    SEP = "═" * W
    LN  = "─" * W

    sign = "+" if price_pct >= 0 else ""
    price_chg = f"{price_col}({sign}{price_pct:.2f}%){_RST}"

    print(f"\n{_B}{SEP}{_RST}")
    print(f"{_B}  {config.SYMBOL}  |  PAPER TRADING  |  {now_s}{_RST}")
    print(f"{_B}{SEP}{_RST}")
    print(f"  Prix actuel    {_C}{_B}${price:>14,.2f}{_RST}   {price_chg}")
    print(f"  RSI ({config.RSI_PERIOD})       {zone_col}{_B}{rsi:>8.2f}{_RST}          {zone_col}[ {zone_lbl} ]{_RST}")
    print()
    print(_rsi_bar(rsi))
    print()
    print(f"  {LN}")
    print(f"  Signal         {sig_col}{_B}{signal:<10}{_RST}")
    print(f"  Action         {act_col}{_B}{act_txt}{_RST}")
    print(f"  {LN}")

    if trader.in_position:
        pnl_col  = _G if pnl >= 0 else _R
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_pct  = pnl / (trader.entry_price * trader.position) * 100
        print(f"  Position       {_B}{trader.position:.6f} BTC{_RST}")
        print(f"  Entry          ${trader.entry_price:>14,.2f}")
        print(f"  Stop-loss      {_R}${trader.sl_price:>14,.2f}{_RST}  "
              f"({_R}-{config.STOP_LOSS_PCT*100:.0f}%{_RST})")
        print(f"  Take-profit    {_G}${trader.tp_price:>14,.2f}{_RST}  "
              f"({_G}+{config.TAKE_PROFIT_PCT*100:.0f}%{_RST})")
        print(f"  PnL unrealisé  {pnl_col}{_B}{pnl_sign}{pnl:.2f} USDT  ({pnl_sign}{pnl_pct:.2f}%){_RST}")
    else:
        print(f"  Position       {_D}aucune{_RST}")

    print(f"  Balance        {_B}${trader.balance:>14,.2f} USDT{_RST}")
    ret_col = _G if total_ret >= 0 else _R
    print(f"  Portfolio      {ret_col}{_B}${portfolio:>14,.2f} USDT{_RST}   {_pct_str(total_ret)}")
    print(f"  Trades         {trader.trade_count}")
    print(f"  {LN}")
    print(f"  {_D}Prochain check : {nxt_s}  (dans {config.LOOP_INTERVAL // 60} min)  |  Ctrl+C pour arrêter{_RST}")
    print(f"{_B}{SEP}{_RST}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_bot() -> None:
    config.validate()
    quiet_console()  # logs → file only; dashboard handles console output

    logger.info("=" * 60)
    logger.info("START | %s | PAPER | RSI(%d) | %s | loop=%ds",
                config.SYMBOL, config.RSI_PERIOD, config.TIMEFRAME, config.LOOP_INTERVAL)
    logger.info("=" * 60)

    trader: PaperTrader = PaperTrader(config.INITIAL_BALANCE)
    prev_price: float | None = None
    iteration = 0

    print(f"\n{_B}{'━' * 54}{_RST}")
    print(f"{_B}  BOT DÉMARRÉ — {config.SYMBOL} PAPER TRADING{_RST}")
    print(f"  RSI({config.RSI_PERIOD})  |  {config.TIMEFRAME}  |  "
          f"SL -{config.STOP_LOSS_PCT*100:.0f}%  TP +{config.TAKE_PROFIT_PCT*100:.0f}%  "
          f"|  boucle {config.LOOP_INTERVAL // 60} min")
    print(f"  Balance initiale : ${config.INITIAL_BALANCE:,.2f} USDT")
    print(f"  Source données   : Kraken (lecture seule — aucune clé API)")
    print(f"{_B}{'━' * 54}{_RST}\n")

    while True:
        try:
            iteration += 1
            df            = fetch_ohlcv()
            ticker        = fetch_ticker()
            current_price = float(ticker["last"])
            if prev_price is None:
                prev_price = current_price

            action = "—"

            # ── SL / TP first ─────────────────────────────────────────────
            if trader.in_position:
                reason = check_exit(current_price, trader.entry_price)
                if reason:
                    trader.sell(current_price, reason=reason)
                    action = reason.replace("_", " ")

            # ── RSI signal ────────────────────────────────────────────────
            rsi    = get_latest_rsi(df)
            signal = get_signal(df)

            if action == "—":
                if signal == SIGNAL_BUY and not trader.in_position:
                    trader.buy(current_price)
                    action = "BUY"
                elif signal == SIGNAL_SELL and trader.in_position:
                    trader.sell(current_price, reason="RSI_SIGNAL")
                    action = "SELL"

            display_dashboard(current_price, prev_price, rsi, signal, action, trader)
            prev_price = current_price

        except KeyboardInterrupt:
            print(f"\n{_Y}Bot arrêté par l'utilisateur après {iteration} itération(s).{_RST}")
            try:
                t  = fetch_ticker()
                pv = trader.portfolio_value(float(t["last"]))
                ret = (pv - config.INITIAL_BALANCE) / config.INITIAL_BALANCE * 100
                sign = "+" if ret >= 0 else ""
                col  = _G if ret >= 0 else _R
                print(f"Portfolio final : {col}{_B}${pv:,.2f} USDT  ({sign}{ret:.2f}%){_RST}")
            except Exception:
                pass
            logger.info("Bot stopped after %d iterations.", iteration)
            break

        except Exception as exc:
            logger.error("Erreur itération %d : %s", iteration, exc, exc_info=True)
            print(f"{_R}Erreur : {exc}{_RST}  — nouvelle tentative dans {config.LOOP_INTERVAL}s")

        time.sleep(config.LOOP_INTERVAL)


if __name__ == "__main__":
    run_bot()
