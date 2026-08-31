import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.merge_quotes import missing_parts, is_complete, promote, main


def entry(**overrides):
    fields = {
        "id": "abc1234567", "author": "Voltaire", "lang": "fr",
        "text_fr": "Le mieux est l'ennemi du bien.",
        "source_fr": "Dictionnaire philosophique, 1770",
        "wikiquote_fr": "Voltaire",
    }
    fields.update(overrides)
    return fields


class TestCompleteness(unittest.TestCase):
    def test_a_single_language_entry_is_complete(self):
        """La contrainte bilingue n'est délibérément pas imposée : le corpus est
        francophone tant que la dette de traduction EN n'est pas traitée."""
        self.assertEqual(missing_parts(entry()), [])
        self.assertTrue(is_complete(entry()))

    def test_an_english_entry_is_complete_on_its_english_fields(self):
        self.assertTrue(is_complete(entry(
            lang="en", text_fr=None, source_fr=None, wikiquote_fr=None,
            text_en="Truth is the daughter of time.", source_en="Novum Organum, 1620")))

    def test_missing_text_is_reported(self):
        self.assertIn("text_fr", missing_parts(entry(text_fr="")))

    def test_missing_source_is_reported(self):
        self.assertIn("source_fr", missing_parts(entry(source_fr=None)))

    def test_missing_author_and_id_are_reported(self):
        parts = missing_parts(entry(id="", author="   "))
        self.assertIn("id", parts)
        self.assertIn("author", parts)

    def test_an_unknown_lang_is_reported(self):
        self.assertIn("lang", missing_parts(entry(lang="de")))


class TestPromote(unittest.TestCase):
    def test_promotes_complete_entries_and_keeps_the_rest_in_staging(self):
        complete, incomplete = entry(), entry(id="def1234567", source_fr="")
        corpus, remaining, promoted, duplicates = promote([], [complete, incomplete])
        self.assertEqual(promoted, ["abc1234567"])
        self.assertEqual(len(corpus), 1)
        self.assertEqual(remaining, [incomplete])
        self.assertEqual(duplicates, [])

    def test_never_promotes_an_id_already_in_the_corpus(self):
        """promote() n'a pas d'autre garde-fou, et un id dupliqué rendrait un
        deep link partagé ambigu."""
        existing = entry()
        corpus, remaining, promoted, duplicates = promote([existing], [entry()])
        self.assertEqual(promoted, [])
        self.assertEqual(len(corpus), 1)
        self.assertEqual(remaining, [])

    def test_deduplicates_within_a_single_staging_batch(self):
        corpus, _, promoted, _ = promote([], [entry(), entry()])
        self.assertEqual(len(promoted), 1)
        self.assertEqual(len(corpus), 1)

    def test_reports_duplicates_separately_from_incomplete_entries(self):
        """Un doublon (complet, déjà au corpus) n'est ni une promotion ni une
        entrée à compléter : il doit être compté à part, sans quoi le rapport
        le fait disparaître silencieusement."""
        existing = entry()
        corpus, remaining, promoted, duplicates = promote([existing], [entry()])
        self.assertEqual(duplicates, ["abc1234567"])
        self.assertEqual(remaining, [])


class TestMainPersistsDuplicates(unittest.TestCase):
    """finding 3 : main() sortait avant d'écrire `remaining` dès que rien
    n'était promouvable, alors que `promote()` avait déjà retiré les doublons
    de `remaining` — ces lignes restaient donc en staging et étaient
    re-rejetées à chaque exécution suivante."""

    def _run_main(self, quotes, pending):
        quotes_fd, quotes_path = tempfile.mkstemp(suffix=".json")
        pending_fd, pending_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(quotes_fd, "w", encoding="utf-8") as f:
            json.dump(quotes, f)
        with os.fdopen(pending_fd, "w", encoding="utf-8") as f:
            json.dump({"quotes": pending}, f)
        self.addCleanup(os.unlink, quotes_path)
        self.addCleanup(os.unlink, pending_path)

        out = io.StringIO()
        with patch("scripts.merge_quotes.QUOTES_PATH", quotes_path), \
             patch("scripts.merge_quotes.PENDING_PATH", pending_path), \
             patch.object(sys, "argv", ["merge_quotes"]), \
             contextlib.redirect_stdout(out):
            main()

        with open(pending_path, encoding="utf-8") as f:
            remaining_on_disk = json.load(f)["quotes"]
        with open(quotes_path, encoding="utf-8") as f:
            quotes_on_disk = json.load(f)
        return out.getvalue(), remaining_on_disk, quotes_on_disk

    def test_a_pure_duplicate_batch_is_persisted_as_empty_and_reported(self):
        existing = entry()
        output, remaining_on_disk, quotes_on_disk = self._run_main([existing], [entry()])
        self.assertEqual(remaining_on_disk, [])
        self.assertEqual(quotes_on_disk, [existing])
        self.assertIn("doublon", output.lower())
        self.assertNotIn("aucune citation complète, rien écrit.", output.lower())


if __name__ == "__main__":
    unittest.main()
