import random
from typing import List
from src.historical_figure import HistoricalFigure
from src.logger import LOGGER

class Database:
    def __init__(self):
        LOGGER.info("init DB")
        #self.conn = psycopg2.connect(host=os.environ['DB_HOST'], database=os.environ['DB_NAME'], user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'])

    def get_all_figures(self) -> List[HistoricalFigure]:
        return self.historical_figures
    
    def get_random_figure(self):
        figures = self.get_all_figures()
        index = random.randint(0, len(figures)-1)
        return figures[index]

    def get_figure_of_the_day(self, day):
        figures = self.get_all_figures()
        index = day.timetuple().tm_yday % len(figures)
        return figures[index]
    
    historical_figures = [
        HistoricalFigure("Albert Einstein", "Physicist who developed the theory of relativity."),
        HistoricalFigure("Leonardo da Vinci", "Italian polymath known for his paintings and inventions."),
        HistoricalFigure("Marie Curie", "Physicist and chemist who conducted pioneering research on radioactivity."),
    ]

