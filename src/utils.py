import os, json, re, unicodedata
from src.logger import LOGGER


class Utils:
    @staticmethod
    def get_environment_variable(env_var: str):
        try:
            return os.environ[env_var]
        except KeyError:
            LOGGER.error(f"Environment variable: {env_var} not found")
            return None

    @staticmethod
    def load_localizable_data(file_path="src/localizable.json"):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def localize(key, language, localizable_data):
        if language in localizable_data and key in localizable_data[language]:
            return localizable_data[language][key]
        LOGGER.error(f"Missing translation for '{key}' in '{language}'")
        return ""

    @staticmethod
    def resolve_locale(language_code, supported=("en", "fr"), default="en"):
        if not language_code:
            return default
        primary = language_code.split("-")[0].lower()
        return primary if primary in supported else default

    @staticmethod
    def normalize_name(name) -> str:
        """Forme comparable d'un nom de figure : casse neutralisée, accents
        dépouillés, espaces collapsés. Le roster mêle des saisies manuelles et
        des titres Wikipédia, dont l'accentuation diverge."""
        if not name:
            return ""
        decomposed = unicodedata.normalize("NFKD", name)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return " ".join(stripped.casefold().split())

    @staticmethod
    def figure_slug(name) -> str:
        """Identifiant URL-safe d'une figure, dérivé de son nom. C'est le payload
        d'un deep link Telegram : 64 caractères max, charset [A-Za-z0-9_-].
        Le roster n'a pas d'id stable — wikidata_id ne couvre que 7 des 339
        figures — et les noms sont uniques, donc le nom fait foi."""
        return re.sub(r"[^a-z0-9]+", "-", Utils.normalize_name(name)).strip("-")

    @staticmethod
    def names_match(a, b) -> bool:
        """Vrai quand l'un des deux noms normalisés contient l'autre.
        Volontairement lâche : le roster stocke des formes courtes ('De Lesseps')
        qu'un nom complet tapé à la main doit reconnaître. Produit de vrais faux
        positifs ('Philippe Auguste' vs 'Auguste') — les appelants décident
        quoi en faire."""
        na, nb = Utils.normalize_name(a), Utils.normalize_name(b)
        if not na or not nb:
            return False
        return na in nb or nb in na
