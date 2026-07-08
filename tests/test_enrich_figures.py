from scripts.enrich_figures import normalize_image_width, resolve_titles


def test_normalize_image_width_rewrites_thumb():
    url = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Foo.jpg/330px-Foo.jpg"
    out = normalize_image_width(url, 800)
    assert "/800px-Foo.jpg" in out


def test_normalize_image_width_leaves_non_thumb_untouched():
    url = "https://upload.wikimedia.org/wikipedia/commons/f/f2/Foo.jpg"
    assert normalize_image_width(url, 800) == url


def test_resolve_titles_default_uses_name():
    r = resolve_titles("Voltaire", {})
    assert r["fr"] == "Voltaire" and r["en"] == "Voltaire" and r["wikidata_id"] is None


def test_resolve_titles_uses_overrides():
    overrides = {"Aristide": {"fr": "Aristide (homme d'État)", "en": "Aristides", "wikidata_id": "Q184960"}}
    r = resolve_titles("Aristide", overrides)
    assert r["en"] == "Aristides"
    assert r["wikidata_id"] == "Q184960"
