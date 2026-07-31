import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pytest

from scripts.add_figures import build_entry, known_names, load_json, with_retry
from scripts.enrich_figures import FetchError


class TestBuildEntry(unittest.TestCase):
    def test_complete_figure_yields_entry(self):
        with patch("scripts.add_figures.fetch_summary_strict",
                   side_effect=[("bio fr", "http://img/x.jpg"), ("bio en", None)]):
            entry, reason = build_entry("Vauban")
        self.assertIsNone(reason)
        self.assertEqual(entry["name"], "Vauban")
        self.assertEqual(entry["bio_fr"], "bio fr")
        self.assertEqual(entry["bio_en"], "bio en")
        self.assertEqual(entry["image_url"], "http://img/x.jpg")
        # Rédaction laissée à l'humain, mais les clés existent.
        self.assertEqual(entry["description"], "")
        self.assertEqual(entry["facts_fr"], [])
        self.assertEqual(entry["facts_en"], [])

    def test_missing_portrait_is_rejected_with_reason(self):
        with patch("scripts.add_figures.fetch_summary_strict",
                   side_effect=[("bio fr", None), ("bio en", None)]):
            entry, reason = build_entry("Sans Portrait")
        self.assertIsNone(entry)
        self.assertIn("portrait", reason)

    def test_missing_french_article_is_rejected_with_reason(self):
        with patch("scripts.add_figures.fetch_summary_strict",
                   side_effect=[("", None), ("bio en", "http://img/x.jpg")]):
            entry, reason = build_entry("EN Seulement")
        self.assertIsNone(entry)
        self.assertIn("bio_fr", reason)

    def test_portrait_falls_back_to_english_thumbnail(self):
        with patch("scripts.add_figures.fetch_summary_strict",
                   side_effect=[("bio fr", None), ("bio en", "http://img/en.jpg")]):
            entry, reason = build_entry("Portrait EN")
        self.assertIsNone(reason)
        self.assertEqual(entry["image_url"], "http://img/en.jpg")

    def test_network_failure_propagates_and_never_rejects(self):
        """La régression à ne jamais réintroduire : un throttling qui se
        traduirait par un rejet de figure."""
        with patch("scripts.add_figures.time.sleep"), \
             patch("scripts.add_figures.fetch_summary_strict", side_effect=FetchError("HTTP 429")):
            with pytest.raises(FetchError):
                build_entry("William Shakespeare")

    def test_wikidata_id_carried_from_overrides(self):
        overrides = {"Aristide": {"fr": "Aristide le Juste", "en": "Aristides", "wikidata_id": "Q184960"}}
        with patch("scripts.add_figures.OVERRIDES", overrides), \
             patch("scripts.add_figures.fetch_summary_strict",
                   side_effect=[("bio fr", "http://img/x.jpg"), ("bio en", None)]):
            entry, _ = build_entry("Aristide")
        self.assertEqual(entry["wikidata_id"], "Q184960")


class TestWithRetry(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = []

        def flaky(*args):
            calls.append(args)
            if len(calls) < 3:
                raise FetchError("HTTP 429")
            return ("ok", None)

        with patch("scripts.add_figures.time.sleep"):
            self.assertEqual(with_retry(flaky, "fr", "X"), ("ok", None))
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_attempts_and_raises(self):
        def always_fails(*args):
            raise FetchError("HTTP 429")

        with patch("scripts.add_figures.time.sleep"):
            with pytest.raises(FetchError):
                with_retry(always_fails, "fr", "X")


class TestKnownNames(unittest.TestCase):
    def test_merges_roster_and_staging(self):
        figures = [{"name": "Colbert"}, {"name": "De Lesseps"}]
        pending = [{"name": "Vauban"}]
        self.assertCountEqual(known_names(figures, pending), ["Colbert", "De Lesseps", "Vauban"])


class TestLoadJson(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)
        self.addCleanup(lambda: os.path.exists(self.path) and os.unlink(self.path))

    def test_missing_file_returns_default(self):
        self.assertEqual(load_json(self.path, []), [])

    def test_existing_file_is_read(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([{"name": "X"}], f)
        self.assertEqual(load_json(self.path, []), [{"name": "X"}])


if __name__ == "__main__":
    unittest.main()
