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
    _infer_bias,
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


# --- MACD / Bollinger / EMA -------------------------------------------------

def test_ema_series_length_and_seed():
    vals = [float(x) for x in range(1, 11)]
    ema = indicators.ema_series(vals, 3)
    assert len(ema) == len(vals)
    assert ema[0] is None and ema[1] is None
    # zalążek = SMA(1,2,3) = 2.0
    assert math.isclose(ema[2], 2.0)


def test_ema_insufficient_data():
    assert indicators.ema_series([1.0, 2.0], 5) == [None, None]


def test_macd_line_sign_follows_trend():
    up = [100 + i * 1.5 for i in range(60)]
    down = [100 - i * 1.5 for i in range(60)]
    m_up = indicators.macd([[i, c, c, c, c, 1] for i, c in enumerate(up)])
    m_dn = indicators.macd([[i, c, c, c, c, 1] for i, c in enumerate(down)])
    assert m_up is not None and m_dn is not None
    assert m_up["macd"] > 0   # fast EMA nad slow EMA -> trend wzrostowy
    assert m_dn["macd"] < 0


def test_macd_histogram_sign_on_acceleration():
    # Przyspieszający ruch -> histogram (MACD - sygnał) niezerowy i zgodny z kierunkiem.
    up_acc = [100 + (i ** 1.8) * 0.05 for i in range(60)]
    dn_acc = [100 - (i ** 1.8) * 0.05 for i in range(60)]
    m_up = indicators.macd([[i, c, c, c, c, 1] for i, c in enumerate(up_acc)])
    m_dn = indicators.macd([[i, c, c, c, c, 1] for i, c in enumerate(dn_acc)])
    assert m_up["hist"] > 0
    assert m_dn["hist"] < 0


def test_macd_insufficient_data_returns_none():
    closes = [100.0] * 10
    assert indicators.macd([[i, c, c, c, c, 1] for i, c in enumerate(closes)]) is None


def test_bollinger_percent_b_and_bandwidth():
    closes = [10.0] * 19 + [12.0]  # ostatnia świeca wybija w górę
    bb = indicators.bollinger([[i, c, c, c, c, 1] for i, c in enumerate(closes)],
                              period=20)
    assert bb is not None
    assert bb["upper"] > bb["middle"] > bb["lower"]
    assert bb["percent_b"] > 0.5      # cena w górnej części wstęg
    assert bb["bandwidth_pct"] > 0


def test_bollinger_insufficient_data():
    closes = [10.0] * 5
    assert indicators.bollinger([[i, c, c, c, c, 1] for i, c in enumerate(closes)],
                                period=20) is None


# --- sygnał kierunku (bias) -------------------------------------------------

def test_bias_overbought_flags_warning():
    m = PairMetrics(symbol="X", rsi=75.0, change_24h_pct=5.0, macd_hist=1.0)
    assert "wykupienie" in _infer_bias(m)


def test_bias_oversold_flags_warning():
    m = PairMetrics(symbol="X", bb_percent_b=-0.1, rsi=25.0, change_24h_pct=-5.0)
    assert "wyprzedanie" in _infer_bias(m)


def test_bias_macd_drives_long():
    m = PairMetrics(symbol="X", rsi=58.0, change_24h_pct=2.0, macd_hist=0.5,
                    bb_percent_b=0.7)
    assert _infer_bias(m) == "LONG"


def test_bias_macd_drives_short():
    m = PairMetrics(symbol="X", rsi=42.0, change_24h_pct=-2.0, macd_hist=-0.5,
                    bb_percent_b=0.3)
    assert _infer_bias(m) == "SHORT"


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


# --- warstwa webowa (bez sieci) ---------------------------------------------

def test_web_compute_ranking_parses_params_and_shapes_output():
    from kucoin_analyzer import web

    captured = {}

    def fake_analyze(**kwargs):
        captured.update(kwargs)
        return [
            PairMetrics(symbol="XBTUSDTM", price=50000.0, change_24h_pct=2.5,
                        turnover_24h=1e9, funding_rate=0.0001, volatility=1.5,
                        rsi=60.0),
            PairMetrics(symbol="ETHUSDTM", price=3000.0, change_24h_pct=-1.0,
                        turnover_24h=5e8, funding_rate=-0.0002, volatility=2.0,
                        rsi=45.0),
        ]

    orig = web.analyze
    web.analyze = fake_analyze
    try:
        out = web.compute_ranking(
            "top=2&interval=15&candidates=30&no_klines=1"
            "&weights=volatility=0.5,momentum=0.5,liquidity=0,funding=0"
        )
    finally:
        web.analyze = orig

    # Parametry z query poprawnie zmapowane na wywołanie analyze():
    assert captured["granularity"] == 15
    assert captured["candidates"] == 30
    assert captured["use_klines"] is False
    assert captured["weights"]["volatility"] == 0.5
    assert captured["weights"]["liquidity"] == 0.0

    # Kształt odpowiedzi:
    assert out["quote"] == "USDT"
    assert len(out["results"]) == 2
    first = out["results"][0]
    assert first["rank"] == 1
    assert first["symbol"] == "XBTUSDTM"
    assert "score_breakdown" in first


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
