"""Punktacja i ranking par na podstawie metryk rynkowych.

Każda metryka jest normalizowana do zakresu 0..1 metodą rangi percentylowej
(odpornej na wartości odstające), a następnie łączona w ważoną
"ocenę potencjału" 0..100.

Metryki:
  - volatility  (zmienność, ATR% lub zakres 24h) -> większa = wyższa ocena
  - momentum    (siła trendu, |RSI-50| + |zmiana%|) -> większa = wyższa ocena
  - liquidity   (obrót 24h)                         -> większy = wyższa ocena
  - funding     (|funding rate|, sygnał zatłoczenia)-> większy = wyższa ocena

Kierunek (LONG/SHORT) jest sygnałem pomocniczym wyprowadzonym z RSI
i zmiany ceny — NIE jest gwarancją.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_WEIGHTS = {
    "volatility": 0.30,
    "momentum": 0.30,
    "liquidity": 0.25,
    "funding": 0.15,
}


@dataclass
class PairMetrics:
    """Surowe metryki jednej pary (kontraktu)."""

    symbol: str
    price: float = 0.0
    change_24h_pct: float = 0.0
    turnover_24h: float = 0.0
    funding_rate: float = 0.0  # ułamek, np. 0.0001 = 0.01%
    volatility: float | None = None  # ATR% lub zakres 24h w %
    rsi: float | None = None
    momentum_change_pct: float | None = None  # zmiana ceny w oknie klines

    # Wypełniane podczas rankingu:
    scores: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    bias: str = "—"


def _percentile_ranks(values: list[float | None]) -> list[float]:
    """Zamienia listę wartości na rangi percentylowe 0..1.

    None -> 0.0 (brak danych = brak przewagi). Remisy dostają średnią rangę.
    """
    indexed = [(v, i) for i, v in enumerate(values) if v is not None]
    ranks = [0.0] * len(values)
    if len(indexed) <= 1:
        for v, i in indexed:
            ranks[i] = 1.0
        return ranks

    indexed.sort(key=lambda t: t[0])
    n = len(indexed)
    j = 0
    while j < n:
        k = j
        while k + 1 < n and indexed[k + 1][0] == indexed[j][0]:
            k += 1
        # Średnia pozycja dla remisów, znormalizowana do 0..1.
        avg_pos = (j + k) / 2.0
        rank = avg_pos / (n - 1)
        for m in range(j, k + 1):
            ranks[indexed[m][1]] = rank
        j = k + 1
    return ranks


def _infer_bias(m: PairMetrics) -> str:
    """Prosty sygnał kierunku na podstawie RSI i zmiany 24h.

    To heurystyka trendowa, nie prognoza. Skrajne RSI oznaczamy jako
    ryzyko odwrócenia.
    """
    rsi = m.rsi
    chg = m.change_24h_pct
    if rsi is not None:
        if rsi >= 70:
            return "LONG⚠ (wykupienie)"
        if rsi <= 30:
            return "SHORT⚠ (wyprzedanie)"
        if rsi > 55 and chg > 0:
            return "LONG"
        if rsi < 45 and chg < 0:
            return "SHORT"
    if chg > 1:
        return "LONG"
    if chg < -1:
        return "SHORT"
    return "neutralny"


def rank_pairs(
    pairs: Iterable[PairMetrics],
    weights: dict[str, float] | None = None,
) -> list[PairMetrics]:
    """Liczy oceny cząstkowe i łączną, zwraca listę posortowaną malejąco."""
    weights = weights or DEFAULT_WEIGHTS
    total_w = sum(weights.values()) or 1.0

    items = list(pairs)
    if not items:
        return []

    vol_rank = _percentile_ranks([m.volatility for m in items])
    # Momentum: łączymy dystans RSI od 50 z |zmiana 24h| (po normalizacji).
    rsi_strength = [
        (abs(m.rsi - 50.0) if m.rsi is not None else None) for m in items
    ]
    chg_strength = [abs(m.change_24h_pct) for m in items]
    rsi_rank = _percentile_ranks(rsi_strength)
    chg_rank = _percentile_ranks([float(x) for x in chg_strength])
    mom_rank = [(a + b) / 2.0 for a, b in zip(rsi_rank, chg_rank)]

    liq_rank = _percentile_ranks([m.turnover_24h for m in items])
    fund_rank = _percentile_ranks([abs(m.funding_rate) for m in items])

    for i, m in enumerate(items):
        m.scores = {
            "volatility": vol_rank[i],
            "momentum": mom_rank[i],
            "liquidity": liq_rank[i],
            "funding": fund_rank[i],
        }
        weighted = (
            m.scores["volatility"] * weights.get("volatility", 0.0)
            + m.scores["momentum"] * weights.get("momentum", 0.0)
            + m.scores["liquidity"] * weights.get("liquidity", 0.0)
            + m.scores["funding"] * weights.get("funding", 0.0)
        )
        m.total_score = round(weighted / total_w * 100.0, 2)
        m.bias = _infer_bias(m)

    items.sort(key=lambda x: x.total_score, reverse=True)
    return items
