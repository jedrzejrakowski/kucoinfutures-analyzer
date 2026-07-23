"""Prosta wersja webowa analizatora KuCoin Futures.

Lekki serwer HTTP oparty wyłącznie na bibliotece standardowej (http.server).
Serwuje stronę (static/index.html) oraz endpoint JSON /api/ranking, który
uruchamia tę samą analizę co CLI.

Uruchomienie:
    python -m kucoin_analyzer.web
    python -m kucoin_analyzer.web --port 8080 --host 0.0.0.0

Następnie otwórz w przeglądarce: http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .analyzer import analyze
from .api import KucoinApiError, KucoinFuturesClient
from .cli import parse_weights

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _bool(params: dict, key: str, default: bool = False) -> bool:
    if key not in params:
        return default
    return params[key][0].lower() in ("1", "true", "yes", "on")


def _int(params: dict, key: str, default: int) -> int:
    try:
        return int(params[key][0])
    except (KeyError, ValueError, IndexError):
        return default


def compute_ranking(query: str) -> dict:
    """Buduje dane rankingu z parametrów query stringa."""
    params = urllib.parse.parse_qs(query)
    top = max(1, _int(params, "top", 15))
    quote = params.get("quote", ["USDT"])[0]
    candidates = _int(params, "candidates", 60)
    interval = _int(params, "interval", 60)
    lookback = _int(params, "lookback", 100)
    use_klines = not _bool(params, "no_klines", False)
    weights = parse_weights(params.get("weights", [None])[0])

    pairs = analyze(
        client=KucoinFuturesClient(),
        quote=quote,
        candidates=candidates,
        use_klines=use_klines,
        granularity=interval,
        lookback=lookback,
        weights=weights,
    )

    rows = [
        {
            "rank": i,
            "symbol": m.symbol,
            "price": m.price,
            "change_24h_pct": round(m.change_24h_pct, 4),
            "volatility_pct": m.volatility,
            "rsi": m.rsi,
            "macd_hist": m.macd_hist,
            "bb_percent_b": m.bb_percent_b,
            "bb_bandwidth_pct": m.bb_bandwidth_pct,
            "turnover_24h": m.turnover_24h,
            "funding_rate_pct": round(m.funding_rate * 100, 6),
            "score": m.total_score,
            "score_breakdown": {k: round(v, 4) for k, v in m.scores.items()},
            "bias": m.bias,
        }
        for i, m in enumerate(pairs[:top], 1)
    ]
    return {"weights": weights, "quote": quote, "results": rows}


class Handler(BaseHTTPRequestHandler):
    server_version = f"kucoin-analyzer/{__version__}"

    def log_message(self, fmt, *args):  # cichszy log
        return

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, content_type: str) -> None:
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404, "Nie znaleziono")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            return

        if route == "/api/ranking":
            try:
                data = compute_ranking(parsed.query)
                self._send_json(data)
            except KucoinApiError as exc:
                self._send_json({"error": f"Błąd API KuCoin: {exc}"}, status=502)
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self._send_json({"error": f"Błąd serwera: {exc}"}, status=500)
            return

        self.send_error(404, "Nie znaleziono")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kucoin-analyzer-web",
        description="Webowa wersja analizatora KuCoin Futures.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host", default="127.0.0.1", help="adres nasłuchu")
    p.add_argument("--port", type=int, default=8000, help="port")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"KuCoin Futures Analyzer — serwer webowy działa: {url}")
    print("Otwórz ten adres w przeglądarce. Zatrzymanie: Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nZatrzymuję serwer...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
