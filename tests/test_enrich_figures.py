import urllib.error
from unittest.mock import patch

import pytest

from scripts.enrich_figures import (
    FetchError, fetch_summary, fetch_summary_strict, resolve_titles,
)


def test_resolve_titles_default_uses_name():
    r = resolve_titles("Voltaire", {})
    assert r["fr"] == "Voltaire" and r["en"] == "Voltaire" and r["wikidata_id"] is None


def test_resolve_titles_uses_overrides():
    overrides = {"Aristide": {"fr": "Aristide (homme d'État)", "en": "Aristides", "wikidata_id": "Q184960"}}
    r = resolve_titles("Aristide", overrides)
    assert r["en"] == "Aristides"
    assert r["wikidata_id"] == "Q184960"


def test_strict_raises_on_throttling():
    """429 = 'je n'ai pas pu répondre', jamais 'la figure n'existe pas'."""
    err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    with patch("scripts.enrich_figures._get_json", side_effect=err):
        with pytest.raises(FetchError):
            fetch_summary_strict("fr", "William Shakespeare")


def test_strict_raises_on_network_error():
    with patch("scripts.enrich_figures._get_json", side_effect=urllib.error.URLError("timed out")):
        with pytest.raises(FetchError):
            fetch_summary_strict("fr", "William Shakespeare")


def test_strict_returns_empty_on_404():
    """404 = réponse valide du serveur : l'article n'existe pas."""
    err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("scripts.enrich_figures._get_json", side_effect=err):
        assert fetch_summary_strict("fr", "Nimportequoi") == ("", None)


def test_strict_returns_extract_and_thumbnail():
    payload = {"extract": "Une bio.", "thumbnail": {"source": "http://img/x.jpg"}}
    with patch("scripts.enrich_figures._get_json", return_value=payload):
        assert fetch_summary_strict("fr", "X") == ("Une bio.", "http://img/x.jpg")


def test_lenient_wrapper_still_swallows():
    """enrich_figures.main() dépend de ce comportement pour parcourir tout le
    roster sans s'interrompre — il ne doit pas changer."""
    err = urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)
    with patch("scripts.enrich_figures._get_json", side_effect=err):
        assert fetch_summary("fr", "William Shakespeare") == ("", None)
