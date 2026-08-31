import unittest
from scripts.merge_quotes import missing_parts, is_complete, promote


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
        corpus, remaining, promoted = promote([], [complete, incomplete])
        self.assertEqual(promoted, ["abc1234567"])
        self.assertEqual(len(corpus), 1)
        self.assertEqual(remaining, [incomplete])

    def test_never_promotes_an_id_already_in_the_corpus(self):
        """promote() n'a pas d'autre garde-fou, et un id dupliqué rendrait un
        deep link partagé ambigu."""
        existing = entry()
        corpus, remaining, promoted = promote([existing], [entry()])
        self.assertEqual(promoted, [])
        self.assertEqual(len(corpus), 1)
        self.assertEqual(remaining, [])

    def test_deduplicates_within_a_single_staging_batch(self):
        corpus, _, promoted = promote([], [entry(), entry()])
        self.assertEqual(len(promoted), 1)
        self.assertEqual(len(corpus), 1)


if __name__ == "__main__":
    unittest.main()
