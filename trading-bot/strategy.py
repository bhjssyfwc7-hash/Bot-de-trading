import pandas as pd
from config import config
from logger import logger

SIGNAL_BUY  = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_HOLD = "HOLD"


# ── Indicators ────────────────────────────────────────────────────────────────

def compute_rsi(df: pd.DataFrame) -> pd.Series:
    """Wilder's RSI via exponential smoothing."""
    period   = config.RSI_PERIOD
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def compute_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()


# ── Combined scalping signal ──────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> dict:
    """
    Compute RSI + EMA crossover and return a full state dict.

    BUY  = RSI < RSI_OVERSOLD  AND EMA_FAST crosses above EMA_SLOW
    SELL = RSI > RSI_OVERBOUGHT AND EMA_FAST crosses below EMA_SLOW
    """
    df = df.copy()
    df["rsi"]      = compute_rsi(df)
    df["ema_fast"] = compute_ema(df, config.EMA_FAST)
    df["ema_slow"] = compute_ema(df, config.EMA_SLOW)

    rsi      = df["rsi"].iloc[-1]
    ef_now   = df["ema_fast"].iloc[-1]
    ef_prev  = df["ema_fast"].iloc[-2]
    es_now   = df["ema_slow"].iloc[-1]
    es_prev  = df["ema_slow"].iloc[-2]

    # Crossover on last two candles
    if ef_prev < es_prev and ef_now >= es_now:
        cross = "bullish"
    elif ef_prev > es_prev and ef_now <= es_now:
        cross = "bearish"
    else:
        cross = None

    # ema_trend: ongoing relationship (independent of crossover event)
    ema_trend = "bullish" if ef_now > es_now else ("bearish" if ef_now < es_now else "neutral")

    # Combined conditions
    if rsi < config.RSI_OVERSOLD and cross == "bullish":
        signal = SIGNAL_BUY
    elif rsi > config.RSI_OVERBOUGHT and cross == "bearish":
        signal = SIGNAL_SELL
    else:
        signal = SIGNAL_HOLD

    logger.info(
        "TICK | %s | RSI=%.1f | EMA%d=%.2f | EMA%d=%.2f | cross=%-8s | %s",
        config.SYMBOL, rsi,
        config.EMA_FAST, ef_now,
        config.EMA_SLOW, es_now,
        cross or "none", signal,
    )

    return {
        "rsi":       rsi,
        "ema_fast":  ef_now,
        "ema_slow":  es_now,
        "cross":     cross,       # "bullish" | "bearish" | None  — event this tick
        "ema_trend": ema_trend,   # "bullish" | "bearish" | "neutral" — ongoing
        "signal":    signal,
    }


# ── Backward-compatible wrappers (used by backtest.py) ───────────────────────

def get_signal(df: pd.DataFrame) -> str:
    return compute_indicators(df)["signal"]


def get_latest_rsi(df: pd.DataFrame) -> float:
    return compute_rsi(df).iloc[-1]
