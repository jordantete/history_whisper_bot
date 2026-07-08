from scripts.enrich_figures import resolve_titles


def test_resolve_titles_default_uses_name():
    r = resolve_titles("Voltaire", {})
    assert r["fr"] == "Voltaire" and r["en"] == "Voltaire" and r["wikidata_id"] is None


def test_resolve_titles_uses_overrides():
    overrides = {"Aristide": {"fr": "Aristide (homme d'État)", "en": "Aristides", "wikidata_id": "Q184960"}}
    r = resolve_titles("Aristide", overrides)
    assert r["en"] == "Aristides"
    assert r["wikidata_id"] == "Q184960"
