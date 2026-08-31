import unittest
from src.quote import Quote


class TestQuote(unittest.TestCase):
    def test_minimal_quote_defaults_every_optional_field_to_none(self):
        quote = Quote(id="abc1234567", author="Napoléon Ier", lang="fr")
        self.assertEqual(quote.id, "abc1234567")
        self.assertEqual(quote.author, "Napoléon Ier")
        self.assertEqual(quote.lang, "fr")
        self.assertIsNone(quote.text_fr)
        self.assertIsNone(quote.text_en)
        self.assertIsNone(quote.source_fr)
        self.assertIsNone(quote.source_en)
        self.assertIsNone(quote.wikiquote_fr)
        self.assertIsNone(quote.wikiquote_en)

    def test_quote_carries_text_and_source_per_language(self):
        quote = Quote(id="abc1234567", author="Charlie Munger", lang="en",
                      text_en="It's good to learn from your mistakes.",
                      source_en="Poor Charlie's Almanack, 2005, p. 62",
                      wikiquote_en="Charlie Munger")
        self.assertEqual(quote.text_en, "It's good to learn from your mistakes.")
        self.assertEqual(quote.source_en, "Poor Charlie's Almanack, 2005, p. 62")
        self.assertEqual(quote.wikiquote_en, "Charlie Munger")


if __name__ == "__main__":
    unittest.main()
