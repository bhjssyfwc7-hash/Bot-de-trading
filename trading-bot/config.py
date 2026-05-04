import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Binance API credentials (unused in paper mode)
    API_KEY:    str = os.getenv("BINANCE_API_KEY", "")
    API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

    # Trading mode
    TRADING_MODE: str  = os.getenv("TRADING_MODE", "paper").lower()
    IS_PAPER:     bool = TRADING_MODE == "paper"

    # ── Market ────────────────────────────────────────────────────────────────
    SYMBOL:    str = os.getenv("SYMBOL",    "BTC/USDT")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1m")
    LIMIT:     int = 120   # 120 × 1-min candles — enough for EMA(21) warmup

    # ── Scalping indicators ───────────────────────────────────────────────────
    RSI_PERIOD:     int   = int(os.getenv("RSI_PERIOD",      7))
    RSI_OVERSOLD:   float = float(os.getenv("RSI_OVERSOLD",  35))
    RSI_OVERBOUGHT: float = float(os.getenv("RSI_OVERBOUGHT", 65))
    EMA_FAST:       int   = int(os.getenv("EMA_FAST", 9))
    EMA_SLOW:       int   = int(os.getenv("EMA_SLOW", 21))

    # ── Risk management ───────────────────────────────────────────────────────
    STOP_LOSS_PCT:      float = float(os.getenv("STOP_LOSS_PCT",      0.005))
    TAKE_PROFIT_PCT:    float = float(os.getenv("TAKE_PROFIT_PCT",    0.010))
    CAPITAL_PER_TRADE:  float = float(os.getenv("CAPITAL_PER_TRADE",  0.05))
    MAX_POSITIONS:      int   = int(os.getenv("MAX_POSITIONS",        3))
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("MAX_DAILY_LOSS_PCT", 0.03))
    INITIAL_BALANCE:    float = float(os.getenv("INITIAL_BALANCE",    1000.0))

    # Kept for backtest.py backward compatibility
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", 0.05))

    # ── Telegram notifications ────────────────────────────────────────────────
    TELEGRAM_TOKEN:   str  = os.getenv("TELEGRAM_TOKEN",   "")
    TELEGRAM_CHAT_ID: str  = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_ENABLED: bool = bool(
        os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")
    )

    # ── Loop ──────────────────────────────────────────────────────────────────
    LOOP_INTERVAL: int = int(os.getenv("LOOP_INTERVAL", 30))

    @classmethod
    def validate(cls) -> None:
        if not cls.IS_PAPER and (not cls.API_KEY or not cls.API_SECRET):
            raise ValueError("API keys required for live trading.")
        if cls.TRADING_MODE not in ("paper", "live"):
            raise ValueError("TRADING_MODE must be 'paper' or 'live'.")
        if not (0 < cls.CAPITAL_PER_TRADE <= 0.25):
            raise ValueError("CAPITAL_PER_TRADE must be between 0 and 0.25.")
        if not (0 < cls.MAX_DAILY_LOSS_PCT <= 0.20):
            raise ValueError("MAX_DAILY_LOSS_PCT must be between 0 and 0.20.")


config = Config()
