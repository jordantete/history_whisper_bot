import os
import json

from src.logger import LOGGER
from src.utils import Utils


class SuggestionStore:
    """File des figures suggérées via /suggest, persistée en JSON.

    Module dédié, comme SubscriberStore : c'est de l'état runtime écrit sur le
    VPS, qui ne doit jamais se mêler au pipeline de contenu. La file n'est
    qu'une source de noms — elle ne fait autorité sur rien, et sa perte est sans
    gravité.
    """

    def __init__(self, path: str):
        self.path = path
        self._names = self._load()

    def _load(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            names = data.get("suggestions", []) if isinstance(data, dict) else []
            return names if isinstance(names, list) else []
        except (json.JSONDecodeError, OSError) as e:
            LOGGER.error(f"Failed to load suggestions from {self.path}: {e}; starting empty")
            return []

    def _save(self) -> None:
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"suggestions": self._names}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)  # atomique sur POSIX

    def add(self, name: str) -> bool:
        """Empile un nom. False s'il y est déjà, à la casse et aux accents près."""
        normalized = Utils.normalize_name(name)
        if any(Utils.normalize_name(n) == normalized for n in self._names):
            return False
        self._names.append(name)
        self._save()
        return True

    def all(self) -> list:
        return list(self._names)

    def count(self) -> int:
        return len(self._names)
