from dataclasses import dataclass
from typing import Optional


@dataclass
class Quote:
    """Une citation sourcée. `lang` est la langue d'origine : c'est elle qui
    porte le texte au moment de la promotion, l'autre restant vide tant que la
    dette de traduction n'est pas traitée."""
    id: str
    author: str
    lang: str
    text_fr: Optional[str] = None
    text_en: Optional[str] = None
    source_fr: Optional[str] = None
    source_en: Optional[str] = None
    wikiquote_fr: Optional[str] = None
    wikiquote_en: Optional[str] = None
