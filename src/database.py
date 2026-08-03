import json, random, re
from typing import List
from src.historical_figure import HistoricalFigure
from src.utils import Utils
from src.logger import LOGGER

FIGURES_PATH = "src/figures.json"


class Database:
    def __init__(self, figures_path: str = FIGURES_PATH):
        LOGGER.info("init DB")
        self.historical_figures = self._load_figures(figures_path)
        self._by_slug = self._index_by_slug(self.historical_figures)
        LOGGER.info(f"Loaded {len(self.historical_figures)} figures")

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
