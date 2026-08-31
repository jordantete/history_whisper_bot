import json, os, random, re
from typing import List
from src.historical_figure import HistoricalFigure
from src.quote import Quote
from src.utils import Utils
from src.logger import LOGGER

FIGURES_PATH = "src/figures.json"
QUOTES_PATH = "src/quotes.json"


class Database:
    def __init__(self, figures_path: str = FIGURES_PATH, quotes_path: str = QUOTES_PATH):
        LOGGER.info("init DB")
        self.historical_figures = self._load_figures(figures_path)
        self._by_slug = self._index_by_slug(self.historical_figures)
        LOGGER.info(f"Loaded {len(self.historical_figures)} figures")
        self.quotes = self._load_quotes(quotes_path)
        self._by_quote_id = self._index_by_quote_id(self.quotes)
        LOGGER.info(f"Loaded {len(self.quotes)} quotes")

    # Ordinary whitespace only: U+00A0 is left alone, French typography uses it
    # before ':' / ';' and inside "Ier siècle" and must not become a break point.
    _WHITESPACE = r"[ \t\r\n\f\v]"

    @classmethod
    def _clean(cls, text):
        """Collapse whitespace in scraped prose. Bios and facts are rendered
        verbatim inside the Telegram caption, so a stray newline (Wikipedia
        paragraph break, leading blank lines) shows up as a broken layout."""
        if not text:
            return text
        return re.sub(cls._WHITESPACE + "+", " ", text).strip(" \t\r\n\f\v")

    @classmethod
    def _load_figures(cls, figures_path: str) -> List[HistoricalFigure]:
        with open(figures_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return [
            HistoricalFigure(
                name=item["name"],
                description=cls._clean(item.get("description", "")),
                wikidata_id=item.get("wikidata_id"),
                image_url=item.get("image_url"),
                bio_en=cls._clean(item.get("bio_en")),
                bio_fr=cls._clean(item.get("bio_fr")),
                facts_en=[cls._clean(f) for f in item.get("facts_en", [])],
                facts_fr=[cls._clean(f) for f in item.get("facts_fr", [])],
            )
            for item in data
        ]

    def get_all_figures(self) -> List[HistoricalFigure]:
        return self.historical_figures

    def get_random_figure(self):
        figures = self.get_all_figures()
        index = random.randint(0, len(figures) - 1)
        return figures[index]

    def get_figure_of_the_day(self, day):
        figures = self.get_all_figures()
        index = day.timetuple().tm_yday % len(figures)
        return figures[index]

    @staticmethod
    def _index_by_slug(figures):
        """Index slug -> figure, construit une fois au chargement. Le slug sert
        de payload de deep link ; une collision rendrait un lien partagé
        ambigu, donc le premier arrivé gagne et la seconde est tracée."""
        index = {}
        for figure in figures:
            slug = Utils.figure_slug(figure.name)
            if not slug:
                continue
            if slug in index:
                LOGGER.warning(
                    f"Slug collision on '{slug}': keeping '{index[slug].name}', "
                    f"ignoring '{figure.name}'")
                continue
            index[slug] = figure
        return index

    def get_figure_by_slug(self, slug):
        """Résout le payload d'un deep link. Le slug est re-normalisé, donc la
        casse et les accents reçus sont indifférents."""
        return self._by_slug.get(Utils.figure_slug(slug))

    @classmethod
    def _load_quotes(cls, quotes_path: str) -> List[Quote]:
        """Le corpus peut ne pas exister : entre la livraison du code et le
        premier lot promu, le bot sert la figure seule. Ce n'est pas une erreur.

        `_clean` s'applique aux textes et aux sources pour la même raison que
        sur les bios — le contenu atterrit verbatim dans le message."""
        if not os.path.exists(quotes_path):
            LOGGER.warning(f"No quotes file at {quotes_path} — quotes disabled")
            return []
        with open(quotes_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return [
            Quote(
                id=item["id"],
                author=cls._clean(item["author"]),
                lang=item.get("lang", "fr"),
                text_fr=cls._clean(item.get("text_fr")),
                text_en=cls._clean(item.get("text_en")),
                source_fr=cls._clean(item.get("source_fr")),
                source_en=cls._clean(item.get("source_en")),
                wikiquote_fr=item.get("wikiquote_fr"),
                wikiquote_en=item.get("wikiquote_en"),
            )
            for item in data
        ]

    @staticmethod
    def _index_by_quote_id(quotes):
        """Index id -> citation. Même précaution que pour les slugs de figures :
        merge_quotes n'a pas de contrôle d'appartenance, et un id dupliqué
        rendrait un lien partagé ambigu. Le premier arrivé gagne."""
        index = {}
        for quote in quotes:
            if quote.id in index:
                LOGGER.warning(
                    f"Quote id collision on '{quote.id}': keeping "
                    f"'{index[quote.id].author}', ignoring '{quote.author}'")
                continue
            index[quote.id] = quote
        return index

    def get_all_quotes(self) -> List[Quote]:
        return self.quotes

    def get_random_quote(self):
        if not self.quotes:
            return None
        return self.quotes[random.randint(0, len(self.quotes) - 1)]

    def get_quote_of_the_day(self, day):
        if not self.quotes:
            return None
        return self.quotes[day.timetuple().tm_yday % len(self.quotes)]

    def get_quote_by_id(self, quote_id):
        return self._by_quote_id.get(quote_id)
