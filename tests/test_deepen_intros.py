import unittest
import urllib.error
from unittest.mock import patch

import pytest

from scripts.enrich_figures import FetchError, OVERRIDES, fetch_article_strict, resolve_titles
from scripts.deepen_intros import (
    MARGIN_THRESHOLD, deepen_pending, is_authored, margin, needs_deepening,
)


class TestMargin(unittest.TestCase):
    def test_computes_difference(self):
        self.assertEqual(margin("hello world", "hello"), 6)

    def test_missing_intro_is_negative_bio_length(self):
        self.assertEqual(margin("", "hello"), -5)
        self.assertEqual(margin(None, "hello"), -5)

    def test_missing_bio_is_full_intro_length(self):
        self.assertEqual(margin("hello", ""), 5)
        self.assertEqual(margin("hello", None), 5)


class TestIsAuthored(unittest.TestCase):
    def test_three_facts_each_language_is_authored(self):
        fig = {"facts_fr": ["a", "b", "c"], "facts_en": ["a", "b", "c"]}
        self.assertTrue(is_authored(fig))

    def test_fewer_than_three_in_either_language_is_not_authored(self):
        self.assertFalse(is_authored({"facts_fr": ["a"], "facts_en": ["a", "b", "c"]}))
        self.assertFalse(is_authored({"facts_fr": ["a", "b", "c"], "facts_en": []}))

    def test_missing_keys_is_not_authored(self):
        self.assertFalse(is_authored({}))


class TestNeedsDeepening(unittest.TestCase):
    def test_below_threshold_needs_deepening(self):
        fig = {"facts_fr": [], "facts_en": []}
        self.assertTrue(needs_deepening(fig, 100))

    def test_above_threshold_does_not_need_deepening(self):
        fig = {"facts_fr": [], "facts_en": []}
        self.assertFalse(needs_deepening(fig, MARGIN_THRESHOLD))

    def test_already_authored_figure_is_ignored_even_if_thin(self):
        fig = {"facts_fr": ["a", "b", "c"], "facts_en": ["a", "b", "c"]}
        self.assertFalse(needs_deepening(fig, 0))


class TestFetchArticleStrict(unittest.TestCase):
    def test_truncates_to_max_chars(self):
        payload = {"query": {"pages": {"123": {"extract": "x" * 100}}}}
        with patch("scripts.enrich_figures._get_json", return_value=payload):
            text = fetch_article_strict("fr", "X", max_chars=10)
        self.assertEqual(text, "x" * 10)

    def test_returns_full_text_when_under_max_chars(self):
        payload = {"query": {"pages": {"123": {"extract": "short article"}}}}
        with patch("scripts.enrich_figures._get_json", return_value=payload):
            self.assertEqual(fetch_article_strict("fr", "X"), "short article")

    def test_404_returns_empty_string(self):
        err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        with patch("scripts.enrich_figures._get_json", side_effect=err):
            self.assertEqual(fetch_article_strict("fr", "Nimportequoi"), "")

    def test_429_raises_fetch_error(self):
        err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
        with patch("scripts.enrich_figures._get_json", side_effect=err):
            with pytest.raises(FetchError):
                fetch_article_strict("fr", "X")

    def test_network_error_raises_fetch_error(self):
        with patch("scripts.enrich_figures._get_json", side_effect=urllib.error.URLError("timed out")):
            with pytest.raises(FetchError):
                fetch_article_strict("fr", "X")


