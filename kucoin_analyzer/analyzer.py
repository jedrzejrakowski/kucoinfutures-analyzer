"""Orkiestracja analizy: pobranie danych -> metryki -> ranking."""

from __future__ import annotations

from typing import Callable

from . import indicators
from .api import KucoinFuturesClient
from .scoring import PairMetrics, rank_pairs


def _f(value, default: float = 0.0) -> float:
    """Bezpieczna konwersja na float (pola API bywają str/None)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_metrics_from_contract(c: dict) -> PairMetrics:
    """Buduje metryki z pojedynczego rekordu /contracts/active (dane 24h).

    Zmienność liczona jest tu jako zakres 24h: (high-low)/price * 100.
    Zostanie nadpisana przez ATR%, jeśli włączymy analizę świec.
    """
    price = _f(c.get("lastTradePrice") or c.get("markPrice"))
    high = _f(c.get("highPrice"))
    low = _f(c.get("lowPrice"))
    range_pct = ((high - low) / price * 100.0) if price and high and low else None

    return PairMetrics(
        symbol=c.get("symbol", "?"),
        price=price,
        change_24h_pct=_f(c.get("priceChgPct")) * 100.0,  # API daje ułamek
        turnover_24h=_f(c.get("turnoverOf24h")),
        funding_rate=_f(c.get("fundingFeeRate")),
        volatility=range_pct,
    )


def analyze(
    client: KucoinFuturesClient | None = None,
    quote: str = "USDT",
    candidates: int = 60,
    use_klines: bool = True,
    granularity: int = 60,
    lookback: int = 100,
    weights: dict[str, float] | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[PairMetrics]:
    """Zwraca posortowaną listę PairMetrics (najwyższa ocena pierwsza).

    Kroki:
      1. Pobierz aktywne kontrakty (1 wywołanie API).
      2. Odfiltruj po walucie kwotowanej (domyślnie USDT) i statusie Open.
      3. Wstępnie posortuj po obrocie 24h; weź `candidates` najlepszych.
      4. (opcjonalnie) Dla kandydatów pobierz świece i policz ATR% + RSI.
      5. Zbuduj ranking ważoną punktacją.
    """
    client = client or KucoinFuturesClient()

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    log("Pobieram listę aktywnych kontraktów...")
    contracts = client.active_contracts()

    filtered = [
        c
        for c in contracts
        if str(c.get("quoteCurrency", "")).upper() == quote.upper()
        and str(c.get("status", "Open")).lower() == "open"
    ]
    log(f"Znaleziono {len(filtered)} kontraktów {quote}.")

    metrics = [build_metrics_from_contract(c) for c in filtered]
    # Kandydaci: najbardziej płynne pary (największy obrót 24h).
    metrics.sort(key=lambda m: m.turnover_24h, reverse=True)
    if candidates > 0:
        metrics = metrics[:candidates]

    if use_klines:
        log(f"Pobieram świece dla {len(metrics)} par (ATR%, RSI, MACD, Bollinger)...")
        for i, m in enumerate(metrics, 1):
            try:
                candles = client.klines(m.symbol, granularity, lookback)
            except Exception:  # noqa: BLE001 - pojedyncza para nie może zabić całości
                candles = []
            if candles:
                atr = indicators.atr_pct(candles)
                if atr is not None:
                    m.volatility = atr  # dokładniejsza miara niż zakres 24h
                m.rsi = indicators.rsi(candles)
                m.momentum_change_pct = indicators.price_change_pct(candles)
                macd = indicators.macd(candles)
                if macd is not None:
                    m.macd_hist = macd["hist"]
                bb = indicators.bollinger(candles)
                if bb is not None:
                    m.bb_percent_b = bb["percent_b"]
                    m.bb_bandwidth_pct = bb["bandwidth_pct"]
            if progress and i % 10 == 0:
                log(f"  ...{i}/{len(metrics)}")

    log("Buduję ranking...")
    return rank_pairs(metrics, weights)
