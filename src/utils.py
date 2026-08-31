import os, json, re, unicodedata, hashlib
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

    # Motif d'un payload de deep link désignant une citation. Le motif exact
    # plutôt qu'un simple préfixe 'q-' : le roster ne contient aujourd'hui aucun
    # slug qui matche, et cette formulation le garde vrai quoi qu'on y ajoute.
    QUOTE_PAYLOAD_PATTERN = re.compile(r"^q-[a-f0-9]{10}$")

    @staticmethod
    def quote_id(text) -> str:
        """Identifiant stable d'une citation, dérivé de son texte d'origine.
        Contrairement aux figures, une citation n'a pas de nom dont dériver un
        slug. Un hash reste stable quand le fichier est réordonné, sert de clé
        de déduplication au pipeline, et tient dans les 64 caractères et le
        charset [A-Za-z0-9_-] d'un payload Telegram."""
        normalized = " ".join((text or "").split())
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]

    @staticmethod
    def is_quote_payload(payload) -> bool:
        """Vrai quand un payload de deep link désigne une citation. Tout le
        reste part vers la résolution de slug de figure, comportement inchangé."""
        return bool(Utils.QUOTE_PAYLOAD_PATTERN.match(payload or ""))