class TestDeepenPending(unittest.TestCase):
    @staticmethod
    def _fig(name, facts_fr=None, facts_en=None, bio_fr="", bio_en=""):
        return {
            "name": name,
            "facts_fr": facts_fr or [],
            "facts_en": facts_en or [],
            "bio_fr": bio_fr,
            "bio_en": bio_en,
        }

    def test_fully_authored_figure_is_skipped_entirely(self):
        fig = self._fig("Done", facts_fr=["a", "b", "c"], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        intros = {"Done": {"fr": "", "en": ""}}
        with patch("scripts.deepen_intros.fetch_article_strict") as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig], intros)
        fetch_mock.assert_not_called()
        self.assertEqual(deepened, [])
        self.assertEqual(still_thin, [])

    def test_margin_above_threshold_is_left_alone(self):
        fig = self._fig("Wide", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        intros = {"Wide": {"fr": "x" * 500, "en": "y" * 500}}
        with patch("scripts.deepen_intros.fetch_article_strict") as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig], intros)
        fetch_mock.assert_not_called()
        self.assertEqual(intros["Wide"]["fr"], "x" * 500)
        self.assertEqual(intros["Wide"]["en"], "y" * 500)

    def test_dry_run_lists_without_fetching_or_writing(self):
        fig = self._fig("Thin", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        intros = {"Thin": {"fr": "short", "en": ""}}
        with patch("scripts.deepen_intros.fetch_article_strict") as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep") as sleep_mock:
            deepened, still_thin = deepen_pending([fig], intros, dry_run=True)
        fetch_mock.assert_not_called()
        sleep_mock.assert_not_called()
        self.assertEqual(deepened, [])
        self.assertEqual(intros["Thin"]["fr"], "short")
        self.assertTrue(any(name == "Thin" and lang == "fr" for name, lang, _m in still_thin))

    def test_longer_fetched_text_replaces_thin_intro(self):
        fig = self._fig("Thin", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        intros = {"Thin": {"fr": "short", "en": "y" * 500}}
        replacement = "a much longer article body " * 5
        with patch("scripts.deepen_intros.fetch_article_strict", return_value=replacement), \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig], intros)
        self.assertEqual(intros["Thin"]["fr"], replacement)
        self.assertEqual(len(deepened), 1)
        name, lang, before, after = deepened[0]
        self.assertEqual((name, lang), ("Thin", "fr"))
        self.assertGreater(after, before)

    def test_shorter_fetched_text_does_not_overwrite_existing_intro(self):
        """Règle de non-régression : ne jamais perdre une intro existante."""
        fig = self._fig("Thin", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        existing = "a fairly long existing intro that is already decent " * 3
        intros = {"Thin": {"fr": existing, "en": "y" * 500}}
        with patch("scripts.deepen_intros.fetch_article_strict", return_value="short"), \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig], intros)
        self.assertEqual(intros["Thin"]["fr"], existing)
        self.assertEqual(deepened, [])
        self.assertTrue(any(name == "Thin" and lang == "fr" for name, lang, _m in still_thin))

    def test_fetch_error_leaves_intro_untouched_and_does_not_interrupt_others(self):
        fig_x = self._fig("X", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        fig_y = self._fig("Y", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        intros = {
            "X": {"fr": "existing intro for X", "en": ""},
            "Y": {"fr": "existing intro for Y", "en": ""},
        }
        replacement = "a much longer replacement article body text " * 5

        def fake_fetch(lang, title, max_chars=8000):
            resolved = resolve_titles("X", OVERRIDES)
            if lang == "fr" and title == resolved["fr"]:
                raise FetchError("boom")
            return replacement

        with patch("scripts.deepen_intros.fetch_article_strict", side_effect=fake_fetch), \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig_x, fig_y], intros)

        self.assertEqual(intros["X"]["fr"], "existing intro for X")
        self.assertEqual(intros["Y"]["fr"], replacement)
        self.assertTrue(any(name == "Y" and lang == "fr" for name, lang, _b, _a in deepened))
        self.assertTrue(any(name == "X" and lang == "fr" for name, lang, _m in still_thin))

    def test_names_restricts_working_set(self):
        """Seule la figure nommée doit être touchée, même si une autre serait
        elle aussi sous le seuil. --names traite les deux langues, donc deux
        appels attendus — aucun pour la figure non nommée."""
        target = self._fig("Copernic", facts_fr=["a", "b"], facts_en=["a", "b", "c"],
                            bio_fr="bio", bio_en="bio")
        other = self._fig("Fleming", facts_fr=["a", "b"], facts_en=["a", "b", "c"],
                           bio_fr="bio", bio_en="bio")
        intros = {
            "Copernic": {"fr": "short fr", "en": "short en"},
            "Fleming": {"fr": "short fr too", "en": "y" * 500},
        }
        replacement = "a much longer article body text " * 5
        with patch("scripts.deepen_intros.fetch_article_strict", return_value=replacement) as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([target, other], intros, names=["Copernic"])
        self.assertTrue(any(name == "Copernic" for name, *_ in deepened))
        self.assertFalse(any(name == "Fleming" for name, *_ in deepened + still_thin))
        self.assertEqual(fetch_mock.call_count, 2)
        called_langs = {call.args[0] for call in fetch_mock.call_args_list}
        self.assertEqual(called_langs, {"fr", "en"})

    def test_names_bypasses_margin_check(self):
        """Copernic/Fleming : marge au-dessus du seuil par défaut mais matière
        épuisée — --names doit quand même déclencher la récupération."""
        fig = self._fig("Copernic", facts_fr=["a", "b"], facts_en=["a", "b", "c"],
                         bio_fr="bio", bio_en="bio")
        # Marge très au-dessus de MARGIN_THRESHOLD : le chemin normal l'ignorerait.
        wide_intro = "x" * (MARGIN_THRESHOLD + 1000)
        intros = {"Copernic": {"fr": wide_intro, "en": "y" * 500}}
        replacement = "z" * (len(wide_intro) + 1)
        with patch("scripts.deepen_intros.fetch_article_strict", return_value=replacement) as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep"):
            deepened_default, _ = deepen_pending([fig], dict(intros))
            deepened_forced, _ = deepen_pending([fig], intros, names=["Copernic"])
        self.assertEqual(deepened_default, [])  # chemin normal : marge trop large, ignoré
        self.assertTrue(any(name == "Copernic" and lang == "fr" for name, lang, *_ in deepened_forced))
        # --names force les DEUX langues, sans regarder la marge : c'est sa
        # propriété définissante. >= 1 laisserait passer une dégradation
        # silencieuse à une seule langue.
        self.assertEqual(fetch_mock.call_count, 2)

    def test_names_still_refuses_shorter_text(self):
        """La non-régression n'a pas de dérogation via --names."""
        fig = self._fig("Copernic", facts_fr=["a", "b"], facts_en=["a", "b", "c"],
                         bio_fr="bio", bio_en="bio")
        existing = "a long existing intro that should not be lost " * 3
        intros = {"Copernic": {"fr": existing, "en": "y" * 500}}
        with patch("scripts.deepen_intros.fetch_article_strict", return_value="short"), \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig], intros, names=["Copernic"])
        self.assertEqual(intros["Copernic"]["fr"], existing)
        self.assertFalse(any(name == "Copernic" and lang == "fr" for name, lang, *_ in deepened))
        self.assertTrue(any(name == "Copernic" and lang == "fr" for name, lang, _m in still_thin))

    def test_names_dry_run_lists_regardless_of_margin_without_fetching(self):
        fig = self._fig("Copernic", facts_fr=["a", "b"], facts_en=["a", "b", "c"],
                         bio_fr="bio", bio_en="bio")
        intros = {"Copernic": {"fr": "x" * (MARGIN_THRESHOLD + 1000), "en": "y" * 500}}
        with patch("scripts.deepen_intros.fetch_article_strict") as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep") as sleep_mock:
            deepened, still_thin = deepen_pending([fig], intros, dry_run=True, names=["Copernic"])
        fetch_mock.assert_not_called()
        sleep_mock.assert_not_called()
        self.assertEqual(deepened, [])
        self.assertTrue(any(name == "Copernic" and lang == "fr" for name, lang, _m in still_thin))
        self.assertTrue(any(name == "Copernic" and lang == "en" for name, lang, _m in still_thin))

    def test_custom_threshold_excludes_pair_default_would_include(self):
        fig = self._fig("Mince", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        # Marge 100 : sous le seuil par défaut (300), au-dessus d'un seuil de 50.
        intros = {"Mince": {"fr": "x" * 103, "en": "y" * 500}}
        with patch("scripts.deepen_intros.fetch_article_strict") as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep"):
            deepened, still_thin = deepen_pending([fig], intros, threshold=50)
        fetch_mock.assert_not_called()
        self.assertEqual(deepened, [])
        self.assertFalse(any(lang == "fr" for _n, lang, _m in still_thin))

    def test_custom_threshold_includes_pair_default_would_exclude(self):
        fig = self._fig("Large", facts_fr=[], facts_en=["a", "b", "c"], bio_fr="bio", bio_en="bio")
        # fr : marge 400, au-dessus du seuil par défaut (300), sous un seuil de 800.
        # en : marge ~1997, au-dessus des deux seuils — sert de témoin "ne bouge pas".
        intros = {"Large": {"fr": "x" * 403, "en": "y" * 2000}}
        replacement = "z" * 500
        with patch("scripts.deepen_intros.fetch_article_strict", return_value=replacement) as fetch_mock, \
             patch("scripts.deepen_intros.time.sleep"):
            deepened_default, _ = deepen_pending([fig], dict(intros))
            fetch_mock.assert_not_called()
            deepened_wide, _ = deepen_pending([fig], intros, threshold=800)
        self.assertEqual(deepened_default, [])
        fetch_mock.assert_called_once()
        self.assertEqual(fetch_mock.call_args.args[0], "fr")
        self.assertTrue(any(name == "Large" and lang == "fr" for name, lang, *_ in deepened_wide))


if __name__ == "__main__":
    unittest.main()
