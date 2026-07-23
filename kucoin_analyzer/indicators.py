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


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """Wykładnicza średnia krocząca (EMA) jako seria.

    Zwraca listę tej samej długości co `values`; pierwsze period-1 pozycji
    to None (za mało danych). Zalążek = SMA z pierwszych `period` wartości.
    """
    if period <= 0 or len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out: list[float | None] = [None] * (period - 1) + [seed]
    ema = seed
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out


def macd(
    candles: Sequence[Sequence[float]],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, float] | None:
    """MACD (Moving Average Convergence Divergence).

    Zwraca dict: macd, signal, hist, prev_hist.
      - hist > 0 -> momentum byczy (linia MACD nad linią sygnału)
      - zmiana znaku hist (prev_hist -> hist) sygnalizuje przecięcie
    Zwraca None, jeśli za mało danych.
    """
    prices = closes(candles)
    if len(prices) < slow + signal:
        return None

    ema_fast = ema_series(prices, fast)
    ema_slow = ema_series(prices, slow)
    macd_line = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    macd_vals = [m for m in macd_line if m is not None]
    if len(macd_vals) < signal + 1:
        return None

    signal_series = ema_series(macd_vals, signal)
    macd_last = macd_vals[-1]
    signal_last = signal_series[-1]
    if signal_last is None:
        return None
    hist = macd_last - signal_last

    prev_hist = None
    if len(macd_vals) >= 2 and signal_series[-2] is not None:
        prev_hist = macd_vals[-2] - signal_series[-2]

    return {
        "macd": macd_last,
        "signal": signal_last,
        "hist": hist,
        "prev_hist": prev_hist if prev_hist is not None else hist,
    }


def bollinger(
    candles: Sequence[Sequence[float]],
    period: int = 20,
    num_std: float = 2.0,
) -> dict[str, float] | None:
    """Wstęgi Bollingera.

    Zwraca dict: upper, middle, lower, bandwidth_pct, percent_b.
      - bandwidth_pct = (upper-lower)/middle*100 -> miara zmienności/ściśnięcia
      - percent_b = (cena-lower)/(upper-lower): 0=dolna, 1=górna wstęga
        (>1 wybicie górą / wykupienie, <0 wybicie dołem / wyprzedanie)
    Zwraca None, jeśli za mało danych.
    """
    prices = closes(candles)
    if len(prices) < period:
        return None

    window = prices[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    sd = variance ** 0.5
    upper = mid + num_std * sd
    lower = mid - num_std * sd
    last = prices[-1]

    bandwidth = (upper - lower) / mid * 100.0 if mid else None
    percent_b = (last - lower) / (upper - lower) if upper != lower else 0.5

    return {
        "upper": upper,
        "middle": mid,
        "lower": lower,
        "bandwidth_pct": bandwidth,
        "percent_b": percent_b,
    }
