"""
Scalping Bot — Paper Trading  |  RSI(7) + EMA(9/21) crossover  |  BTC/USDT 1-min

Usage:
    python main.py
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from config import config
from data import fetch_ohlcv, fetch_ticker
from strategy import compute_indicators, SIGNAL_BUY, SIGNAL_SELL, SIGNAL_HOLD
from risk import (
    position_size, stop_loss_price, take_profit_price,
    check_exit, is_daily_loss_exceeded,
)
from logger import logger, log_trade, quiet_console

# ── ANSI palette ──────────────────────────────────────────────────────────────
_G   = "\033[92m"
_R   = "\033[91m"
_Y   = "\033[93m"
_C   = "\033[96m"
_B   = "\033[1m"
_D   = "\033[2m"
_RST = "\033[0m"


# ── Position dataclass ────────────────────────────────────────────────────────

@dataclass
class Position:
    id:          int
    qty:         float
    entry_price: float
    sl_price:    float
    tp_price:    float
    entry_time:  datetime
    cost:        float          # USDT locked in when opened

    def pnl(self, price: float) -> float:
        return (price - self.entry_price) * self.qty

    def pnl_pct(self, price: float) -> float:
        return (price / self.entry_price - 1) * 100


# ── Scalping trader ───────────────────────────────────────────────────────────

class ScalpingTrader:
    def __init__(self, initial_balance: float) -> None:
        self.balance              = initial_balance
        self.positions: list[Position] = []
        self._pos_counter         = 0
        self.trade_count          = 0
        self.wins                 = 0
        self.losses               = 0
        self.total_realized_pnl   = 0.0
        self.daily_start_balance  = initial_balance
        self.daily_start_date     = datetime.now(timezone.utc).date()
        self.paused               = False
        self._pause_reason        = ""

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def portfolio_value(self, price: float) -> float:
        return self.balance + sum(p.qty * price for p in self.positions)

    def daily_pnl_pct(self, price: float) -> float:
        return (self.portfolio_value(price) - self.daily_start_balance) / self.daily_start_balance

    # ── Daily guards ──────────────────────────────────────────────────────────

    def check_daily_reset(self, price: float) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.daily_start_date:
            self.daily_start_balance = self.portfolio_value(price)
            self.daily_start_date    = today
            if self.paused and "daily" in self._pause_reason:
                self.paused       = False
                self._pause_reason = ""
                logger.info("Nouveau jour — pause journalière levée. Balance : %.2f USDT",
                            self.daily_start_balance)

    def check_daily_loss_limit(self, price: float) -> None:
        if not self.paused and is_daily_loss_exceeded(
            self.portfolio_value(price), self.daily_start_balance
        ):
            self.paused        = True
            self._pause_reason = "daily loss limit"
            logger.warning(
                "Limite journalière atteinte : %.2f%% — bot en PAUSE jusqu'à demain.",
                self.daily_pnl_pct(price) * 100,
            )

    # ── Open / close ──────────────────────────────────────────────────────────

    @property
    def can_open(self) -> bool:
        return (
            not self.paused
            and len(self.positions) < config.MAX_POSITIONS
            and self.balance > 0
        )

    def open_position(self, price: float) -> "Position | None":
        if not self.can_open:
            return None
        pv      = self.portfolio_value(price)
        capital = min(pv * config.CAPITAL_PER_TRADE, self.balance * 0.98)
        qty     = capital / price
        cost    = qty * price
        if cost <= 0 or cost > self.balance:
            return None

        self._pos_counter += 1
        pos = Position(
            id          = self._pos_counter,
            qty         = qty,
            entry_price = price,
            sl_price    = stop_loss_price(price),
            tp_price    = take_profit_price(price),
            entry_time  = datetime.now(timezone.utc),
            cost        = cost,
        )
        self.balance -= cost
        self.positions.append(pos)
        self.trade_count += 1
        log_trade("BUY", config.SYMBOL, price, qty, self.balance)
        logger.info("  #%d | SL=%.2f | TP=%.2f | capital=%.2f USDT",
                    pos.id, pos.sl_price, pos.tp_price, cost)
        return pos

    def close_position(self, pos: Position, price: float, reason: str) -> float:
        pnl = pos.pnl(price)
        self.balance += pos.qty * price
        self.total_realized_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.positions.remove(pos)
        log_trade("SELL", config.SYMBOL, price, pos.qty, self.balance)
        logger.info("  #%d | %s | PnL=%+.4f USDT", pos.id, reason, pnl)
        return pnl

    def check_exits(self, price: float) -> list[tuple[Position, str, float]]:
        """Check SL/TP for every open position. Returns list of closed ones."""
        closed: list[tuple[Position, str, float]] = []
        for pos in list(self.positions):
            reason = check_exit(price, pos.entry_price)
            if reason:
                pnl = self.close_position(pos, price, reason)
                closed.append((pos, reason.replace("_", " "), pnl))
        return closed

    def close_all(self, price: float, reason: str = "RSI_SIGNAL") -> float:
        total = 0.0
        for pos in list(self.positions):
            total += self.close_position(pos, price, reason)
        return total


# ── RSI bar ───────────────────────────────────────────────────────────────────

def _rsi_zone(rsi: float) -> tuple[str, str]:
    if rsi < config.RSI_OVERSOLD:   return "SURVENTE", _G
    if rsi > config.RSI_OVERBOUGHT: return "SURACHAT", _R
    if rsi < 50:                    return "baissier", _Y
    if rsi > 50:                    return "haussier", _C
    return "neutre", _D


def _rsi_bar(rsi: float, w: int = 48) -> str:
    pos  = min(int(rsi / 100 * w), w - 1)
    lo   = int(config.RSI_OVERSOLD  / 100 * w)
    hi   = int(config.RSI_OVERBOUGHT / 100 * w)
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

    lo_s  = f"{config.RSI_OVERSOLD:.0f}%"
    hi_s  = f"{config.RSI_OVERBOUGHT:.0f}%"
    gap   = hi - lo - len(f" {lo_s} ")
    hi_r  = w - hi - len(f" {hi_s}") - 1
    axis  = (f"{_D}  0%"
             f"{'':>{lo - 2}} {lo_s}"
             f"{'':>{max(gap, 1)}} {hi_s}"
             f"{'':>{max(hi_r, 1)}} 100%{_RST}")
    return "  [" + "".join(chars) + "]\n" + axis


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _pct(pct: float, bold: bool = False) -> str:
    col  = _G if pct >= 0 else _R
    sign = "+" if pct >= 0 else ""
    b    = _B if bold else ""
    return f"{col}{b}{sign}{pct:.2f}%{_RST}"


def _ema_status(ind: dict) -> str:
    ef, es   = ind["ema_fast"], ind["ema_slow"]
    trend    = ind["ema_trend"]
    cross    = ind["cross"]

    if trend == "bullish":
        trend_str = f"{_G}EMA{config.EMA_FAST} > EMA{config.EMA_SLOW}  haussier{_RST}"
    elif trend == "bearish":
        trend_str = f"{_R}EMA{config.EMA_FAST} < EMA{config.EMA_SLOW}  baissier{_RST}"
    else:
        trend_str = f"{_D}EMA{config.EMA_FAST} = EMA{config.EMA_SLOW}  neutre{_RST}"

    if cross == "bullish":
        cross_str = f"  {_G}{_B}*** CROSS HAUSSIER ***{_RST}"
    elif cross == "bearish":
        cross_str = f"  {_R}{_B}*** CROSS BAISSIER ***{_RST}"
    else:
        cross_str = ""

    return (
        f"  EMA({config.EMA_FAST})     ${ef:>12,.2f}\n"
        f"  EMA({config.EMA_SLOW})     ${es:>12,.2f}   {trend_str}{cross_str}"
    )


def display_dashboard(
    price:      float,
    prev_price: float,
    ind:        dict,
    action:     str,
    closed:     list,
    trader:     ScalpingTrader,
) -> None:
    now   = datetime.now(timezone.utc)
    nxt   = now + timedelta(seconds=config.LOOP_INTERVAL)
    now_s = now.strftime("%Y-%m-%d  %H:%M:%S UTC")
    nxt_s = nxt.strftime("%H:%M:%S UTC")

    signal       = ind["signal"]
    rsi          = ind["rsi"]
    zone_lbl, zone_col = _rsi_zone(rsi)
    price_pct    = (price - prev_price) / prev_price * 100 if prev_price else 0.0
    price_col    = _G if price_pct >= 0 else _R
    portfolio    = trader.portfolio_value(price)
    total_ret    = (portfolio - config.INITIAL_BALANCE) / config.INITIAL_BALANCE * 100
    daily_pct    = trader.daily_pnl_pct(price) * 100

    sig_col = {SIGNAL_BUY: _G, SIGNAL_SELL: _R}.get(signal, _D)

    _act_map = {
        "BUY":          (_G, f">>> BUY  #{trader._pos_counter} ouvert          <<<"),
        "SELL":         (_R, ">>> SELL  — positions fermées     <<<"),
        "STOP LOSS":    (_R, ">>> STOP LOSS  déclenché          <<<"),
        "TAKE PROFIT":  (_G, ">>> TAKE PROFIT atteint           <<<"),
        "MULTI EXIT":   (_Y, ">>> MULTI-EXIT (SL+TP)            <<<"),
    }
    act_col, act_txt = _act_map.get(action, (_D, "—  en attente"))

    pause_str = (f"  {_R}{_B}BOT EN PAUSE ({trader._pause_reason}){_RST}\n"
                 if trader.paused else "")

    W   = 58
    SEP = "═" * W
    LN  = "─" * W

    price_sign = "+" if price_pct >= 0 else ""

    print(f"\n{_B}{SEP}{_RST}")
    print(f"{_B}  {config.SYMBOL}  SCALPING  1-min  |  {now_s}{_RST}")
    print(f"{_B}{SEP}{_RST}")

    # Price
    print(f"  Prix actuel    {_C}{_B}${price:>14,.2f}{_RST}"
          f"   {price_col}({price_sign}{price_pct:.3f}%){_RST}")

    # RSI
    print(f"  RSI ({config.RSI_PERIOD})         {zone_col}{_B}{rsi:>8.2f}{_RST}"
          f"         {zone_col}[ {zone_lbl} ]{_RST}")
    print(_rsi_bar(rsi))

    # EMA
    print()
    print(_ema_status(ind))
    print()

    # Signal / action
    print(f"  {LN}")
    print(f"  Signal         {sig_col}{_B}{signal}{_RST}")
    print(f"  Action         {act_col}{_B}{act_txt}{_RST}")

    # Closed-this-tick summary
    if closed:
        for pos, reason, pnl in closed:
            pnl_col = _G if pnl >= 0 else _R
            pnl_sign = "+" if pnl >= 0 else ""
            print(f"  {_D}  └─ #{pos.id} {reason:<12} PnL={pnl_col}{pnl_sign}{pnl:.4f} USDT{_RST}")

    print(f"  {LN}")

    # Daily + pause status
    daily_col = _G if daily_pct >= 0 else _R
    daily_sign = "+" if daily_pct >= 0 else ""
    print(f"  Journée        {daily_col}{_B}{daily_sign}{daily_pct:.2f}%{_RST}"
          f"   {_D}limite : -{config.MAX_DAILY_LOSS_PCT*100:.0f}%{_RST}")
    print(pause_str, end="")

    # Open positions
    n_pos = len(trader.positions)
    print(f"  Positions      {_B}{n_pos}/{config.MAX_POSITIONS} ouvertes{_RST}")
    if trader.positions:
        for pos in trader.positions:
            pnl     = pos.pnl(price)
            pnl_col = _G if pnl >= 0 else _R
            age     = int((datetime.now(timezone.utc) - pos.entry_time).total_seconds() // 60)
            pnl_sign = "+" if pnl >= 0 else ""
            print(f"  {_D}  #{pos.id:<3} {pos.qty:.6f} BTC"
                  f"  @${pos.entry_price:,.2f}"
                  f"  SL=${pos.sl_price:,.2f}"
                  f"  TP=${pos.tp_price:,.2f}"
                  f"  PnL={pnl_col}{pnl_sign}{pnl:.4f}{_RST}"
                  f"{_D}  [{age}min]{_RST}")
    print(f"  {LN}")

    # Portfolio
    print(f"  Balance        {_B}${trader.balance:>14,.2f} USDT{_RST}")
    print(f"  Portfolio      {(_G if total_ret >= 0 else _R)}{_B}${portfolio:>14,.2f} USDT{_RST}"
          f"   {_pct(total_ret, bold=True)}")
    win_rate = trader.wins / trader.trade_count * 100 if trader.trade_count else 0
    print(f"  Trades         {trader.trade_count}"
          f"  {_D}(W:{trader.wins} L:{trader.losses}"
          f"  WR:{win_rate:.0f}%"
          f"  PnL:{'+' if trader.total_realized_pnl >= 0 else ''}{trader.total_realized_pnl:.4f} USDT){_RST}")
    print(f"  {LN}")
    print(f"  {_D}Prochain check : {nxt_s}  "
          f"(dans {config.LOOP_INTERVAL}s)  |  Ctrl+C pour arrêter{_RST}")
    print(f"{_B}{SEP}{_RST}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_bot() -> None:
    config.validate()
    quiet_console()

    logger.info("=" * 60)
    logger.info("SCALPING START | %s | RSI(%d) EMA(%d/%d) | %s | loop=%ds",
                config.SYMBOL, config.RSI_PERIOD,
                config.EMA_FAST, config.EMA_SLOW,
                config.TIMEFRAME, config.LOOP_INTERVAL)
    logger.info("SL=%.1f%%  TP=%.1f%%  capital/trade=%.0f%%  max_pos=%d  daily_limit=-%.0f%%",
                config.STOP_LOSS_PCT * 100, config.TAKE_PROFIT_PCT * 100,
                config.CAPITAL_PER_TRADE * 100, config.MAX_POSITIONS,
                config.MAX_DAILY_LOSS_PCT * 100)
    logger.info("=" * 60)

    trader:     ScalpingTrader    = ScalpingTrader(config.INITIAL_BALANCE)
    prev_price: float | None      = None
    iteration                     = 0

    print(f"\n{_B}{'━' * 58}{_RST}")
    print(f"{_B}  SCALPING BOT DÉMARRÉ — {config.SYMBOL}  |  {config.TIMEFRAME}{_RST}")
    print(f"  RSI({config.RSI_PERIOD})  EMA({config.EMA_FAST}/{config.EMA_SLOW})"
          f"  SL-{config.STOP_LOSS_PCT*100:.1f}%"
          f"  TP+{config.TAKE_PROFIT_PCT*100:.1f}%"
          f"  {config.CAPITAL_PER_TRADE*100:.0f}%/trade"
          f"  max {config.MAX_POSITIONS} pos"
          f"  boucle {config.LOOP_INTERVAL}s")
    print(f"  Balance initiale : ${config.INITIAL_BALANCE:,.2f} USDT")
    print(f"  Source données   : Kraken — lecture seule (aucune clé API)")
    print(f"{_B}{'━' * 58}{_RST}\n")

    while True:
        try:
            iteration    += 1
            df            = fetch_ohlcv()
            ticker        = fetch_ticker()
            current_price = float(ticker["last"])
            if prev_price is None:
                prev_price = current_price

            # ── Daily checks ───────────────────────────────────────────────
            trader.check_daily_reset(current_price)
            trader.check_daily_loss_limit(current_price)

            # ── SL / TP on all positions ───────────────────────────────────
            closed = trader.check_exits(current_price)

            # ── Strategy signal ────────────────────────────────────────────
            ind    = compute_indicators(df)
            signal = ind["signal"]
            action = "—"

            if closed:
                reasons = {r for _, r, _ in closed}
                action  = "MULTI EXIT" if len(reasons) > 1 else list(reasons)[0]

            if not trader.paused:
                if signal == SIGNAL_BUY and trader.can_open:
                    pos = trader.open_position(current_price)
                    if pos:
                        action = "BUY"

                elif signal == SIGNAL_SELL and trader.positions:
                    trader.close_all(current_price, reason="RSI_SIGNAL")
                    action = "SELL"

            display_dashboard(current_price, prev_price, ind, action, closed, trader)
            prev_price = current_price

        except KeyboardInterrupt:
            print(f"\n{_Y}Bot arrêté après {iteration} itération(s).{_RST}")
            try:
                t  = fetch_ticker()
                pv = trader.portfolio_value(float(t["last"]))
                ret = (pv - config.INITIAL_BALANCE) / config.INITIAL_BALANCE * 100
                sign = "+" if ret >= 0 else ""
                col  = _G if ret >= 0 else _R
                print(f"Portfolio final : {col}{_B}${pv:,.2f} USDT  ({sign}{ret:.2f}%){_RST}")
                print(f"Trades réalisés : {trader.trade_count}  "
                      f"(W:{trader.wins} L:{trader.losses}  "
                      f"PnL:{'+' if trader.total_realized_pnl >= 0 else ''}"
                      f"{trader.total_realized_pnl:.4f} USDT)")
            except Exception:
                pass
            logger.info("Bot stopped after %d iterations.", iteration)
            break

        except Exception as exc:
            logger.error("Erreur itération %d : %s", iteration, exc, exc_info=True)
            print(f"{_R}Erreur : {exc}{_RST}")

        time.sleep(config.LOOP_INTERVAL)


if __name__ == "__main__":
    run_bot()
