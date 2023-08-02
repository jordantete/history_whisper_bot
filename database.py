import os, psycopg2, random
from historical_figure import HistoricalFigure
from typing import List

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.environ['DB_HOST'],
            database=os.environ['DB_NAME'],
            user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD']
        )

    def get_all_figures(self) -> List[HistoricalFigure]:
        figures = []
        with self.conn.cursor() as cur:
            cur.execute("SELECT name, description FROM historical_figures")
            rows = cur.fetchall()
            for row in rows:
                figure = HistoricalFigure(row[0], row[1])
                figures.append(figure)
        return figures
    
    def get_random_figures(self):
        figures = self.get_all_figures()
        index = random.randint(0, len(figures)-1)
        return figures[index]
    
    historical_figures = [
        HistoricalFigure("Albert Einstein", "Physicist who developed the theory of relativity."),
        HistoricalFigure("Leonardo da Vinci", "Italian polymath known for his paintings and inventions."),
        HistoricalFigure("Marie Curie", "Physicist and chemist who conducted pioneering research on radioactivity."),
    ]

