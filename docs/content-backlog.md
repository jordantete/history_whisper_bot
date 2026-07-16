# Content backlog — sujets additionnels

Issu de la tâche Notion *« Investiguer les sujets additionnels (Chine, Milgram, Péloponnèse…) »*.
Objectif : élargir le backlog **au-delà des figures individuelles**. Recherche menée sujet par sujet,
chaque figure vérifiée contre la contrainte dure du pipeline (`scripts/enrich_figures.py`) :
**article Wikipédia EN + FR** (bio auto-fetch par titre) **+ portrait/illustration sur Commons**.

## État d'implémentation (76 → 164 figures)

**60 figures ajoutées** en 5 lots + Mao. Tous les sujets Notion couverts.
**+ Lafayette** (demande utilisateur, 2026-07-16) — héros des deux mondes ; Lamartine était déjà présent.
**+ 27 figures « incontournables »** (lot 2026-07-16, validé utilisateur) — comblement des trous au cœur
des périodes déjà couvertes : Révolution/Empire (Napoléon Bonaparte, Louis XVI, Marie-Antoinette,
Mirabeau, Olympe de Gouges) · Ancien Régime/médiéval (Louis XIV, François Ier, Catherine de Médicis,
Jeanne d'Arc) · Antiquité (Alexandre le Grand, Cléopâtre, Auguste, Hannibal, Néron) · Sciences
(Isaac Newton, Galilée, Louis Pasteur, Marie Curie, Lavoisier) · Lettres (Victor Hugo, Molière, Zola,
Alexandre Dumas) · Mythes (Ulysse, Achille, Méduse, Orphée). Chaque figure = bio EN+FR +
portrait Commons + 3 faits marquants EN/FR *grounded* et distincts de la bio.

- **Ajoutées** : Saussure, Barthes, Milgram · Chine (Qin Shi Huang, Wu Zetian, Cixi, Zheng He, Sun Yat-sen,
  Puyi, Tchang Kaï-chek, Zhu Yuanzhang, Cao Cao, Zhuge Liang, Sun Tzu, Kangxi, Yongle, Sima Qian, Laozi,
  Liu Bei, Guan Yu, Sun Quan, Mao Zedong) · Révolution (Danton, Saint-Just, Marat, Sieyès, Lazare Carnot,
  Camille Desmoulins, Barras, Tallien, Babeuf, Hébert, Couthon) · Victorien (Victoria, Darwin, Dickens,
  Faraday, Nightingale, Brunel, James Watt, Stephenson, Ada Lovelace, Charles Babbage) · Péloponnèse
  (Périclès, Thucydide, Alcibiade, Lysandre, Nicias) · Mythes (Scylla, Charybde) · Psycho (Pavlov, Skinner,
  Zimbardo, John B. Watson) · Sémio (Eco, Peirce, Jakobson, Greimas) · Sumatra (Iskandar Muda, Adityawarman).
- **Écartées — décision utilisateur (2026-07-08)** :
  - *Sans portrait (fallback texte), non retenues* : **Cléon** (avait été ajouté puis retiré), Asch, Harlow,
    Hjelmslev, Charles W. Morris.
  - *Péloponnèse Tier C (sans portrait), abandonnées* : Brasidas, Gylippe, Démosthène (général), Archidamos II.
  - *Han Xin* : pas d'article FR → rejetée (gate EN+FR).
  - *Kubilai Khan* : abandonnée (chevauche Gengis Khan déjà présent).
- **Gardée malgré la sensibilité** : Mao Zedong (portrait ✅).

## Décision de modèle de données (recommandation unanime)

Le bot sert **une personne par entrée** (`HistoricalFigure`). Plusieurs sujets sont des
**événements / disciplines / mythes**, pas des individus. Verdict de la recherche : **décomposer en
personnes, garder le modèle actuel, ne PAS construire de type « thème/concept » maintenant.**

- Un événement/expérience/discipline se rattache proprement à un auteur : la guerre du Péloponnèse →
  ses acteurs ; l'expérience de Milgram → Milgram ; la sémiologie → ses fondateurs. Le contenu
  « punchline » vit dans les `faits marquants` de la personne.
- Cas qui ne rentrent **pas** dans le modèle personne :
  - **Charybde et Scylla** : pas d'article bilingue combiné. → ajouter **Scylla** (et option. **Charybde**)
    comme entrées légendaires, exactement comme Prométhée / Hercule / Icare & Dédale déjà présents.
  - **Royaume de Sumatra** : seulement 2 individus exploitables (voir plus bas), le reste échoue le
    gate FR. Le « roi exécuté » = épisode du sultanat de Pasai (usurpateur capturé par Zheng He et
    exécuté en Chine) → pas d'article dédié, à porter comme **anecdote sur Zheng He**.
  - **Société victorienne / révolution industrielle**, **dynastie Ming**, **Trois Royaumes** = thèmes →
    mappés sur des personnes ci-dessous.
- Un type « ère/thème » (fetch depuis un article de *période* + image représentative) reste possible
  **plus tard**, en chemin de code opt-in séparé, si on veut des cartes thématiques. Pas requis ici.

## Contrainte pipeline : `OVERRIDES` à ajouter

Beaucoup de figures ont des titres FR/EN différents ou un risque de désambiguïsation (mauvais article/
portrait). Bloc prêt à coller dans `OVERRIDES` de `scripts/enrich_figures.py` (vérifier les Wikidata IDs
au moment de l'ingestion) :

```python
# Chine
"Qin Shi Huang":   {"fr": "Qin Shi Huang", "en": "Qin Shi Huang"},
"Wu Zetian":       {"fr": "Wu Zetian", "en": "Wu Zetian"},
"Cixi":            {"fr": "Cixi", "en": "Empress Dowager Cixi"},          # ⚠ ville du Zhejiang
"Zheng He":        {"fr": "Zheng He", "en": "Zheng He"},
"Sun Yat-sen":     {"fr": "Sun Yat-sen", "en": "Sun Yat-sen"},
"Puyi":            {"fr": "Puyi", "en": "Puyi"},
"Tchang Kaï-chek": {"fr": "Tchang Kaï-chek", "en": "Chiang Kai-shek"},    # ⚠ translittération accentuée
"Zhu Yuanzhang":   {"fr": "Zhu Yuanzhang", "en": "Hongwu Emperor"},       # titré par nom de naissance
"Cao Cao":         {"fr": "Cao Cao", "en": "Cao Cao"},
"Zhuge Liang":     {"fr": "Zhuge Liang", "en": "Zhuge Liang"},
"Sun Tzu":         {"fr": "Sun Tzu", "en": "Sun Tzu"},                    # ⚠ vs Sun Bin
"Kangxi":          {"fr": "Kangxi", "en": "Kangxi Emperor"},             # ⚠ ère vs personne
# Sumatra
"Iskandar Muda":   {"fr": "Iskandar Muda", "en": "Iskandar Muda"},       # ⚠ aéroport/province homonymes
"Adityawarman":    {"fr": "Adityawarman", "en": "Adityawarman"},
# Péloponnèse
"Périclès":        {"fr": "Périclès", "en": "Pericles"},
"Thucydide":       {"fr": "Thucydide", "en": "Thucydides"},
"Alcibiade":       {"fr": "Alcibiade", "en": "Alcibiades"},
"Lysandre":        {"fr": "Lysandre", "en": "Lysander"},
"Nicias":          {"fr": "Nicias", "en": "Nicias"},
"Cléon":           {"fr": "Cléon", "en": "Cleon"},                        # ⚠ commune + moteur
"Démosthène (général)": {"fr": "Démosthène (général)", "en": "Demosthenes (general)"},  # ⚠ vs l'orateur
# Mythe
"Scylla":          {"fr": "Scylla (monstre)", "en": "Scylla"},
"Charybde":        {"fr": "Charybde", "en": "Charybdis"},
# Convention / Directoire
"Danton":          {"fr": "Georges Jacques Danton", "en": "Georges Danton"},
"Sieyès":          {"fr": "Emmanuel-Joseph Sieyès", "en": "Emmanuel Joseph Sieyès"},
"Lazare Carnot":   {"fr": "Lazare Nicolas Marguerite Carnot", "en": "Lazare Carnot"},   # ⚠ ≠ Sadi Carnot déjà présent
"Babeuf":          {"fr": "Gracchus Babeuf", "en": "François-Noël Babeuf"},
"Hébert":          {"fr": "Jacques-René Hébert", "en": "Jacques Hébert"},
# Victorien
"Victoria":        {"fr": "Victoria (reine du Royaume-Uni)", "en": "Queen Victoria"},
"Brunel":          {"fr": "Isambard Kingdom Brunel", "en": "Isambard Kingdom Brunel"},  # ⚠ ≠ Marc Isambard Brunel (père)
# Psychologie / sémiologie
"Skinner":         {"fr": "Burrhus Frederic Skinner", "en": "B. F. Skinner"},
"Watson":          {"fr": "John Broadus Watson", "en": "John B. Watson"},               # ⚠ homonymes (Dr Watson…)
"Asch":            {"fr": "Solomon Asch", "en": "Solomon Asch"},                         # ⚠ ≠ Sholem Asch (romancier)
```

---

## Backlog par sujet

Légende portrait : ✅ portrait/illustration exploitable · 🖼️ buste antique · ⚠️ image faible/absente
(fallback texte — déjà géré par `send_photo → text`, commit bbfe872).

### 1. Histoire de la Chine — mine d'or (~12 sûres + banc de touche)

| Figure | Portrait | Note |
|---|---|---|
| Qin Shi Huang | ✅ | 1ᵉʳ empereur, armée de terre cuite |
| Wu Zetian | ✅ | unique impératrice régnante, stèle vierge |
| Cixi | ✅ | impératrice douairière Qing · ⚠ désambig ville |
| Zheng He | ✅ | amiral eunuque, bateaux-trésors + anecdote Pasai |
| Sun Yat-sen | ✅ | père de la Chine moderne |
| Puyi | ✅ | dernier empereur (*Le Dernier Empereur*) |
| Tchang Kaï-chek | ✅ | Kuomintang/Taïwan *(seed)* · ⚠ titre FR accentué |
| Zhu Yuanzhang (Hongwu) | ✅ | fondateur Ming *(seed « dynastie Ming »)* |
| Cao Cao | ✅ | Trois Royaumes *(seed)* |
| Zhuge Liang | ✅ | stratège légendaire (flèches empruntées) |
| Sun Tzu | ✅ | *L'Art de la guerre* · ⚠ vs Sun Bin |
| Kangxi | ✅ | plus long règne · ⚠ ère vs personne |
| **Flags** | | Mao Zedong (sensible/récent — décision éditoriale) · Kubilai Khan (chevauche Gengis Khan déjà présent) |
| **Banc** | | Laozi (`Lao Tseu`), Sima Qian, Yongle, Liu Bei, Guan Yu, Sun Quan, Han Xin |

### 2. Royaume de Sumatra — mince (2 seulement)

| Figure | Portrait | Note |
|---|---|---|
| Iskandar Muda | ✅ | sultan d'Aceh, « le jeune Alexandre » · ⚠ homonymes aéroport/province |
| Adityawarman | ⚠️ | roi Minangkabau ; article FR court (bio brève) ; image = statue Bhairava |

Échouent le gate FR (EN seul, à rejeter) : Balaputra, Dapunta Hyang Sri Jayanasa, Sangrama Vijayottunggavarman.
« Roi exécuté » = usurpateur de Pasai capturé par Zheng He → **anecdote sur Zheng He**, pas une figure.

### 3. Guerre du Péloponnèse — décomposée en acteurs

| Figure | Portrait | Note |
|---|---|---|
| Périclès | 🖼️ | figure clé, oraison funèbre, mort de la peste |
| Thucydide | 🖼️ | historien-stratège, exilé 20 ans |
| Alcibiade | 🖼️ | change de camp 3×, élève de Socrate |
| Lysandre | ⚠️ | vainqueur spartiate final ; gravure imaginaire |
| Nicias | ⚠️ | paix de Nicias ; pas de portrait |
| Cléon | ⚠️ | démagogue ; ⚠ désambig commune/moteur |
| Brasidas / Gylippe / Démosthène (gén.) / Archidamos II | ⚠️ | Tier C : image = carte/bataille ; Démosthène **⚠ HAUT** (vs l'orateur) |

### 4. Charybde et Scylla — mythe (entrées légendaires)

| Figure | Portrait | Note |
|---|---|---|
| Scylla | ✅ | `Scylla (monstre)` — comme Prométhée/Hercule |
| Charybde | ✅ | option. jumelle, se citent mutuellement |

Pas de carte combinée « Charybde et Scylla » (aucun article bilingue commun).

### 5. Convention nationale / le Directoire

| Figure | Portrait | Note |
|---|---|---|
| Danton | ✅ | « De l'audace… » |
| Saint-Just | ✅ | l'Archange de la Terreur, 25 ans |
| Marat | ✅ | *La Mort de Marat* (David) |
| Sieyès | ✅ | *Qu'est-ce que le Tiers État ?* · « J'ai vécu » |
| Lazare Carnot | ✅ | Organisateur de la Victoire · ⚠ **≠ Sadi Carnot déjà présent** |
| Camille Desmoulins | ✅ | déclencheur de la Bastille |
| Barras | ✅ | homme fort du Directoire, lance Bonaparte |
| Tallien | ✅ | 9 Thermidor |
| Babeuf | ✅ | Conjuration des Égaux · ⚠ titres EN/FR différents |
| Hébert | ✅ | *Le Père Duchesne* |
| Couthon | ✅ | triumvirat, loi de Prairial |

Top 5 : Danton, Saint-Just, Marat, Sieyès, Lazare Carnot.

### 6. Société victorienne / révolution industrielle

| Figure | Portrait | Note |
|---|---|---|
| Queen Victoria | ✅ | · ⚠ titre FR `Victoria (reine du Royaume-Uni)` |
| Charles Darwin | ✅ | HMS Beagle, *L'Origine des espèces* |
| Charles Dickens | ✅ | feuilletons, fabrique de cirage |
| Michael Faraday | ✅ | induction électromagnétique |
| Florence Nightingale | ✅ | Dame à la lampe, rose polaire |
| Isambard K. Brunel | ✅ | ingénieur · ⚠ ≠ Marc Isambard Brunel (père) |
| James Watt | ✅ | machine à vapeur |
| George Stephenson | ✅ | père du rail · ⚠ ≠ Robert Stephenson (fils) |
| Ada Lovelace | ✅ | première programmeuse |
| Charles Babbage | ✅ | machine analytique |

Top 5 : Victoria, Darwin, Dickens, Faraday, Nightingale. Cluster ingénieurs = profondeur « révolution industrielle ».

### 7. Expérience de Milgram (→ scientifiques)

| Figure | Portrait | Note |
|---|---|---|
| Stanley Milgram | ✅ | *l'ask direct* — soumission à l'autorité, six degrés |
| Ivan Pavlov | ✅ | conditionnement classique |
| B. F. Skinner | ✅ | conditionnement opérant · titre FR différent |
| Philip Zimbardo | ✅ | prison de Stanford |
| John B. Watson | ✅ | petit Albert · ⚠ homonymes |
| Solomon Asch | ⚠️ | conformité ; pas de portrait libre · ⚠ ≠ Sholem Asch |
| Harry Harlow | ⚠️ | attachement (singes) ; pas de portrait |

### 8. Sémiologie / sémiotique (→ fondateurs)

| Figure | Portrait | Note |
|---|---|---|
| Ferdinand de Saussure | ✅ | **éponyme de la sémiologie — plus forte addition** |
| Roland Barthes | ✅ | *Mythologies* — plus fort pour public FR |
| Umberto Eco | ✅ | *Le Nom de la rose* |
| Charles S. Peirce | ✅ | icône/indice/symbole |
| Roman Jakobson | ✅ | six fonctions du langage |
| Greimas | ⚠️ | carré sémiotique ; portrait probable |
| Hjelmslev | ⚠️ | glossématique ; portrait incertain |
| Charles W. Morris | ⚠️ | syntaxe/sémantique/pragmatique ; pas de portrait · ⚠ nom commun |

---

## Ordre de priorité global (faisabilité × notoriété)

1. Ferdinand de Saussure, Roland Barthes, Stanley Milgram
2. Chine Tier A : Qin Shi Huang, Wu Zetian, Cixi, Zheng He, Sun Yat-sen, Puyi, Tchang Kaï-chek
3. Révolution : Danton, Saint-Just, Marat, Sieyès, Lazare Carnot
4. Victorien : Victoria, Darwin, Dickens, Faraday, Nightingale
5. Péloponnèse Tier A : Périclès, Thucydide, Alcibiade + Scylla
6. Reste des sujets (portrait ✅) : Pavlov, Skinner, Eco, Peirce, Jakobson, Zimbardo, Cao Cao, Zhuge Liang, Sun Tzu, Kangxi, Zhu Yuanzhang, ingénieurs victoriens, Desmoulins/Barras/Tallien/Babeuf/Hébert/Couthon
7. Tier fallback texte (pas de portrait) : Asch, Harlow, Hjelmslev, Charles W. Morris, Péloponnèse Tier B/C, Adityawarman

**Total exploitable : ~60 figures** compatibles avec le pipeline actuel, sans changement de modèle.
