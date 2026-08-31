import unittest
from scripts.add_quotes import (
    strip_markup, iter_templates, template_field, format_ref, parse_page,
    MAX_QUOTE_LENGTH,
)

SOURCED = """== Citations ==
=== Sur les sciences ===
{{Citation|citation=Les vraies conquêtes, les seules qui ne donnent aucun regret, sont celles que l'on fait sur l'ignorance.|précisions=Bonaparte au Directoire}}
{{Réf Livre|titre=La campagne d'Égypte|auteur=Jacques-Olivier Boudon|éditeur=Belin|année=2018|page=111|ISBN=978-2410015270}}
"""

UNSOURCED = """== Citations ==
{{Citation|citation=Une phrase sans la moindre référence derrière elle.}}
"""

ATTRIBUTED = """== Citations attribuées ==
{{Citation|citation=Tout est permis mais rien n'est possible.}}
{{Réf Livre|titre=Un recueil douteux|année=1990}}
"""

ABOUT = """== À propos de Napoléon Ier ==
{{Citation|citation=Il était un homme de son temps.}}
{{Réf Livre|titre=Une biographie|année=2001}}
"""


class TestStripMarkup(unittest.TestCase):
    def test_removes_wiki_links_keeping_the_visible_text(self):
        self.assertEqual(strip_markup("Les [[Français|Francais]] et l'[[Europe]]"),
                         "Les Francais et l'Europe")

    def test_removes_w_templates_keeping_the_visible_text(self):
        self.assertEqual(strip_markup("Selon {{w|Jean Racine|Racine}} et {{w|Corneille}}"),
                         "Selon Racine et Corneille")

    def test_removes_bold_and_italic_markers(self):
        self.assertEqual(strip_markup("Le ''mieux'' est l''''ennemi''' du bien"),
                         "Le mieux est l'ennemi du bien")

    def test_removes_ref_tags_and_their_content(self):
        self.assertEqual(strip_markup("Une phrase<ref>note de bas de page</ref> nette"),
                         "Une phrase nette")

    def test_collapses_whitespace_and_decodes_entities(self):
        self.assertEqual(strip_markup("  Deux\n  mots &amp; trois  "), "Deux mots & trois")


class TestTemplateParsing(unittest.TestCase):
    def test_iter_templates_yields_name_and_body(self):
        names = [name for name, _, _ in iter_templates(SOURCED)]
        self.assertEqual(names, ["Citation", "Réf Livre"])

    def test_iter_templates_survives_nested_templates(self):
        """Une regex non récursive couperait la citation au premier }} du
        {{w|…}} imbriqué, tronquant le texte sans le signaler."""
        wikitext = "{{Citation|citation=Selon {{w|Platon|Platon}}, tout coule.}}"
        name, body, _ = next(iter(iter_templates(wikitext)))
        self.assertEqual(name, "Citation")
        self.assertEqual(template_field(body, "citation"),
                         "Selon {{w|Platon|Platon}}, tout coule.")

    def test_template_field_ignores_pipes_inside_nested_markup(self):
        body = "Citation|citation=Les [[France|Français]] d'abord|précisions=Discours"
        self.assertEqual(template_field(body, "citation"), "Les [[France|Français]] d'abord")
        self.assertEqual(template_field(body, "précisions"), "Discours")

    def test_template_field_survives_an_unpaired_opening_bracket_in_prose(self):
        """« [0,1[ » est la notation française standard d'un intervalle semi-
        ouvert : un crochet seul, non apparié, ne doit pas désynchroniser le
        compteur de profondeur et masquer le '|' de premier niveau qui suit."""
        body = ("Citation|citation=La probabilite est dans [0,1[ selon Kolmogorov."
                "|precisions=Note editoriale")
        self.assertEqual(template_field(body, "citation"),
                         "La probabilite est dans [0,1[ selon Kolmogorov.")
        self.assertEqual(template_field(body, "precisions"), "Note editoriale")

    def test_template_field_survives_an_unpaired_closing_bracket_in_prose(self):
        """Même défaut avec un ']' orphelin — artefact de transcription."""
        body = ("Citation|citation=Une phrase mal transcrite] avec un reste."
                "|precisions=Note editoriale")
        self.assertEqual(template_field(body, "citation"),
                         "Une phrase mal transcrite] avec un reste.")
        self.assertEqual(template_field(body, "precisions"), "Note editoriale")

    def test_template_field_falls_back_to_the_positional_argument(self):
        self.assertEqual(template_field("Citation|Un texte positionnel", "citation"),
                         "Un texte positionnel")

    def test_template_field_returns_none_for_a_missing_field(self):
        self.assertIsNone(template_field("Citation|citation=Texte", "absent"))

    def test_format_ref_builds_a_readable_source_line(self):
        _, body, _ = list(iter_templates(SOURCED))[1]
        self.assertEqual(format_ref(body),
                         "La campagne d'Égypte, Belin, 2018, p. 111")

    def test_format_ref_is_empty_when_the_template_carries_nothing_useful(self):
        self.assertEqual(format_ref("Réf Livre|ISBN=978-2410015270"), "")


