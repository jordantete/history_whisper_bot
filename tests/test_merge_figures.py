import unittest

from scripts.merge_figures import is_complete, missing_parts, promote


def entry(name="X", description="d", facts_fr=None, facts_en=None):
    return {
        "name": name,
        "description": description,
        "bio_fr": "bio fr",
        "bio_en": "bio en",
        "image_url": "http://img/x.jpg",
        "facts_fr": facts_fr if facts_fr is not None else ["a", "b", "c"],
        "facts_en": facts_en if facts_en is not None else ["a", "b", "c"],
    }


class TestCompleteness(unittest.TestCase):
    def test_fully_authored_figure_is_complete(self):
        self.assertTrue(is_complete(entry()))
        self.assertEqual(missing_parts(entry()), [])

    def test_empty_description_is_incomplete(self):
        self.assertIn("description", missing_parts(entry(description="")))
        self.assertIn("description", missing_parts(entry(description="   ")))

    def test_wrong_fact_count_is_incomplete(self):
        # L'invariant de test_database.py est « exactement 3 », pas « au moins 3 ».
        self.assertTrue(any("facts_fr" in p for p in missing_parts(entry(facts_fr=["a", "b"]))))
        self.assertTrue(any("facts_en" in p for p in missing_parts(entry(facts_en=["a", "b", "c", "d"]))))

    def test_missing_facts_key_is_incomplete(self):
        broken = entry()
        del broken["facts_en"]
        self.assertFalse(is_complete(broken))


class TestPromote(unittest.TestCase):
    def test_complete_figures_move_to_roster(self):
        figures = [{"name": "Colbert"}]
        pending = [entry(name="Vauban"), entry(name="Brouillon", description="")]
        new_figures, still_pending, promoted = promote(figures, pending)
        self.assertEqual(promoted, ["Vauban"])
        self.assertEqual([f["name"] for f in new_figures], ["Colbert", "Vauban"])
        self.assertEqual([p["name"] for p in still_pending], ["Brouillon"])

    def test_incomplete_figures_stay_in_staging(self):
        figures = []
        pending = [entry(name="Brouillon", facts_fr=[])]
        new_figures, still_pending, promoted = promote(figures, pending)
        self.assertEqual(promoted, [])
        self.assertEqual(new_figures, [])
        self.assertEqual(len(still_pending), 1)

    def test_empty_staging_is_a_no_op(self):
        figures = [{"name": "Colbert"}]
        new_figures, still_pending, promoted = promote(figures, [])
        self.assertEqual(new_figures, figures)
        self.assertEqual(still_pending, [])
        self.assertEqual(promoted, [])


if __name__ == "__main__":
    unittest.main()
