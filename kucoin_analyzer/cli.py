"""Interfejs wiersza poleceń analizatora KuCoin Futures."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .analyzer import analyze
from .api import KucoinApiError, KucoinFuturesClient
from .scoring import DEFAULT_WEIGHTS, PairMetrics

DISCLAIMER = (
    "UWAGA: Ranking to sygnał wspierający decyzję, a NIE prognoza cen ani "
    "porada inwestycyjna.\nHandel futures z dźwignią jest bardzo ryzykowny — "
    "możesz stracić cały kapitał."
)


def _fmt_turnover(v: float) -> str:
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= div:
            return f"{v / div:.2f}{unit}"
    return f"{v:.0f}"


def _fmt(v: float | None, suffix: str = "", dash: str = "—") -> str:
    return f"{v:.2f}{suffix}" if v is not None else dash


def render_table(pairs: list[PairMetrics], top: int) -> str:
    rows = pairs[:top]
    headers = [
        "#", "Symbol", "Cena", "24h%", "Zmien.%", "RSI",
        "Obrót24h", "Fund.%", "Ocena", "Sygnał",
    ]
    table: list[list[str]] = []
    for i, m in enumerate(rows, 1):
        table.append([
            str(i),
            m.symbol,
            _fmt(m.price),
            f"{m.change_24h_pct:+.2f}",
            _fmt(m.volatility),
            _fmt(m.rsi, dash="—"),
            _fmt_turnover(m.turnover_24h),
            f"{m.funding_rate * 100:+.4f}",
            f"{m.total_score:.1f}",
            m.bias,
        ])

    widths = [len(h) for h in headers]
    for row in table:
        for j, cell in enumerate(row):
            widths[j] = max(widths[j], len(cell))

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[j]) for j, c in enumerate(cells))

    sep = "  ".join("-" * w for w in widths)
    out = [line(headers), sep]
    out += [line(r) for r in table]
    return "\n".join(out)


def parse_weights(spec: str | None) -> dict[str, float]:
    if not spec:
        return dict(DEFAULT_WEIGHTS)
    weights = dict(DEFAULT_WEIGHTS)
    for part in spec.split(","):
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip().lower()
        if key in weights:
            try:
                weights[key] = float(val)
            except ValueError:
                pass
    return weights


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kucoin-analyzer",
        description="Analiza rynku KuCoin Futures — ranking par o największym potencjale.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--top", type=int, default=15, help="ile par pokazać w rankingu")
    p.add_argument("--quote", default="USDT", help="waluta kwotowana kontraktów")
    p.add_argument(
        "--candidates",
        type=int,
        default=60,
        help="ile najbardziej płynnych par analizować świecami (0 = wszystkie)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=60,
        help="granulacja świec w minutach (1,5,15,30,60,120,240,480,720,1440,10080)",
    )
    p.add_argument("--lookback", type=int, default=100, help="liczba świec do analizy")
    p.add_argument(
        "--no-klines",
        action="store_true",
        help="pomiń świece (szybciej; zmienność/momentum tylko z danych 24h)",
    )
    p.add_argument(
        "--weights",
        default=None,
        help="wagi, np. 'volatility=0.4,momentum=0.3,liquidity=0.2,funding=0.1'",
    )
    p.add_argument("--json", action="store_true", help="wypisz wynik jako JSON")
    p.add_argument("--quiet", action="store_true", help="bez komunikatów postępu")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    weights = parse_weights(args.weights)

    def progress(msg: str) -> None:
        if not args.quiet and not args.json:
            print(msg, file=sys.stderr)

    try:
        pairs = analyze(
            client=KucoinFuturesClient(),
            quote=args.quote,
            candidates=args.candidates,
            use_klines=not args.no_klines,
            granularity=args.interval,
            lookback=args.lookback,
            weights=weights,
            progress=progress,
        )
    except KucoinApiError as exc:
        print(f"Błąd API: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = [
            {
                "rank": i,
                "symbol": m.symbol,
                "price": m.price,
                "change_24h_pct": round(m.change_24h_pct, 4),
                "volatility_pct": m.volatility,
                "rsi": m.rsi,
                "turnover_24h": m.turnover_24h,
                "funding_rate_pct": round(m.funding_rate * 100, 6),
                "score": m.total_score,
                "score_breakdown": {k: round(v, 4) for k, v in m.scores.items()},
                "bias": m.bias,
            }
            for i, m in enumerate(pairs[: args.top], 1)
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"=== KuCoin Futures — TOP {args.top} par (waluta {args.quote}) ===")
    print(f"Wagi: {weights}")
    print()
    print(render_table(pairs, args.top))
    print()
    print(DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
