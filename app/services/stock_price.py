import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

log = logging.getLogger(__name__)

NAVER_KRX_URL = "https://m.stock.naver.com/api/stock/{ticker}/basic"
NAVER_GLOBAL_URL = "https://api.stock.naver.com/stock/{ticker}.{exchange}/basic"


def _fetch_basic(ticker: str, exchange: str | None = None) -> dict | None:
    """Fetch basic info from Naver Finance. exchange: O(NASDAQ), N(NYSE), A(AMEX) for foreign."""
    if exchange:
        url = NAVER_GLOBAL_URL.format(ticker=ticker, exchange=exchange)
    else:
        url = NAVER_KRX_URL.format(ticker=ticker)
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except (URLError, ValueError, KeyError, json.JSONDecodeError) as e:
        log.warning("Failed to fetch info for %s: %s", ticker, e)
    return None


def fetch_price(ticker: str, exchange: str | None = None) -> int | float | None:
    """Fetch current price for a stock ticker from Naver Finance."""
    data = _fetch_basic(ticker, exchange)
    if data:
        price_str = data.get("closePrice", "").replace(",", "")
        if price_str:
            return float(price_str) if "." in price_str else int(price_str)
    return None


def lookup_ticker(ticker: str, exchange: str | None = None) -> dict | None:
    """Lookup ticker and return name + current price."""
    data = _fetch_basic(ticker, exchange)
    if data and data.get("stockName"):
        price_str = data.get("closePrice", "").replace(",", "")
        name = data.get("stockNameEng") or data["stockName"] if exchange else data["stockName"]
        price = float(price_str) if "." in price_str else int(price_str) if price_str else 0
        return {
            "ticker": ticker,
            "name": name,
            "current_price": price,
        }
    return None


def fetch_prices(tickers: list[str]) -> dict[str, int | float]:
    """Fetch current prices for multiple tickers. Returns {ticker: price}."""
    import time
    result = {}
    for ticker in tickers:
        price = fetch_price(ticker)
        if price is not None:
            result[ticker] = price
        time.sleep(0.2)  # Rate limiting
    return result
