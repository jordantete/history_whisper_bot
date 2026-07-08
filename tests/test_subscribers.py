import os
import json
import tempfile
import unittest

from src.subscribers import SubscriberStore


class TestSubscriberStore(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.path)  # start with no file
        self.addCleanup(lambda: os.path.exists(self.path) and os.unlink(self.path))

    def test_load_missing_file_is_empty(self):
        store = SubscriberStore(self.path)
        self.assertEqual(store.count(), 0)
        self.assertEqual(store.all(), [])

    def test_subscribe_persists_and_reloads(self):
        store = SubscriberStore(self.path)
        self.assertTrue(store.subscribe(123, "fr"))  # newly subscribed
        self.assertTrue(store.is_subscribed(123))
        # A fresh store reading the same file sees the subscriber.
        reloaded = SubscriberStore(self.path)
        self.assertTrue(reloaded.is_subscribed(123))
        self.assertEqual(reloaded.all(), [(123, "fr")])

    def test_subscribe_existing_returns_false_and_updates_locale(self):
        store = SubscriberStore(self.path)
        store.subscribe(123, "en")
        self.assertFalse(store.subscribe(123, "fr"))  # already there
        self.assertEqual(store.all(), [(123, "fr")])  # locale updated

    def test_unsubscribe(self):
        store = SubscriberStore(self.path)
        store.subscribe(123, "en")
        self.assertTrue(store.unsubscribe(123))   # was subscribed
        self.assertFalse(store.is_subscribed(123))
        self.assertFalse(store.unsubscribe(123))  # already gone

    def test_all_and_count(self):
        store = SubscriberStore(self.path)
        store.subscribe(1, "en")
        store.subscribe(2, "fr")
        self.assertEqual(store.count(), 2)
        self.assertCountEqual(store.all(), [(1, "en"), (2, "fr")])

    def test_load_corrupt_file_is_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        store = SubscriberStore(self.path)  # must not raise
        self.assertEqual(store.count(), 0)

    def test_persisted_format_is_readable_json(self):
        store = SubscriberStore(self.path)
        store.subscribe(42, "fr")
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("subscribers", data)
        self.assertIn("42", data["subscribers"])


if __name__ == "__main__":
    unittest.main()
