import json
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

log = logging.getLogger(__name__)

NAVER_API_URL = "https://m.stock.naver.com/api/stock/{ticker}/basic"


def fetch_price(ticker: str) -> int | None:
    """Fetch current price for a KRX stock ticker from Naver Finance."""
    url = NAVER_API_URL.format(ticker=ticker)
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            price_str = data.get("closePrice", "").replace(",", "")
            if price_str:
                return int(price_str)
    except (URLError, ValueError, KeyError, json.JSONDecodeError) as e:
        log.warning("Failed to fetch price for %s: %s", ticker, e)
    return None


def fetch_prices(tickers: list[str]) -> dict[str, int]:
    """Fetch current prices for multiple tickers. Returns {ticker: price}."""
    import time
    result = {}
    for ticker in tickers:
        price = fetch_price(ticker)
        if price is not None:
            result[ticker] = price
        time.sleep(0.2)  # Rate limiting
    return result
