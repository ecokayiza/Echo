import unittest
from unittest.mock import patch

from eco_rag.tools.web_search import web_search


class _FakeResponse:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class WebSearchTests(unittest.TestCase):
    def test_web_search_parses_duckduckgo_html_results(self):
        html = """
        <html>
          <body>
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fone">Result One</a>
            <a class="result__snippet">Snippet one</a>
            <a class="result__a" href="https://example.com/two">Result Two</a>
            <a class="result__snippet">Snippet two</a>
          </body>
        </html>
        """

        with patch("eco_rag.tools.web_search.urlopen", return_value=_FakeResponse(html)):
            result = web_search.invoke({"query": "langgraph", "max_results": 2})

        self.assertEqual(result["skill_name"], "web_search")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["title"], "Result One")
        self.assertEqual(result["items"][0]["content"], "Snippet one")
        self.assertEqual(result["items"][0]["url"], "https://example.com/one")
        self.assertEqual(result["items"][1]["url"], "https://example.com/two")

    def test_web_search_aggregates_multiple_queries_and_dedupes(self):
        first_html = """
        <html>
          <body>
            <a class="result__a" href="https://example.com/one">Result One</a>
            <a class="result__snippet">Snippet one</a>
          </body>
        </html>
        """
        second_html = """
        <html>
          <body>
            <a class="result__a" href="https://example.com/one">Result One</a>
            <a class="result__snippet">Snippet one</a>
            <a class="result__a" href="https://example.com/two">Result Two</a>
            <a class="result__snippet">Snippet two</a>
          </body>
        </html>
        """

        with patch(
            "eco_rag.tools.web_search.urlopen",
            side_effect=[_FakeResponse(first_html), _FakeResponse(second_html)],
        ):
            result = web_search.invoke({"queries": ["langgraph", "eco rag"], "max_results": 5})

        self.assertEqual(len(result["items"]), 2)
        self.assertEqual([item["url"] for item in result["items"]], ["https://example.com/one", "https://example.com/two"])

    def test_web_search_rejects_empty_queries(self):
        result = web_search.invoke({"query": "   "})

        self.assertEqual(result["items"], [])
        self.assertEqual(result["error"], "Query cannot be empty.")


if __name__ == "__main__":
    unittest.main()
