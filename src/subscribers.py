import os
import json

from src.logger import LOGGER


class SubscriberStore:
    """Persists daily-delivery subscribers (chat_id + locale) to a JSON file.

    Kept in a dedicated module (separate from the figures data) so it never
    collides with the content pipeline. The full set is held in memory and the
    file is rewritten atomically on every change — fine for a moderate-volume
    public bot; swap for a real DB if volume grows.
    """

    def __init__(self, path: str):
        self.path = path
        self._subs = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            subs = data.get("subscribers", {}) if isinstance(data, dict) else {}
            return subs if isinstance(subs, dict) else {}
        except (json.JSONDecodeError, OSError) as e:
            LOGGER.error(f"Failed to load subscribers from {self.path}: {e}; starting empty")
            return {}

    def _save(self) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"subscribers": self._subs}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # atomic on POSIX

    def subscribe(self, chat_id, locale: str) -> bool:
        """Add or update a subscriber. Returns True if newly subscribed,
        False if they were already subscribed (locale is refreshed either way)."""
        key = str(chat_id)
        newly = key not in self._subs
        self._subs[key] = {"locale": locale}
        self._save()
        return newly

    def unsubscribe(self, chat_id) -> bool:
        """Remove a subscriber. Returns True if they were subscribed."""
        key = str(chat_id)
        if key in self._subs:
            del self._subs[key]
            self._save()
            return True
        return False

    def is_subscribed(self, chat_id) -> bool:
        return str(chat_id) in self._subs

    def all(self) -> list:
        """List of (chat_id: int, locale: str) — a fresh copy safe to iterate
        while unsubscribing."""
        return [(int(k), v.get("locale", "en")) for k, v in self._subs.items()]

    def count(self) -> int:
        return len(self._subs)
