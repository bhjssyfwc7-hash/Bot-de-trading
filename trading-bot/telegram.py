"""
Telegram notification module for the scalping bot.

Required .env vars:
    TELEGRAM_TOKEN   = token from @BotFather
    TELEGRAM_CHAT_ID = your numeric chat/channel id

All notify_* functions are no-ops when Telegram is not configured.
"""

from __future__ import annotations

import urllib3
import requests
from datetime import datetime, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import config
from logger import logger

_API = "https://api.telegram.org/bot{token}/sendMessage"


# ── Base sender ───────────────────────────────────────────────────────────────

def send_alert(text: str) -> bool:
    """
    POST a HTML-formatted message to the configured Telegram chat.
    Returns True on success, False on error (never raises).
    """
    if not config.TELEGRAM_ENABLED:
        return False
    try:
        r = requests.post(
            _API.format(token=config.TELEGRAM_TOKEN),
            json={
                "chat_id":    config.TELEGRAM_CHAT_ID,
                "text":       text,
                "parse_mode": "HTML",
            },
            timeout=10,
            verify=False,
        )
        if not r.ok:
            desc = r.json().get("description", r.text[:120])
            logger.warning("Telegram error %s: %s", r.status_code, desc)
            return False
        return True
    except Exception as exc:
        logger.warning("Telegram unavailable: %s", exc)
        return False


# ── Event notifications ───────────────────────────────────────────────────────

def notify_start(balance: float) -> None:
    """Sent once when the bot starts."""
    send_alert(
        f"🤖 <b>SCALPING BOT DÉMARRÉ</b>\n"
        f"\n"
        f"Symbole      : <code>{config.SYMBOL}</code>\n"
        f"Timeframe    : <code>{config.TIMEFRAME}</code>\n"
        f"Stratégie    : RSI({config.RSI_PERIOD}) + EMA({config.EMA_FAST}/{config.EMA_SLOW})\n"
        f"SL / TP      : <code>-{config.STOP_LOSS_PCT*100:.1f}% / +{config.TAKE_PROFIT_PCT*100:.1f}%</code>"
        f"  (ratio 2:1)\n"
        f"Capital/trade: <code>{config.CAPITAL_PER_TRADE*100:.0f}%</code>"
        f"  —  max <code>{config.MAX_POSITIONS}</code> positions\n"
        f"Stop journée : <code>-{config.MAX_DAILY_LOSS_PCT*100:.0f}%</code>\n"
        f"\n"
        f"💼 Balance initiale : <code>${balance:,.2f} USDT</code>\n"
        f"📄 Mode : <b>PAPER TRADING</b>"
    )


def notify_buy(pos, price: float, rsi: float, portfolio: float) -> None:
    """
    pos must expose: id, qty, entry_price, sl_price, tp_price, cost, entry_time
    """
    risk_usdt = (pos.entry_price - pos.sl_price) * pos.qty
    reward_usdt = (pos.tp_price - pos.entry_price) * pos.qty
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    send_alert(
        f"🟢 <b>BUY — {config.SYMBOL}</b>  #{pos.id}\n"
        f"\n"
        f"Prix d'entrée : <code>${pos.entry_price:,.2f}</code>\n"
        f"RSI ({config.RSI_PERIOD})        : <code>{rsi:.1f}</code>"
        f"  {'🔻 survente' if rsi < config.RSI_OVERSOLD else ''}\n"
        f"EMA cross     : haussier ✅\n"
        f"\n"
        f"💰 Capital engagé : <code>{pos.cost:.2f} USDT</code>"
        f"  ({config.CAPITAL_PER_TRADE*100:.0f}% portfolio)\n"
        f"🛡 Stop-loss      : <code>${pos.sl_price:,.2f}</code>"
        f"  (-{config.STOP_LOSS_PCT*100:.1f}%)"
        f"  ⟹ <code>-{risk_usdt:.4f} USDT</code>\n"
        f"🎯 Take-profit    : <code>${pos.tp_price:,.2f}</code>"
        f"  (+{config.TAKE_PROFIT_PCT*100:.1f}%)"
        f"  ⟹ <code>+{reward_usdt:.4f} USDT</code>\n"
        f"\n"
        f"💼 Portfolio : <code>${portfolio:,.2f} USDT</code>\n"
        f"🕐 {now}"
    )


