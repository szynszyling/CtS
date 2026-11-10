import io
import unittest
import urllib.error
import urllib.parse
from email.message import Message
from unittest.mock import patch

from circle_to_search.search import (
    NoRedirect,
    browser_search_url,
    external_navigation,
    normalize_search_url,
    search_tab,
    search_tab_url,
    text_search_url,
    translation_url,
    upload_to_lens,
    valid_results_url,
)


class SearchTests(unittest.TestCase):
    def test_result_destinations_use_the_system_opener_including_google_sites(self):
        for url in [
            "https://example.org/page",
            "https://support.google.com/websearch/answer/86640",
            "https://docs.google.com/document/example",
            "mailto:example@example.org",
            "magnet:?xt=example",
        ]:
            self.assertTrue(external_navigation(url), url)

    def test_search_tabs_previews_translation_and_verification_stay_embedded(self):
        for url in [
            text_search_url("test"),
            search_tab_url("", "images", "test"),
            translation_url("日本語"),
            "https://lens.google.com/v3/upload",
            "https://www.google.com/imgres?imgurl=example",
            "https://www.google.com/sorry/index",
            "https://consent.google.com/m",
            "https://accounts.google.com/ServiceLogin",
        ]:
            self.assertFalse(external_navigation(url), url)

    def test_explicit_new_tab_opens_externally_even_for_a_google_search(self):
        self.assertTrue(external_navigation(text_search_url("test"), new_window=True))

    def test_in_page_and_browser_local_schemes_do_not_launch_applications(self):
        for url in [
            "#section",
            "about:blank",
            "javascript:void(0)",
            "data:text/html,test",
            "blob:https://example.org/test",
            "file:///tmp/test",
        ]:
            self.assertFalse(external_navigation(url), url)

    def redirect(self, url, code=302):
        headers = Message()
        if url is not None:
            headers["Location"] = url
        return urllib.error.HTTPError(
            "https://lens.google.com/v3/upload", code, "redirect", headers, io.BytesIO()
        )

    @patch("circle_to_search.search.urllib.request.build_opener")
    def test_upload_sends_crop_and_opens_only_returned_google_link(self, builder):
        builder.return_value.open.side_effect = self.redirect(
            "https://lens.google.com/search?p=example"
        )
        result = urllib.parse.parse_qs(urllib.parse.urlsplit(upload_to_lens(b"CROP-ONLY")).query)
        self.assertEqual(result["p"], ["example"])
        self.assertEqual(result["hl"], ["en"])
        self.assertNotIn("gsc", result)
        request = builder.return_value.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn(b'name="encoded_image"; filename="selection.png"', request.data)
        self.assertIn(b"\r\n\r\nCROP-ONLY\r\n", request.data)
        self.assertEqual(request.get_header("Cookie"), "SOCS=CAI")
        builder.return_value.open.assert_called_once()

    @patch("circle_to_search.search.urllib.request.build_opener")
    def test_upload_rejects_redirect_to_other_site(self, builder):
        builder.return_value.open.side_effect = self.redirect("https://attacker.example/search")
        with self.assertRaisesRegex(RuntimeError, "Open Lens"):
            upload_to_lens(b"crop")

    @patch("circle_to_search.search.urllib.request.build_opener")
    def test_missing_location_is_a_failure(self, builder):
        builder.return_value.open.side_effect = self.redirect(None)
        with self.assertRaises(RuntimeError):
            upload_to_lens(b"crop")

    @patch("circle_to_search.search.urllib.request.build_opener")
    def test_rate_limit_explains_manual_fallback(self, builder):
        builder.return_value.open.side_effect = self.redirect(None, 429)
        with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
            upload_to_lens(b"crop")

    @patch("circle_to_search.search.urllib.request.build_opener")
    def test_network_error_is_actionable(self, builder):
        builder.return_value.open.side_effect = urllib.error.URLError("offline")
        with self.assertRaisesRegex(RuntimeError, "connection"):
            upload_to_lens(b"crop")

    def test_no_redirect_handler_never_follows_or_reposts(self):
        self.assertIsNone(
            NoRedirect().redirect_request(None, None, 307, "", {}, "https://elsewhere.example")
        )

    def test_results_url_allowlist(self):
        for url in [
            "http://google.com/search",
            "https://google.com.evil.test/search",
            "https://consent.google.com/m",
            "file:///tmp/test",
            "https://user@google.com/search",
            "https://google.com:123/search",
            "https://google.com:bad/search",
        ]:
            self.assertFalse(valid_results_url(url), url)
        self.assertTrue(valid_results_url("https://www.google.com/search?q=test"))

    def test_google_preferences_override_polish_and_dark_theme_without_losing_image(self):
        url = normalize_search_url("https://www.google.com/search?hl=pl&cs=1&vsrid=example&udm=26")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["hl"], ["en"])
        self.assertNotIn("cs", query)
        self.assertEqual(query["vsrid"], ["example"])
        self.assertEqual(query["udm"], ["26"])

    def test_search_uses_public_route_without_special_rendering_parameters(self):
        url = normalize_search_url(
            "https://www.google.com/search?q=translate&gsc=2&cs=0&gl=us&lr=lang_en"
        )
        self.assertEqual(
            urllib.parse.parse_qs(urllib.parse.urlsplit(url).query),
            {"q": ["translate"], "hl": ["en"]},
        )

    def test_verification_and_external_urls_are_not_rewritten(self):
        for url in [
            "https://www.google.com/sorry/index?continue=example",
            "https://example.org/search?q=example",
        ]:
            self.assertEqual(normalize_search_url(url), url)

    def test_browser_handoff_keeps_query_and_lens_session_on_the_public_route(self):
        url = "https://www.google.com/search?q=日本語&vsrid=image123&udm=24&gsc=2"
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(browser_search_url(url)).query)
        self.assertNotIn("gsc", params)
        self.assertEqual(params["q"], ["日本語"])
        self.assertEqual(params["vsrid"], ["image123"])
        self.assertEqual(params["udm"], ["24"])

    def test_japanese_url_normalization_does_not_create_a_redirect_loop(self):
        from PySide6.QtCore import QUrl

        url = QUrl(text_search_url("日本語 meaning"))
        self.assertEqual(QUrl(normalize_search_url(url.toString())), url)

    def test_search_tabs_preserve_the_query_and_reset_old_view_parameters(self):
        url = "https://www.google.com/search?q=docs%2FREFERENCE.md&tbm=vid&start=20&hl=pl"
        images = search_tab_url(url, "images")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(images).query)
        self.assertEqual(query["q"], ["docs/REFERENCE.md"])
        self.assertEqual(query["udm"], ["2"])
        self.assertNotIn("tbm", query)
        self.assertNotIn("start", query)
        self.assertEqual(search_tab(images), "images")

    def test_ai_mode_is_available_from_an_image_search(self):
        url = search_tab_url("https://www.google.com/search?q=videos&tbm=isch", "ai")
        self.assertEqual(search_tab(url), "ai")
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["q"], ["videos"])

    def test_all_tab_clears_legacy_video_filter(self):
        url = search_tab_url("https://www.google.com/search?q=hello&tbm=vid", "all")
        self.assertEqual(search_tab(url), "all")
        self.assertNotIn("tbm", urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))

    def test_lens_session_survives_switching_views_and_returning_to_all(self):
        original = (
            "https://www.google.com/search?vsrid=image123&gsessionid=session456&udm=26&lns_mode=un"
        )
        images = search_tab_url(original, "images")
        restored = search_tab_url(images, "all")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(restored).query)
        self.assertEqual(query["vsrid"], ["image123"])
        self.assertEqual(query["gsessionid"], ["session456"])
        self.assertEqual(query["udm"], ["26"])

    def test_all_native_search_modes_are_distinguishable(self):
        for tab in ("ai", "all", "images", "videos", "shopping", "news", "forums", "web", "books"):
            with self.subTest(tab=tab):
                self.assertEqual(search_tab(search_tab_url("", tab, "日本語")), tab)

    def test_text_queries_escape_unicode_and_special_characters(self):
        text = "zażółć & a+b? #/"
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(text_search_url(text)).query)
        self.assertEqual(query["q"], [text])
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(translation_url(text, "pl")).query)
        self.assertEqual(query["text"], [text])
        self.assertEqual(query["tl"], ["pl"])

    @patch("circle_to_search.search.urllib.request.build_opener")
    def test_image_search_refinement_preserves_lens_session(self, builder):
        builder.return_value.open.side_effect = self.redirect(
            "https://www.google.com/search?udm=26&vsrid=example"
        )
        url = upload_to_lens(b"crop", "日本語 & more")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["q"], ["日本語 & more"])
        self.assertEqual(query["vsrid"], ["example"])
