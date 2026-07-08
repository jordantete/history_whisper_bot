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


NEW_KEYS = [
    "start-message", "help-message",
    "subscribe-done", "subscribe-already", "unsubscribe-done", "unsubscribe-none",
    "feedback-ask", "feedback-placeholder", "feedback-cancel", "feedback-thanks",
    "highlights-header", "no-figures",
]


def test_all_keys_present_in_both_languages():
    data = Utils.load_localizable_data()
    for lang in ("en", "fr"):
        for key in NEW_KEYS:
            assert Utils.localize(key, lang, data), f"missing {key} in {lang}"


def test_another_message_key_removed():
    data = Utils.load_localizable_data()
    assert "another-message" not in data["en"]
    assert "another-message" not in data["fr"]
