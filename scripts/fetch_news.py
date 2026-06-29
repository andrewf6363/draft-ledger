"""Best-effort latest-headline fetch per ticker via Yahoo's keyless RSS feed.

Shown inside the stock detail drawer. Entirely non-blocking: any failure keeps
the cached headline so the build never waits on or breaks over news.
"""

import ssl
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import store

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
KEEP = 3


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_rss(sym):
    url = RSS.format(sym=sym)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
            xml = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ssl.SSLError, OSError):
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    items = []
    for it in root.findall(".//item")[:KEEP]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "pub": pub})
    return items


def main():
    owners = store.load("owners.json", {"owners": []}).get("owners", [])
    syms = []
    for o in owners:
        for s in o.get("picks", []):
            if s not in syms:
                syms.append(s)

    news = store.load("news.json", {"updated_utc": None, "tickers": {}})
    news.setdefault("tickers", {})

    got = 0
    for sym in syms:
        items = fetch_rss(sym)
        if items:
            news["tickers"][sym] = {"items": items}
            got += 1
        time.sleep(0.3)
    news["updated_utc"] = now_iso()

    store.save_if_changed("news.json", news)
    print(f"news: {got}/{len(syms)} tickers had headlines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