class TestParsePage(unittest.TestCase):
    def test_keeps_a_sourced_quote(self):
        kept, rejected = parse_page("Napoléon Bonaparte", "Napoléon Ier", SOURCED)
        self.assertEqual(len(kept), 1)
        entry = kept[0]
        self.assertEqual(entry["author"], "Napoléon Bonaparte")
        self.assertEqual(entry["lang"], "fr")
        self.assertEqual(entry["wikiquote_fr"], "Napoléon Ier")
        self.assertTrue(entry["text_fr"].startswith("Les vraies conquêtes"))
        self.assertEqual(entry["source_fr"], "La campagne d'Égypte, Belin, 2018, p. 111")
        self.assertRegex(entry["id"], r"^[a-f0-9]{10}$")
        self.assertEqual(rejected, {})

    def test_rejects_an_unsourced_quote(self):
        kept, rejected = parse_page("Anonyme", "Anonyme", UNSOURCED)
        self.assertEqual(kept, [])
        self.assertEqual(rejected["non sourcé"], 1)

    def test_rejects_an_attributed_section(self):
        """« Citations attribuées » est précisément la zone des mésattributions
        que la contrainte dure existe pour écarter."""
        kept, rejected = parse_page("Proudhon", "Proudhon", ATTRIBUTED)
        self.assertEqual(kept, [])
        self.assertEqual(rejected["section exclue"], 1)

    def test_rejects_an_about_section(self):
        """Ces citations parlent de la personne, elles ne sont pas d'elle."""
        kept, rejected = parse_page("Napoléon Ier", "Napoléon Ier", ABOUT)
        self.assertEqual(kept, [])
        self.assertEqual(rejected["section exclue"], 1)

    def test_rejects_an_oversized_quote(self):
        wikitext = ("== Citations ==\n{{Citation|citation=" + "x" * (MAX_QUOTE_LENGTH + 1)
                    + "}}\n{{Réf Livre|titre=T|année=2000}}\n")
        kept, rejected = parse_page("A", "A", wikitext)
        self.assertEqual(kept, [])
        self.assertEqual(rejected["trop long"], 1)

    def test_a_ref_belonging_to_the_next_quote_does_not_source_the_previous_one(self):
        wikitext = ("== Citations ==\n"
                    "{{Citation|citation=Première, orpheline.}}\n"
                    "{{Citation|citation=Seconde, sourcée.}}\n"
                    "{{Réf Livre|titre=Un livre|année=2000}}\n")
        kept, rejected = parse_page("A", "A", wikitext)
        self.assertEqual([entry["text_fr"] for entry in kept], ["Seconde, sourcée."])
        self.assertEqual(rejected["non sourcé"], 1)

    def test_caps_the_number_of_quotes_per_author(self):
        """Robespierre pèse 182 références et Nietzsche 110 : sans plafond, le
        corpus devient un florilège de deux auteurs."""
        blocks = "".join(
            f"{{{{Citation|citation=Citation numéro {i}.}}}}\n{{{{Réf Livre|titre=T{i}|année=2000}}}}\n"
            for i in range(10))
        kept, _ = parse_page("Robespierre", "Robespierre", "== Citations ==\n" + blocks,
                             max_per_author=3)
        self.assertEqual(len(kept), 3)

    def test_deduplicates_identical_quotes_by_id(self):
        block = "{{Citation|citation=La même phrase.}}\n{{Réf Livre|titre=T|année=2000}}\n"
        kept, rejected = parse_page("A", "A", "== Citations ==\n" + block + block)
        self.assertEqual(len(kept), 1)
        self.assertEqual(rejected["doublon"], 1)


if __name__ == "__main__":
    unittest.main()
