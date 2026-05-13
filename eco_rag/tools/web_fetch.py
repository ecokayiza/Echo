from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from langchain_core.tools import tool

from .web_search import REQUEST_HEADERS

MAX_FETCH_CHARS = 50_000


@tool
def web_fetch(url: str, max_chars: int = 8000) -> dict[str, Any]:
    """Fetch one public web page and return readable text."""
    try:
        cleaned_url = _validated_url(url)
        limit = max(1, min(int(max_chars or 8000), MAX_FETCH_CHARS))
        html = _fetch(cleaned_url)
        title, content = _extract_text(html)
        return _context(
            [
                {
                    "title": title or urlparse(cleaned_url).netloc,
                    "url": cleaned_url,
                    "content": content[:limit],
                }
            ]
        )
    except Exception as exc:
        return _context([], error=str(exc))


def _validated_url(value: str) -> str:
    cleaned = str(value or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("web_fetch requires an http or https URL.")
    return cleaned


def _fetch(url: str) -> str:
    request = Request(url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=15) as response:
        body = response.read()
        headers = getattr(response, "headers", None)
        charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
        return body.decode(charset or "utf-8", errors="replace")


def _extract_text(html: str) -> tuple[str, str]:
    parser = _ReadableTextParser()
    parser.feed(html)
    parser.close()
    return _plain_text(" ".join(parser.title_parts)), _plain_text(" ".join(parser.content_parts))


def _plain_text(value: str) -> str:
    return " ".join(unescape(value or "").split())


def _context(items: list[dict[str, Any]], *, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "context",
        "skill_name": "web_fetch",
        "items": items,
    }
    if error:
        payload["error"] = error
    return payload


class _ReadableTextParser(HTMLParser):
    """Extract title and visible text from simple HTML."""

    ignored_tags = {"script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self.title_parts: list[str] = []
        self.content_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        if tag in self.ignored_tags:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif self._skip_depth:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if not data or self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.content_parts.append(data)
