import unittest
from unittest.mock import patch

from eco_rag.settings import AppSettings
from eco_rag.tools.web_fetch import web_fetch
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

        with (
            patch("eco_rag.tools.web_search.load_app_settings", return_value=AppSettings(web_search_backend="duckduckgo")),
            patch("eco_rag.tools.web_search.urlopen", return_value=_FakeResponse(html)),
        ):
            result = web_search.invoke({"query": "langgraph", "max_results": 2})

        self.assertEqual(result["skill_name"], "web_search")
        self.assertEqual(result["backend"], "duckduckgo")
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
            "eco_rag.tools.web_search.load_app_settings", return_value=AppSettings(web_search_backend="duckduckgo")
        ), patch(
            "eco_rag.tools.web_search.urlopen", side_effect=[_FakeResponse(first_html), _FakeResponse(second_html)]
        ):
            result = web_search.invoke({"queries": ["langgraph", "eco rag"], "max_results": 5})

        self.assertEqual(len(result["items"]), 2)
        self.assertEqual([item["url"] for item in result["items"]], ["https://example.com/one", "https://example.com/two"])

    def test_web_search_falls_back_to_duckduckgo_lite(self):
        html = """
        <html>
          <body>
            <a class='result-link' href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Flite">Lite Result</a>
            <td class='result-snippet'>Lite snippet with <b>markup</b></td>
          </body>
        </html>
        """

        with patch(
            "eco_rag.tools.web_search.load_app_settings", return_value=AppSettings(web_search_backend="duckduckgo")
        ), patch(
            "eco_rag.tools.web_search.urlopen", side_effect=[_FakeResponse("<html></html>"), _FakeResponse(html)]
        ):
            result = web_search.invoke({"query": "langgraph", "max_results": 2})

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "Lite Result")
        self.assertEqual(result["items"][0]["content"], "Lite snippet with markup")
        self.assertEqual(result["items"][0]["url"], "https://example.com/lite")

    def test_web_search_falls_back_to_bing_rss(self):
        rss = """
        <?xml version="1.0" encoding="utf-8" ?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Bing Result</title>
              <link>https://example.com/bing</link>
              <description>Bing snippet with &lt;b&gt;markup&lt;/b&gt;</description>
            </item>
          </channel>
        </rss>
        """

        with patch(
            "eco_rag.tools.web_search.load_app_settings", return_value=AppSettings(web_search_backend="auto")
        ), patch(
            "eco_rag.tools.web_search.urlopen",
            side_effect=[_FakeResponse("<html></html>"), _FakeResponse("<html></html>"), _FakeResponse(rss)],
        ):
            result = web_search.invoke({"query": "langgraph", "max_results": 2})

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "Bing Result")
        self.assertEqual(result["items"][0]["content"], "Bing snippet with markup")
        self.assertEqual(result["items"][0]["url"], "https://example.com/bing")

    def test_web_search_supports_baidu_backend(self):
        html = """
        <html>
          <body>
            <div class="result c-container" mu="https://example.com/baidu">
              <h3><a href="http://www.baidu.com/link?url=abc">Baidu <em>Result</em></a></h3>
              <div class="c-abstract">Baidu snippet with <em>markup</em></div>
            </div>
          </body>
        </html>
        """

        with (
            patch("eco_rag.tools.web_search.load_app_settings", return_value=AppSettings(web_search_backend="baidu")),
            patch("eco_rag.tools.web_search.urlopen", return_value=_FakeResponse(html)),
        ):
            result = web_search.invoke({"query": "langgraph", "max_results": 2})

        self.assertEqual(result["backend"], "baidu")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "Baidu Result")
        self.assertEqual(result["items"][0]["content"], "Baidu snippet with markup")
        self.assertEqual(result["items"][0]["url"], "https://example.com/baidu")

    def test_web_search_rejects_empty_queries(self):
        result = web_search.invoke({"query": "   "})

        self.assertEqual(result["items"], [])
        self.assertEqual(result["error"], "Query cannot be empty.")


class WebFetchTests(unittest.TestCase):
    def test_web_fetch_extracts_title_and_visible_text(self):
        html = """
        <html>
          <head>
            <title>Example Page</title>
            <style>.hidden { display: none; }</style>
          </head>
          <body>
            <h1>Visible heading</h1>
            <script>const secret = "hidden";</script>
            <p>Readable body text.</p>
          </body>
        </html>
        """

        with patch("eco_rag.tools.web_fetch.urlopen", return_value=_FakeResponse(html)):
            result = web_fetch.invoke({"url": "https://example.com/page", "max_chars": 200})

        self.assertEqual(result["skill_name"], "web_fetch")
        self.assertNotIn("error", result)
        self.assertEqual(result["items"][0]["title"], "Example Page")
        self.assertEqual(result["items"][0]["url"], "https://example.com/page")
        self.assertIn("Visible heading", result["items"][0]["content"])
        self.assertIn("Readable body text.", result["items"][0]["content"])
        self.assertNotIn("hidden", result["items"][0]["content"])

    def test_web_fetch_truncates_content(self):
        html = "<html><body>abcdefghijklmnopqrstuvwxyz</body></html>"

        with patch("eco_rag.tools.web_fetch.urlopen", return_value=_FakeResponse(html)):
            result = web_fetch.invoke({"url": "https://example.com/page", "max_chars": 5})

        self.assertEqual(result["items"][0]["content"], "abcde")

    def test_web_fetch_rejects_invalid_url(self):
        result = web_fetch.invoke({"url": "ftp://example.com/page"})

        self.assertEqual(result["items"], [])
        self.assertIn("http or https URL", result["error"])


if __name__ == "__main__":
    unittest.main()
