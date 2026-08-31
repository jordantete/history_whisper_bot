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

    def test_reduces_an_unrecognized_template_to_its_last_argument(self):
        """{{Personnage|…}} est l'attribution de réplique des citations de
        théâtre/dialogue sur Wikiquote ; son nom n'est pas prévisible à
        l'avance, d'où le repli générique plutôt qu'une règle nommée."""
        self.assertEqual(strip_markup("{{Personnage|Socrate}} : Une vie sans examen…"),
                         "Socrate : Une vie sans examen…")

    def test_reduces_an_unrecognized_template_case_insensitively(self):
        self.assertEqual(strip_markup("{{personnage|Mascarille}} : On ne meurt qu'une fois"),
                         "Mascarille : On ne meurt qu'une fois")

    def test_removes_a_bare_template_with_no_argument(self):
        self.assertEqual(strip_markup("Au {{Ier}} siècle"), "Au siècle")

    def test_reduces_a_multi_argument_template_to_its_last_argument(self):
        self.assertEqual(strip_markup("{{tpl|a|b|c}} fin"), "c fin")

    def test_strips_a_labelled_external_link_mid_string(self):
        self.assertEqual(
            strip_markup("Novum Organum [http://gallica.bnf.fr/ark:/12148/bpt6k201287p "
                         "(lire en ligne)], Hachette, 1857, p. 7"),
            "Novum Organum (lire en ligne), Hachette, 1857, p. 7")

    def test_strips_a_labelled_external_link_at_the_start_of_the_string(self):
        self.assertEqual(
            strip_markup("[http://archive.org/details/worksofarchimede029517mbp "
                         "The Works Of Archimedes], Cambridge University Press, 1897, p. 193"),
            "The Works Of Archimedes, Cambridge University Press, 1897, p. 193")

    def test_removes_a_bare_external_link_with_no_label(self):
        self.assertEqual(strip_markup("Voir [https://example.org/page] ici."), "Voir ici.")

    def test_still_reduces_a_wikilink_pipe_after_the_external_link_rule(self):
        """La règle de lien externe ne doit pas prendre un [[…]] pour deux
        liens simples — elle est placée après les règles [[…]]."""
        self.assertEqual(strip_markup("Les [[France|Français]] d'abord"), "Les Français d'abord")

    def test_leaves_an_unpaired_bracket_in_prose_alone(self):
        """Round 1 : un crochet seul, mal apparié (intervalle mathématique),
        ne doit provoquer ni troncature ni corruption — confirmé ici côté
        strip_markup, en plus de la protection déjà testée côté
        template_field."""
        self.assertEqual(
            strip_markup("La probabilite est dans [0,1[ selon Kolmogorov."),
            "La probabilite est dans [0,1[ selon Kolmogorov.")

    def test_unwraps_a_quote_already_enclosed_in_guillemets(self):
        """Le cas Mao Zedong (622633b040) : la page Wikiquote met déjà la
        citation entre « », et sans ce dépouillement le rendu Telegram double
        les guillemets (« « … » »)."""
        self.assertEqual(
            strip_markup("« La révolution n'est pas un dîner de gala. »"),
            "La révolution n'est pas un dîner de gala.")

    def test_leaves_an_internal_guillemet_pair_alone(self):
        """Discours direct rapporté à l'intérieur de la phrase : les
        guillemets ne portent pas sur le texte entier, ils doivent rester."""
        self.assertEqual(
            strip_markup("Ma tante me disait : « Si tu te tais, on te croira sage. »"),
            "Ma tante me disait : « Si tu te tais, on te croira sage. »")

    def test_leaves_a_trailing_closing_guillemet_without_a_matching_opening_alone(self):
        """Une citation qui finit sur '»' sans avoir commencé par '«' n'est pas
        une paire enveloppante — ne rien toucher."""
        self.assertEqual(
            strip_markup("toute la sagesse humaine sera dans ces deux mots :« Attendre et espérer ! »"),
            "toute la sagesse humaine sera dans ces deux mots :« Attendre et espérer ! »")

    def test_replaces_br_with_a_space_instead_of_gluing_words(self):
        """Un saut de ligne wikitext supprimé sans rien à la place colle les
        mots voisins (observé sur 'ÉPIGRAMMEOuvrage…' dans le corpus récolté)."""
        self.assertEqual(strip_markup("mot<br/>suivant"), "mot suivant")
        self.assertEqual(strip_markup("mot<br />suivant"), "mot suivant")
        self.assertEqual(strip_markup("mot<BR>suivant"), "mot suivant")

    def test_still_glues_words_across_a_generic_tag(self):
        """Le correctif est ciblé sur <br> uniquement : une autre balise
        (ex. <i>) ne doit pas se voir attribuer le même traitement."""
        self.assertEqual(strip_markup("mot<i>x</i>suivant"), "motxsuivant")


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

    def test_template_field_matches_an_unaccented_field_name(self):
        """Une page qui écrit 'Editeur'/'annee' sans accent ne doit pas perdre
        le fragment correspondant dans la ligne de source."""
        self.assertEqual(
            template_field("Réf Livre|Editeur=Belin|annee=2018", "éditeur"), "Belin")
        self.assertEqual(
            template_field("Réf Livre|Editeur=Belin|annee=2018", "année"), "2018")

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
