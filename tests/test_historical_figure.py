from src.historical_figure import HistoricalFigure


def test_minimal_figure_has_empty_enriched_defaults():
    f = HistoricalFigure(name="Voltaire", description="Writer.")
    assert f.wikidata_id is None
    assert f.image_url is None
    assert f.bio_en is None and f.bio_fr is None
    assert f.facts_en == [] and f.facts_fr == []


def test_full_figure_holds_all_fields():
    f = HistoricalFigure(
        name="Voltaire", description="Writer.", wikidata_id="Q9068",
        image_url="http://img", bio_en="EN bio", bio_fr="FR bio",
        facts_en=["a"], facts_fr=["b"],
    )
    assert f.image_url == "http://img"
    assert f.facts_fr == ["b"]