def notify_sell(pos, price: float, pnl: float, reason: str,
                portfolio: float, total_ret_pct: float) -> None:
    """SELL via RSI/EMA signal — position closed at market."""
    age_min  = int((datetime.now(timezone.utc) - pos.entry_time).total_seconds() // 60)
    pnl_pct  = (price / pos.entry_price - 1) * 100
    pnl_sign = "+" if pnl >= 0 else ""
    ret_sign = "+" if total_ret_pct >= 0 else ""
    send_alert(
        f"🔴 <b>VENTE — {config.SYMBOL}</b>  #{pos.id}\n"
        f"\n"
        f"Prix de sortie : <code>${price:,.2f}</code>\n"
        f"Prix d'entrée  : <code>${pos.entry_price:,.2f}</code>\n"
        f"PnL            : <code>{pnl_sign}{pnl:.4f} USDT"
        f"  ({pnl_sign}{pnl_pct:.2f}%)</code>\n"
        f"\n"
        f"📌 Durée : {age_min} min  |  Raison : {reason}\n"
        f"💼 Portfolio : <code>${portfolio:,.2f} USDT</code>"
        f"  ({ret_sign}{total_ret_pct:.2f}%)"
    )


def notify_take_profit(pos, price: float, pnl: float,
                       portfolio: float, total_ret_pct: float) -> None:
    """TAKE PROFIT hit — target reached."""
    age_min  = int((datetime.now(timezone.utc) - pos.entry_time).total_seconds() // 60)
    pnl_pct  = (price / pos.entry_price - 1) * 100
    ret_sign = "+" if total_ret_pct >= 0 else ""
    send_alert(
        f"🔴 <b>TAKE PROFIT ✅ — {config.SYMBOL}</b>  #{pos.id}\n"
        f"\n"
        f"Prix de sortie : <code>${price:,.2f}</code>\n"
        f"Prix d'entrée  : <code>${pos.entry_price:,.2f}</code>\n"
        f"PnL            : <code>+{pnl:.4f} USDT  (+{pnl_pct:.2f}%)</code> 🎯\n"
        f"\n"
        f"📌 Durée : {age_min} min\n"
        f"💼 Portfolio : <code>${portfolio:,.2f} USDT</code>"
        f"  ({ret_sign}{total_ret_pct:.2f}%)"
    )


def notify_stop_loss(pos, price: float, loss: float,
                     portfolio: float, total_ret_pct: float) -> None:
    """STOP-LOSS hit — loss capped."""
    age_min  = int((datetime.now(timezone.utc) - pos.entry_time).total_seconds() // 60)
    loss_pct = (price / pos.entry_price - 1) * 100
    ret_sign = "+" if total_ret_pct >= 0 else ""
    send_alert(
        f"🛑 <b>STOP-LOSS — {config.SYMBOL}</b>  #{pos.id}\n"
        f"\n"
        f"Prix touché    : <code>${price:,.2f}</code>\n"
        f"Prix d'entrée  : <code>${pos.entry_price:,.2f}</code>\n"
        f"Perte          : <code>{loss:.4f} USDT  ({loss_pct:.2f}%)</code>\n"
        f"\n"
        f"📌 Durée : {age_min} min\n"
        f"💼 Portfolio : <code>${portfolio:,.2f} USDT</code>"
        f"  ({ret_sign}{total_ret_pct:.2f}%)"
    )


def notify_circuit_breaker(daily_pnl_pct: float, portfolio: float) -> None:
    """Daily loss limit reached — bot paused until next UTC day."""
    send_alert(
        f"⚠️ <b>COUPE-CIRCUIT ACTIVÉ — {config.SYMBOL}</b>\n"
        f"\n"
        f"Perte journalière : <code>{daily_pnl_pct:+.2f}%</code>"
        f"  (limite : <code>-{config.MAX_DAILY_LOSS_PCT*100:.0f}%</code>)\n"
        f"Portfolio         : <code>${portfolio:,.2f} USDT</code>\n"
        f"\n"
        f"🔒 Bot en <b>PAUSE</b> jusqu'à demain 00:00 UTC\n"
        f"Aucun nouveau trade ne sera ouvert."
    )


def notify_daily_summary(stats: dict) -> None:
    """
    Midnight summary. stats keys:
        date, trades, wins, losses, total_pnl,
        start_balance, end_balance, best_trade, worst_trade
    """
    n       = stats.get("trades", 0)
    wins    = stats.get("wins", 0)
    losses  = stats.get("losses", 0)
    pnl     = stats.get("total_pnl", 0.0)
    start   = stats.get("start_balance", 0.0)
    end     = stats.get("end_balance", 0.0)
    best    = stats.get("best_trade", 0.0)
    worst   = stats.get("worst_trade", 0.0)
    date_s  = stats.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    wr      = wins / n * 100 if n else 0.0
    pnl_pct = (end - start) / start * 100 if start else 0.0
    icon    = "📈" if pnl >= 0 else "📉"
    sign    = "+" if pnl >= 0 else ""

    send_alert(
        f"📊 <b>RÉSUMÉ QUOTIDIEN — {date_s}</b>  {icon}\n"
        f"\n"
        f"Trades    : <code>{n}</code>"
        f"  (✅ W:{wins}  ❌ L:{losses}  —  WR {wr:.0f}%)\n"
        f"PnL total : <code>{sign}{pnl:.4f} USDT  ({sign}{pnl_pct:.2f}%)</code>\n"
        f"\n"
        f"Portfolio début : <code>${start:,.2f} USDT</code>\n"
        f"Portfolio fin   : <code>${end:,.2f} USDT</code>\n"
        f"\n"
        f"🏆 Meilleur trade : <code>+{best:.4f} USDT</code>\n"
        f"💀 Pire trade     : <code>{worst:+.4f} USDT</code>"
    )
