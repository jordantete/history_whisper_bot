from src.utils import Utils


def test_resolve_locale_maps_language_codes():
    assert Utils.resolve_locale("fr") == "fr"
    assert Utils.resolve_locale("fr-FR") == "fr"
    assert Utils.resolve_locale("en") == "en"
    assert Utils.resolve_locale("en-US") == "en"


def test_resolve_locale_falls_back_to_default():
    assert Utils.resolve_locale(None) == "en"
    assert Utils.resolve_locale("") == "en"
    assert Utils.resolve_locale("de") == "en"
