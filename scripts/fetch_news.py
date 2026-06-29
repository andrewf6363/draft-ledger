"""Best-effort latest-headline fetch per ticker, shown in the stock detail drawer.

Primary source is Google News RSS (keyless, reliable, searched by company name);
Yahoo's old RSS is a fallback. Entirely non-blocking: any failure keeps the cached
headline so the build never waits on or breaks over news.
"""

import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import store

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
GOOGLE = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
KEEP = 3


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rss_items(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
            xml = r.read().decode("utf-8", "replace")
        root = ET.fromstring(xml)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ssl.SSLError, OSError, ET.ParseError):
        return None
    items = []
    for it in root.findall(".//item")[:KEEP]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "pub": pub})
    return items or None


def fetch_news_for(sym, name):
    q = urllib.parse.quote(f'"{name}" stock')
    return _rss_items(GOOGLE.format(q=q)) or _rss_items(YAHOO.format(sym=sym))


def main():
    owners = store.load("owners.json", {"owners": []}).get("owners", [])
    tickers = store.load("tickers.json", {})
    syms = []
    for o in owners:
        for s in o.get("picks", []):
            if s not in syms:
                syms.append(s)

    news = store.load("news.json", {"updated_utc": None, "tickers": {}})
    news.setdefault("tickers", {})

    got = 0
    for sym in syms:
        items = fetch_news_for(sym, tickers.get(sym, {}).get("name", sym))
        if items:
            news["tickers"][sym] = {"items": items}
            got += 1
        time.sleep(0.4)
    news["updated_utc"] = now_iso()

    store.save_if_changed("news.json", news)
    print(f"news: {got}/{len(syms)} tickers had headlines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
