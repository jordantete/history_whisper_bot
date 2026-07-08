import json, random
from typing import List
from src.historical_figure import HistoricalFigure
from src.logger import LOGGER

FIGURES_PATH = "src/figures.json"


class Database:
    def __init__(self, figures_path: str = FIGURES_PATH):
        LOGGER.info("init DB")
        self.historical_figures = self._load_figures(figures_path)
        LOGGER.info(f"Loaded {len(self.historical_figures)} figures")

    @staticmethod
    def _load_figures(figures_path: str) -> List[HistoricalFigure]:
        with open(figures_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return [
            HistoricalFigure(
                name=item["name"],
                description=item.get("description", ""),
                wikidata_id=item.get("wikidata_id"),
                image_url=item.get("image_url"),
                bio_en=item.get("bio_en"),
                bio_fr=item.get("bio_fr"),
                facts_en=item.get("facts_en", []),
                facts_fr=item.get("facts_fr", []),
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
