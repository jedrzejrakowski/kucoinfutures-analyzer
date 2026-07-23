"""Testy offline logiki analizy — bez połączenia z API.

Uruchom: python -m pytest    lub    python tests/test_analyzer.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kucoin_analyzer import indicators  # noqa: E402
from kucoin_analyzer.analyzer import build_metrics_from_contract  # noqa: E402
from kucoin_analyzer.scoring import (  # noqa: E402
    PairMetrics,
    _percentile_ranks,
    rank_pairs,
)


def _candles_from_closes(closes, spread=1.0):
    """Buduje świece [t,o,h,l,c,v] z listy cen zamknięcia."""
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        h = max(o, c) + spread
        low = min(o, c) - spread
        out.append([i, o, h, low, c, 100.0])
    return out


# --- wskaźniki --------------------------------------------------------------

def test_rsi_all_gains_is_100():
    candles = _candles_from_closes([float(x) for x in range(1, 30)], spread=0.0)
    assert indicators.rsi(candles) == 100.0


def test_rsi_all_losses_is_zero():
    candles = _candles_from_closes([float(x) for x in range(30, 1, -1)], spread=0.0)
    assert indicators.rsi(candles) == 0.0


def test_rsi_mid_range_for_flat_noise():
    closes = [10 + (1 if i % 2 == 0 else -1) for i in range(40)]
    r = indicators.rsi([[i, c, c, c, c, 1] for i, c in enumerate(closes)])
    assert r is not None and 30 < r < 70


def test_rsi_insufficient_data_returns_none():
    assert indicators.rsi(_candles_from_closes([1.0, 2.0, 3.0])) is None


def test_atr_pct_positive_and_scales_with_range():
    small = _candles_from_closes([100.0] * 30, spread=0.5)
    big = _candles_from_closes([100.0] * 30, spread=5.0)
    a_small = indicators.atr_pct(small)
    a_big = indicators.atr_pct(big)
    assert a_small is not None and a_big is not None
    assert a_big > a_small


def test_price_change_pct():
    candles = _candles_from_closes([100.0, 110.0])
    assert math.isclose(indicators.price_change_pct(candles), 10.0, rel_tol=1e-6)


# --- ranking / percentyle ---------------------------------------------------

def test_percentile_ranks_basic_order():
    ranks = _percentile_ranks([10.0, 20.0, 30.0])
    assert ranks[0] < ranks[1] < ranks[2]
    assert ranks[0] == 0.0 and ranks[2] == 1.0


def test_percentile_ranks_handles_none():
    ranks = _percentile_ranks([None, 5.0, 10.0])
    assert ranks[0] == 0.0
    assert ranks[2] == 1.0


def test_rank_pairs_orders_by_score():
    # Para A: wysoka zmienność, obrót, momentum -> powinna wygrać.
    a = PairMetrics(symbol="A", change_24h_pct=8.0, turnover_24h=1e9,
                    funding_rate=0.001, volatility=5.0, rsi=75.0)
    b = PairMetrics(symbol="B", change_24h_pct=0.1, turnover_24h=1e3,
                    funding_rate=0.00001, volatility=0.2, rsi=50.0)
    c = PairMetrics(symbol="C", change_24h_pct=3.0, turnover_24h=1e6,
                    funding_rate=0.0002, volatility=2.0, rsi=60.0)
    ranked = rank_pairs([b, c, a])
    assert [m.symbol for m in ranked] == ["A", "C", "B"]
    assert ranked[0].total_score >= ranked[1].total_score >= ranked[2].total_score
    assert 0.0 <= ranked[-1].total_score <= 100.0


def test_rank_pairs_empty():
    assert rank_pairs([]) == []


def test_weights_change_ranking():
    # Para płynna vs para zmienna; zmiana wag odwraca zwycięzcę.
    liquid = PairMetrics(symbol="LIQ", turnover_24h=1e9, volatility=0.1,
                         change_24h_pct=0.1, rsi=50.0)
    volatile = PairMetrics(symbol="VOL", turnover_24h=1e3, volatility=9.0,
                           change_24h_pct=9.0, rsi=80.0)
    liq_first = rank_pairs([liquid, volatile],
                           {"liquidity": 1.0, "volatility": 0.0,
                            "momentum": 0.0, "funding": 0.0})
    vol_first = rank_pairs([liquid, volatile],
                           {"liquidity": 0.0, "volatility": 1.0,
                            "momentum": 0.0, "funding": 0.0})
    assert liq_first[0].symbol == "LIQ"
    assert vol_first[0].symbol == "VOL"


# --- mapowanie danych z API -------------------------------------------------

def test_build_metrics_from_contract():
    contract = {
        "symbol": "XBTUSDTM",
        "quoteCurrency": "USDT",
        "status": "Open",
        "lastTradePrice": "50000",
        "priceChgPct": "0.025",  # API zwraca ułamek -> 2.5%
        "highPrice": "51000",
        "lowPrice": "49000",
        "turnoverOf24h": "1234567.0",
        "fundingFeeRate": "0.0001",
    }
    m = build_metrics_from_contract(contract)
    assert m.symbol == "XBTUSDTM"
    assert math.isclose(m.price, 50000.0)
    assert math.isclose(m.change_24h_pct, 2.5)
    assert math.isclose(m.turnover_24h, 1234567.0)
    assert math.isclose(m.funding_rate, 0.0001)
    # zakres 24h = (51000-49000)/50000*100 = 4.0%
    assert math.isclose(m.volatility, 4.0)


def test_build_metrics_handles_missing_fields():
    m = build_metrics_from_contract({"symbol": "X"})
    assert m.symbol == "X"
    assert m.price == 0.0
    assert m.volatility is None  # brak high/low


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} testów przeszło.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
