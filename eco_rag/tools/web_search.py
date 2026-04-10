from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

from langchain_core.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the public web for fresh or external information."""
    cleaned = " ".join((query or "").strip().split())
    limit = max(1, min(int(max_results or 5), 8))
    if not cleaned:
        return {
            "type": "context",
            "skill_name": "web_search",
            "items": [],
            "query": cleaned,
            "error": "Query cannot be empty.",
        }

    request = Request(
        f"https://duckduckgo.com/html/?q={quote_plus(cleaned)}&kl=us-en",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urlopen(request, timeout=12) as response:
            html = response.read().decode("utf-8", errors="replace")
        items = _parse_results(html)[:limit]
    except Exception as exc:
        return {
            "type": "context",
            "skill_name": "web_search",
            "items": [],
            "query": cleaned,
            "error": str(exc),
        }

    return {
        "type": "context",
        "skill_name": "web_search",
        "items": items,
        "query": cleaned,
        "count": len(items),
    }


class _DuckDuckGoHTMLParser(HTMLParser):
    """Parse DuckDuckGo HTML search result pages."""

    def __init__(self):
        super().__init__()
        self.items: list[dict[str, str | None]] = []
        self._current: dict[str, Any] | None = None
        self._title_depth = 0
        self._snippet_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())

        if "result__a" in classes:
            self._flush()
            self._current = {
                "title_parts": [],
                "snippet_parts": [],
                "url": _resolve_result_url(attributes.get("href")),
            }
            self._title_depth = 1
            return

        if self._current is None:
            return

        if "result__snippet" in classes:
            self._snippet_depth = 1
            return

        if self._title_depth:
            self._title_depth += 1
        if self._snippet_depth:
            self._snippet_depth += 1

    def handle_endtag(self, _tag: str):
        if self._title_depth:
            self._title_depth -= 1
        if self._snippet_depth:
            self._snippet_depth -= 1

    def handle_data(self, data: str):
        if self._current is None:
            return
        if self._title_depth:
            self._current["title_parts"].append(data)
        elif self._snippet_depth:
            self._current["snippet_parts"].append(data)

    def close(self):
        super().close()
        self._flush()

    def _flush(self):
        if self._current is None:
            return
        title = " ".join(" ".join(self._current["title_parts"]).split())
        snippet = " ".join(" ".join(self._current["snippet_parts"]).split())
        if title:
            self.items.append(
                {
                    "title": unescape(title),
                    "content": unescape(snippet) or unescape(title),
                    "url": self._current["url"],
                }
            )
        self._current = None
        self._title_depth = 0
        self._snippet_depth = 0


def _parse_results(html: str) -> list[dict[str, str | None]]:
    """Parse and deduplicate HTML search results."""
    parser = _DuckDuckGoHTMLParser()
    parser.feed(html)
    parser.close()

    deduped: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for item in parser.items:
        key = (str(item.get("title", "")), str(item.get("content", "")), item.get("url"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _resolve_result_url(value: str | None) -> str | None:
    """Resolve DuckDuckGo redirect URLs into destination URLs."""
    if not value:
        return None
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    target = query.get("uddg", [None])[0]
    if target:
        return target
    if value.startswith("//"):
        return f"https:{value}"
    return value
