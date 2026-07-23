# KuCoin Futures Analyzer

Narzędzie CLI do analizy rynku kontraktów **perpetual futures** na giełdzie
KuCoin. Pobiera publiczne notowania, liczy wskaźniki i buduje **ranking par
kryptowalut o największym potencjale** według czterech kryteriów:

- **Zmienność** (volatility) — ATR% lub zakres 24h
- **Momentum / trend** — RSI + zmiana ceny
- **Płynność** (liquidity) — obrót 24h
- **Funding rate** — sygnał zatłoczenia pozycji long/short (specyficzny dla perpetual)

Wyniki łączone są w ważoną **ocenę potencjału (0–100)** wraz z pomocniczym
sygnałem kierunku (LONG / SHORT).

> ⚠️ **Ważne zastrzeżenie.** Ten program **nie przewiduje przyszłych cen** i
> **nie gwarantuje zysku**. To narzędzie wspierające decyzję — pokazuje pary,
> które według zdefiniowanych reguł są „interesujące", ale rynek pozostaje
> nieprzewidywalny. Handel kontraktami futures z dźwignią jest bardzo
> ryzykowny i możesz stracić cały kapitał. **To nie jest porada inwestycyjna.**

---

## Wymagania

- **Python 3.9+**
- **Brak zależności zewnętrznych** — rdzeń działa wyłącznie na bibliotece
  standardowej (`urllib`, `json`, ...). Nie potrzebujesz klucza API KuCoin
  (używane są publiczne dane rynkowe).
- Dostęp do internetu (endpoint `https://api-futures.kucoin.com`).

## Instalacja

```bash
git clone https://github.com/<twój-login>/kucoin-futures-analyzer.git
cd kucoin-futures-analyzer
```

To wszystko — nie ma nic do zainstalowania.

## Użycie

Domyślny ranking TOP 15 par USDT (z analizą świec):

```bash
python -m kucoin_analyzer
```

Przykłady:

```bash
# Szybko, bez pobierania świec (zmienność/momentum tylko z danych 24h)
python -m kucoin_analyzer --no-klines --top 20

# Analiza na świecach 15-minutowych, 200 świec wstecz
python -m kucoin_analyzer --interval 15 --lookback 200

# Własne wagi kryteriów (nacisk na zmienność i momentum)
python -m kucoin_analyzer --weights "volatility=0.4,momentum=0.35,liquidity=0.15,funding=0.1"

# Analizuj wszystkie kontrakty USDT (wolniej — dużo zapytań o świece)
python -m kucoin_analyzer --candidates 0

# Wynik jako JSON (do dalszego przetwarzania / dashboardu)
python -m kucoin_analyzer --json > ranking.json
```

Pełna lista opcji:

```bash
python -m kucoin_analyzer --help
```

### Najważniejsze opcje

| Opcja | Domyślnie | Opis |
|-------|-----------|------|
| `--top N` | 15 | Ile par pokazać w rankingu |
| `--quote` | USDT | Waluta kwotowana kontraktów |
| `--candidates N` | 60 | Ile najpłynniejszych par analizować świecami (`0` = wszystkie) |
| `--interval` | 60 | Granulacja świec w minutach (1,5,15,30,60,120,240,480,720,1440,10080) |
| `--lookback` | 100 | Liczba świec do analizy wskaźników |
| `--no-klines` | — | Pomiń świece (szybciej, mniej dokładna zmienność/momentum) |
| `--weights` | patrz niżej | Wagi kryteriów |
| `--json` | — | Wynik w formacie JSON |

## Wersja webowa

Oprócz CLI dostępny jest prosty interfejs w przeglądarce (również **bez
zależności zewnętrznych** — serwer oparty na `http.server`, wykresy rysowane
bez żadnych bibliotek/CDN).

```bash
python -m kucoin_analyzer.web
# domyślnie: http://127.0.0.1:8000

# własny host/port:
python -m kucoin_analyzer.web --host 0.0.0.0 --port 8080
```

Otwórz podany adres w przeglądarce, ustaw parametry (liczba par, interwał
świec, wagi kryteriów) i kliknij **„Analizuj"**. Zobaczysz wykres słupkowy
ocen oraz pełną tabelę rankingu z paskami oceny i sygnałem kierunku.

Strona odpytuje lokalny endpoint `GET /api/ranking` (ten sam silnik analizy
co CLI), więc działa tam, gdzie masz dostęp do API KuCoin.

## Jak liczona jest ocena

1. Dla każdej pary zbierane są surowe metryki (zmienność, momentum, obrót,
   funding rate).
2. Każda metryka jest **normalizowana do 0–1 metodą rangi percentylowej** w
   obrębie całego badanego zbioru par (odporne na wartości odstające).
3. Znormalizowane oceny łączone są w **ważoną sumę** i skalowane do 0–100.

Domyślne wagi:

```
volatility = 0.30
momentum   = 0.30
liquidity  = 0.25
funding    = 0.15
```

Kolumny w tabeli wyników:

| Kolumna | Znaczenie |
|---------|-----------|
| `24h%` | Zmiana ceny w ciągu 24h |
| `Zmien.%` | Zmienność: ATR% (ze świec) lub zakres 24h |
| `RSI` | Relative Strength Index (>70 wykupienie, <30 wyprzedanie) |
| `Obrót24h` | Obrót w ciągu 24h (płynność) |
| `Fund.%` | Funding rate w procentach (znak = kierunek) |
| `Ocena` | Łączna ocena potencjału 0–100 |
| `Sygnał` | Pomocniczy kierunek LONG/SHORT (heurystyka, nie prognoza) |

## Testy

Testy logiki działają **offline** (na danych syntetycznych, bez sieci):

```bash
# Bez żadnych zależności:
python tests/test_analyzer.py

# Albo przez pytest, jeśli masz go zainstalowanego:
python -m pytest -q
```

## Struktura projektu

```
kucoin_analyzer/
├── api.py          # klient publicznego API KuCoin Futures (tylko stdlib)
├── indicators.py   # wskaźniki: RSI, ATR%
├── scoring.py      # normalizacja, wagi, ranking
├── analyzer.py     # orkiestracja pobrania danych i analizy
├── cli.py          # interfejs wiersza poleceń + tabela
├── web.py          # serwer webowy (http.server) + endpoint /api/ranking
└── static/
    └── index.html  # strona z tabelą i wykresem (bez zależności/CDN)
tests/
└── test_analyzer.py
```

## Pomysły na rozbudowę

- Automatyczne odświeżanie wersji webowej na żywo
- Dodatkowe wskaźniki (MACD, Bollinger Bands, open interest, wolumen kierunkowy)
- Alerty (np. gdy ocena pary przekroczy próg)
- Backtesting reguł na danych historycznych
- Eksport do CSV / arkusza

## Licencja

MIT — patrz [LICENSE](LICENSE).
