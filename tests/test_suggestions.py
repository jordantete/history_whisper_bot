import json
import os
import tempfile
import unittest

from src.suggestions import SuggestionStore


class TestSuggestionStore(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)  # démarrer sans fichier
        self.addCleanup(lambda: os.path.exists(self.path) and os.unlink(self.path))

    def test_load_missing_file_is_empty(self):
        store = SuggestionStore(self.path)
        self.assertEqual(store.count(), 0)
        self.assertEqual(store.all(), [])

    def test_add_persists_and_reloads(self):
        store = SuggestionStore(self.path)
        self.assertTrue(store.add("Vauban"))
        reloaded = SuggestionStore(self.path)
        self.assertEqual(reloaded.all(), ["Vauban"])

    def test_add_duplicate_returns_false(self):
        store = SuggestionStore(self.path)
        store.add("Vauban")
        self.assertFalse(store.add("Vauban"))
        self.assertEqual(store.count(), 1)

    def test_duplicate_detection_ignores_case_and_accents(self):
        store = SuggestionStore(self.path)
        store.add("Périclès")
        self.assertFalse(store.add("pericles"))
        self.assertFalse(store.add("PÉRICLÈS"))
        self.assertEqual(store.count(), 1)

    def test_distinct_names_both_kept(self):
        store = SuggestionStore(self.path)
        store.add("Vauban")
        store.add("Lyautey")
        self.assertEqual(store.count(), 2)
        self.assertEqual(store.all(), ["Vauban", "Lyautey"])

    def test_load_corrupt_file_is_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ pas du json")
        store = SuggestionStore(self.path)  # ne doit pas lever
        self.assertEqual(store.count(), 0)

    def test_persisted_format_is_readable_json(self):
        store = SuggestionStore(self.path)
        store.add("Vauban")
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, {"suggestions": ["Vauban"]})

    def test_write_is_atomic_no_tmp_left_behind(self):
        store = SuggestionStore(self.path)
        store.add("Vauban")
        self.assertFalse(os.path.exists(f"{self.path}.tmp"))

    def test_reject_empty_string(self):
        store = SuggestionStore(self.path)
        self.assertFalse(store.add(""))
        self.assertEqual(store.count(), 0)
        self.assertEqual(store.all(), [])

    def test_reject_whitespace_only(self):
        store = SuggestionStore(self.path)
        self.assertFalse(store.add("   "))
        self.assertEqual(store.count(), 0)
        self.assertEqual(store.all(), [])

    def test_reject_none(self):
        store = SuggestionStore(self.path)
        self.assertFalse(store.add(None))
        self.assertEqual(store.count(), 0)
        self.assertEqual(store.all(), [])

    def test_no_file_written_for_blank_input(self):
        store = SuggestionStore(self.path)
        store.add("")
        store.add("   ")
        store.add(None)
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
