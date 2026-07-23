"""Wskaźniki techniczne liczone na świecach (bez zależności zewnętrznych).

Świeca ma format [time, open, high, low, close, volume].
"""

from __future__ import annotations

from typing import Sequence

OPEN, HIGH, LOW, CLOSE, VOLUME = 1, 2, 3, 4, 5


def closes(candles: Sequence[Sequence[float]]) -> list[float]:
    return [c[CLOSE] for c in candles]


def rsi(candles: Sequence[Sequence[float]], period: int = 14) -> float | None:
    """Wskaźnik RSI (Relative Strength Index), 0..100.

    RSI > 70 -> wykupienie (możliwa korekta w dół).
    RSI < 30 -> wyprzedanie (możliwe odbicie w górę).
    Wartość ~50 -> brak wyraźnego momentum.
    Zwraca None, jeśli za mało danych.
    """
    prices = closes(candles)
    if len(prices) < period + 1:
        return None

    gains = 0.0
    losses = 0.0
    # Pierwsza średnia z 'period' zmian.
    for i in range(1, period + 1):
        delta = prices[i] - prices[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period

    # Wygładzanie Wildera dla pozostałych świec.
    for i in range(period + 1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr_pct(candles: Sequence[Sequence[float]], period: int = 14) -> float | None:
    """Average True Range wyrażony jako % ostatniej ceny zamknięcia.

    Miara zmienności: ile średnio "rusza się" cena na świecę, względem
    poziomu ceny. Wyższa wartość = większa zmienność (potencjał i ryzyko).
    Zwraca None, jeśli za mało danych.
    """
    if len(candles) < period + 1:
        return None

    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i][HIGH]
        low = candles[i][LOW]
        prev_close = candles[i - 1][CLOSE]
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    last_close = candles[-1][CLOSE]
    if last_close == 0:
        return None
    return (atr / last_close) * 100.0


def price_change_pct(candles: Sequence[Sequence[float]]) -> float | None:
    """Zmiana ceny (%) od pierwszej do ostatniej świecy w oknie."""
    prices = closes(candles)
    if len(prices) < 2 or prices[0] == 0:
        return None
    return (prices[-1] - prices[0]) / prices[0] * 100.0
