import importlib.util
import os
import sys
import types
import unittest
from xml.etree import ElementTree


def load_news_agent():
    os.environ.setdefault("TELEGRAM_TOKEN", "test-token")
    os.environ.setdefault("CHANNEL_ID", "test-channel")
    os.environ.setdefault("OPENROUTER_KEY", "test-key")

    requests = types.ModuleType("requests")
    requests.Session = lambda: types.SimpleNamespace(
        headers={},
        get=lambda *args, **kwargs: None,
        post=lambda *args, **kwargs: None,
    )
    requests.exceptions = types.SimpleNamespace(
        Timeout=TimeoutError,
        ConnectionError=ConnectionError,
        RequestException=Exception,
    )
    sys.modules.setdefault("requests", requests)

    defusedxml = types.ModuleType("defusedxml")
    defusedxml.ElementTree = ElementTree
    sys.modules.setdefault("defusedxml", defusedxml)

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None
    sys.modules.setdefault("dotenv", dotenv)

    sentence_transformers = types.ModuleType("sentence_transformers")
    sentence_transformers.SentenceTransformer = object
    sentence_transformers.util = types.SimpleNamespace()
    sys.modules.setdefault("sentence_transformers", sentence_transformers)

    spec = importlib.util.spec_from_file_location("news_agent", "news_agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


news_agent = load_news_agent()


class NewsAgentPureTests(unittest.TestCase):
    def test_normalize_url_removes_tracking_and_fragment(self):
        url = "HTTPS://Example.COM/path/?utm_source=x&a=1&fbclid=y#section"
        self.assertEqual(news_agent.normalize_url(url), "https://example.com/path/?a=1")

    def test_parse_pub_date_supports_iso_z(self):
        parsed = news_agent.parse_pub_date("2026-05-03T10:20:30Z")
        self.assertEqual(parsed.isoformat(), "2026-05-03T10:20:30+00:00")

    def test_parse_feed_items_supports_atom(self):
        root = news_agent.ET.fromstring(
            """<?xml version="1.0"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <title>Atom title</title>
                <link href="https://example.com/story?utm_source=rss" rel="alternate" type="text/html" />
                <summary>Atom summary</summary>
                <updated>2026-05-03T10:20:30Z</updated>
              </entry>
            </feed>
            """
        )
        items = news_agent.parse_feed_items(root, "feed-url", "Atom Source", 1.0, "science", "news")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Atom title")
        self.assertEqual(items[0]["link"], "https://example.com/story")

    def test_source_repeat_penalty_is_soft(self):
        posted = [{"source": "A"}, {"source": "B"}]
        self.assertEqual(news_agent.source_repeat_penalty("B", posted), news_agent.SAME_SOURCE_LAST_POST_PENALTY)
        self.assertEqual(news_agent.source_repeat_penalty("A", posted), news_agent.SAME_SOURCE_RECENT_PENALTY)
        self.assertEqual(news_agent.source_repeat_penalty("C", posted), 1.0)

    def test_build_telegram_post_keeps_valid_html_under_limit(self):
        text = "Title\n\n" + ("- fact & detail <x>\n" * 1000)
        post = news_agent.build_telegram_post(text, "https://example.com/?utm_source=x&a=1")
        self.assertLessEqual(len(post), news_agent.TELEGRAM_MESSAGE_LIMIT)
        self.assertIn("&lt;x&gt;", post)
        self.assertEqual(post.count("<a href="), 1)

    def test_build_rewrite_prompt_requires_company_context_and_flexible_format(self):
        prompt = news_agent.build_rewrite_prompt("Ramp raises funding", "Ramp is a fintech company.")
        self.assertIn("не загоняй каждую новость в буллеты", prompt.lower())
        self.assertIn("обязательно добавь это в начале текста одной короткой фразой", prompt.lower())
        self.assertIn("короткий абзац на 2–4 предложения", prompt)
        self.assertIn("смешанный формат", prompt.lower())


if __name__ == "__main__":
    unittest.main()
