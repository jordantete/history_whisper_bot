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


def test_normalize_name_strips_accents_and_case():
    assert Utils.normalize_name("Périclès") == "pericles"
    assert Utils.normalize_name("Ferdinand de Lesseps") == "ferdinand de lesseps"
    assert Utils.normalize_name("DÜRER") == "durer"


def test_normalize_name_collapses_whitespace():
    assert Utils.normalize_name("  Jeanne   d'Arc ") == "jeanne d'arc"
    assert Utils.normalize_name("") == ""
    assert Utils.normalize_name(None) == ""


def test_names_match_is_bidirectional_inclusion():
    # Le roster stocke des formes courtes ; un nom complet tapé à la main
    # doit les reconnaître, dans les deux sens.
    assert Utils.names_match("Ferdinand de Lesseps", "De Lesseps")
    assert Utils.names_match("De Lesseps", "Ferdinand de Lesseps")
    assert Utils.names_match("Périclès", "pericles")


def test_names_match_rejects_unrelated_names():
    assert not Utils.names_match("Vauban", "Voltaire")
    assert not Utils.names_match("", "Vauban")
    assert not Utils.names_match("Vauban", "")


def test_names_match_admits_known_false_positives():
    # Documenté, pas un bug : l'inclusion rapproche ces paires à tort. Les
    # appelants traitent un rapprochement comme un signal, pas comme un verdict.
    assert Utils.names_match("Philippe Auguste", "Auguste")
    assert Utils.names_match("Mendel", "Mendeleïev")
