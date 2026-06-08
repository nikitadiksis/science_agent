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


    def test_extract_image_url_from_html_prefers_og_image(self):
        html = """
        <html>
          <head>
            <meta property="og:image" content="/images/mars.jpg?utm_source=site" />
          </head>
        </html>
        """
        image_url = news_agent.extract_image_url_from_html(html, "https://science.nasa.gov/photojournal/story")
        self.assertEqual(image_url, "https://science.nasa.gov/images/mars.jpg")

    def test_send_to_telegram_uses_send_photo_for_short_caption(self):
        calls = []

        class FakeResponse:
            status_code = 200
            text = "ok"

        def fake_post(url, json=None, timeout=None):
            calls.append((url, json, timeout))
            return FakeResponse()

        old_session = news_agent.session
        news_agent.session = types.SimpleNamespace(post=fake_post)
        try:
            ok = news_agent.send_to_telegram_v2("Short post", "chat-id", image_url="https://example.com/image.jpg")
        finally:
            news_agent.session = old_session

        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        self.assertIn("/sendPhoto", calls[0][0])
        self.assertEqual(calls[0][1]["photo"], "https://example.com/image.jpg")
        self.assertIn("caption", calls[0][1])

    def test_should_attach_source_image_for_visual_space_news(self):
        item = {
            "title": "Psyche captured a high-resolution image of Mars south pole",
            "summary": "The snapshot shows the polar cap in detail.",
        }
        self.assertTrue(news_agent.should_attach_source_image(item, topic="space"))

    def test_should_not_attach_source_image_for_plain_funding_news(self):
        item = {
            "title": "Ramp raises $750M at a $40B valuation",
            "summary": "The fintech company is in talks for a new funding round.",
        }
        self.assertFalse(news_agent.should_attach_source_image(item, topic="business_tech"))

    def test_send_to_max_posts_html_message(self):
        calls = []

        class FakeResponse:
            status_code = 200
            text = "ok"

        def fake_post(url, params=None, headers=None, json=None, timeout=None):
            calls.append((url, params, headers, json, timeout))
            return FakeResponse()

        old_session = news_agent.session
        old_token = news_agent.MAX_BOT_TOKEN
        news_agent.session = types.SimpleNamespace(post=fake_post)
        news_agent.MAX_BOT_TOKEN = "max-token"
        try:
            ok = news_agent.send_to_max("<b>Hello</b>", "-123")
        finally:
            news_agent.session = old_session
            news_agent.MAX_BOT_TOKEN = old_token

        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "https://platform-api.max.ru/messages")
        self.assertEqual(calls[0][1]["chat_id"], "-123")
        self.assertEqual(calls[0][3]["format"], "html")

    def test_send_to_max_adds_image_attachment_when_upload_succeeds(self):
        calls = []

        class FakeResponse:
            status_code = 200
            text = "ok"

        def fake_post(url, params=None, headers=None, json=None, timeout=None):
            calls.append((url, params, headers, json, timeout))
            return FakeResponse()

        old_session = news_agent.session
        old_token = news_agent.MAX_BOT_TOKEN
        old_upload = news_agent.upload_image_to_max
        news_agent.session = types.SimpleNamespace(post=fake_post)
        news_agent.MAX_BOT_TOKEN = "max-token"
        news_agent.upload_image_to_max = lambda image_url: "img-token"
        try:
            ok = news_agent.send_to_max("<b>Hello</b>", "-123", image_url="https://example.com/image.jpg")
        finally:
            news_agent.session = old_session
            news_agent.MAX_BOT_TOKEN = old_token
            news_agent.upload_image_to_max = old_upload

        self.assertTrue(ok)
        self.assertEqual(calls[0][3]["attachments"][0]["type"], "image")
        self.assertEqual(calls[0][3]["attachments"][0]["payload"]["token"], "img-token")

    def test_upload_image_to_max_extracts_token_from_photos_payload(self):
        class FakeResponse:
            def __init__(self, status_code, text, json_data=None):
                self.status_code = status_code
                self.text = text
                self._json_data = json_data or {}

            def json(self):
                return self._json_data

        calls = []

        def fake_post(url, params=None, headers=None, files=None, timeout=None, json=None):
            calls.append((url, params, headers, files, timeout, json))
            if "platform-api.max.ru/uploads" in url:
                return FakeResponse(200, "ok", {"url": "https://upload.example.com/file"})
            return FakeResponse(200, "ok", {"photos": {"photo-id": {"token": "nested-token"}}})

        old_session = news_agent.session
        old_token = news_agent.MAX_BOT_TOKEN
        old_fetch = news_agent.fetch_image_bytes
        news_agent.session = types.SimpleNamespace(post=fake_post)
        news_agent.MAX_BOT_TOKEN = "max-token"
        news_agent.fetch_image_bytes = lambda image_url: (b"png-bytes", "test.png", "image/png")
        try:
            token = news_agent.upload_image_to_max("https://example.com/image.png")
        finally:
            news_agent.session = old_session
            news_agent.MAX_BOT_TOKEN = old_token
            news_agent.fetch_image_bytes = old_fetch

        self.assertEqual(token, "nested-token")

    def test_publish_to_platforms_succeeds_if_one_platform_succeeds(self):
        old_send_tg = news_agent.send_to_telegram_v2
        old_send_max = news_agent.send_to_max
        old_tg_token = news_agent.TELEGRAM_TOKEN
        old_channel = news_agent.CHANNEL_ID
        old_max_token = news_agent.MAX_BOT_TOKEN
        old_max_chat = news_agent.MAX_CHAT_ID

        news_agent.send_to_telegram_v2 = lambda text, chat_id, image_url="": False
        news_agent.send_to_max = lambda text, chat_id, image_url="": True
        news_agent.TELEGRAM_TOKEN = "tg"
        news_agent.CHANNEL_ID = "channel"
        news_agent.MAX_BOT_TOKEN = "max"
        news_agent.MAX_CHAT_ID = "-1"
        try:
            result = news_agent.publish_to_platforms("post text")
        finally:
            news_agent.send_to_telegram_v2 = old_send_tg
            news_agent.send_to_max = old_send_max
            news_agent.TELEGRAM_TOKEN = old_tg_token
            news_agent.CHANNEL_ID = old_channel
            news_agent.MAX_BOT_TOKEN = old_max_token
            news_agent.MAX_CHAT_ID = old_max_chat

        self.assertFalse(result["telegram"])
        self.assertTrue(result["max"])
        self.assertTrue(result["any_success"])

    def test_format_run_report_includes_platform_publish_counts(self):
        report = news_agent.format_run_report({
            "published": 1,
            "published_telegram": 1,
            "published_max": 1,
        })
        self.assertIn("Опубликовано новостей: 1", report)
        self.assertIn("в Telegram: 1", report)
        self.assertIn("в MAX: 1", report)

    def test_cleanup_rewrite_output_removes_editorial_chatter(self):
        raw = "Human: хорошо\nВот исправленный вариант:\nTitle\n\n• fact"
        cleaned = news_agent.cleanup_rewrite_output(raw)
        self.assertEqual(cleaned, "Title\n\n• fact")

    def test_has_bad_rewrite_artifacts_detects_dialogue_markers(self):
        self.assertTrue(news_agent.has_bad_rewrite_artifacts("Human: fix this"))
        self.assertFalse(news_agent.has_bad_rewrite_artifacts("Title\n\n• fact one\n• fact two\n• fact three"))

    def test_has_bad_rewrite_quality_detects_broken_repeated_words(self):
        bad = (
            "Anthropanthropic привлёк $65 млрд\n\n"
            "Основатель LinkedIn LinkedIn и партнёр Greylock Ррид Хоффман "
            "сосреднаредоточинаться на своём стартапАп Manus, которй занимается "
            "раз разработклекой лекарсств с помощискью инт.интллекта."
        )
        self.assertTrue(news_agent.has_bad_rewrite_quality(bad))

    def test_has_bad_rewrite_quality_allows_normal_post(self):
        good = (
            "Anthropic привлёк $6,5 млрд для развития ИИ\n\n"
            "Anthropic, создатель Claude, закрыл новый раунд инвестиций.\n"
            "• Оценка компании выросла до $61,5 млрд\n"
            "• В раунде участвуют крупные технологические инвесторы"
        )
        self.assertFalse(news_agent.has_bad_rewrite_quality(good))


if __name__ == "__main__":
    unittest.main()
