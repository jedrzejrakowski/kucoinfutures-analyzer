"""Klient publicznego API KuCoin Futures.

Używa wyłącznie biblioteki standardowej Pythona (urllib) — brak zależności
zewnętrznych i brak potrzeby klucza API dla danych rynkowych (publiczne).

Dokumentacja: https://www.kucoin.com/docs/rest/futures-trading/market-data
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = "https://api-futures.kucoin.com"

# Dozwolone granulacje świec (w minutach) wg API KuCoin Futures.
VALID_GRANULARITIES = {1, 5, 15, 30, 60, 120, 240, 480, 720, 1440, 10080}


class KucoinApiError(RuntimeError):
    """Błąd zwrócony przez API lub warstwę sieciową."""


class KucoinFuturesClient:
    """Cienki klient do publicznych endpointów rynkowych KuCoin Futures."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 20.0,
        max_retries: int = 3,
        user_agent: str = "kucoin-futures-analyzer/0.1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent

    # -- warstwa transportowa -------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
            url = f"{url}?{query}"

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": self.user_agent}
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                # API KuCoin zwraca {"code": "200000", "data": ...}
                code = str(payload.get("code", ""))
                if code and code != "200000":
                    raise KucoinApiError(
                        f"API zwróciło kod {code}: {payload.get('msg')}"
                    )
                return payload.get("data")
            except (urllib.error.URLError, TimeoutError, KucoinApiError) as exc:
                last_err = exc
                # Wykładniczy backoff: 1s, 2s, 4s ...
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        raise KucoinApiError(
            f"Nie udało się pobrać {path} po {self.max_retries} próbach: {last_err}"
        )

    # -- endpointy ------------------------------------------------------------

    def active_contracts(self) -> list[dict[str, Any]]:
        """Lista wszystkich aktywnych kontraktów wraz ze statystykami 24h.

        Pojedyncze wywołanie zwraca m.in.: symbol, lastTradePrice,
        priceChgPct, highPrice, lowPrice, volumeOf24h, turnoverOf24h,
        fundingFeeRate, markPrice, indexPrice, openInterest.
        """
        data = self._get("/api/v1/contracts/active")
        if not isinstance(data, list):
            raise KucoinApiError("Nieoczekiwany format odpowiedzi /contracts/active")
        return data

    def klines(
        self,
        symbol: str,
        granularity: int = 60,
        lookback: int = 100,
    ) -> list[list[float]]:
        """Świece dla symbolu.

        Zwraca listę [time_ms, open, high, low, close, volume].
        `granularity` w minutach; `lookback` = liczba ostatnich świec.
        """
        if granularity not in VALID_GRANULARITIES:
            raise ValueError(
                f"granularity={granularity} nieobsługiwana; "
                f"dozwolone: {sorted(VALID_GRANULARITIES)}"
            )
        now_ms = int(time.time() * 1000)
        span_ms = granularity * 60 * 1000 * (lookback + 2)
        params = {
            "symbol": symbol,
            "granularity": granularity,
            "from": now_ms - span_ms,
            "to": now_ms,
        }
        data = self._get("/api/v1/kline/query", params)
        if not isinstance(data, list):
            return []
        # Każda świeca: [time, open, high, low, close, volume]
        out: list[list[float]] = []
        for row in data[-lookback:]:
            try:
                out.append([float(x) for x in row])
            except (TypeError, ValueError):
                continue
        return out
