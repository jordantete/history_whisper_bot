from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class HistoricalFigure:
    name: str
    description: str
    wikidata_id: Optional[str] = None
    image_url: Optional[str] = None
    bio_en: Optional[str] = None
    bio_fr: Optional[str] = None
    facts_en: List[str] = field(default_factory=list)
    facts_fr: List[str] = field(default_factory=list)
