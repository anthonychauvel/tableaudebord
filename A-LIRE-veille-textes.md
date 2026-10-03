# Veille des nouveaux textes — ce qui change

## En bref

- **📰 Nouvel onglet « Textes »** : tout texte NOUVEAU du fonds qui touche
  tes sujets, gardé 45 jours, filtrable par fonds (JO, conventions, Code,
  accords) et par thème.
- **Articles cités** : alerte 🔴 si l'un d'eux n'existe plus, avec
  « Remplacé par … » et son dernier texte connu. Étiquette violette
  « Changement de sujet » si son texte a changé presque entièrement.
- **MonLegiTexte** : l'alerte « [CGFP + Code civil/pénal] 21 changements »
  ne revient que si un texte a VRAIMENT changé (pas juste été re-téléchargé)
  ET touche tes sujets. Le reste se met à jour tout seul pour les
  utilisateurs, sans te déranger.
- **Fichiers modifiés** : une seule carte au lieu de 123.
- **Accueil** : cartes repliables (touche pour ouvrir), filtres rapides
  (🔴 Vite, 🆕 Nouveau, 📰 Textes, ⚖️ Articles…), les points ⚪ « pour info »
  ne sont plus dans la liste du jour.

## Tes sujets : `mots-cles.json`

Modifiable sur GitHub (crayon ✏️), comme `exceptions.json`. Un thème =
un nom, un emoji, une liste d'expressions exactes. Majuscules et accents
ne comptent pas. `exclusions` : un texte dont le titre contient une de ces
expressions est ignoré.

## Qui remonte, avec quelle gravité

| Fonds | Remonte si… | Gravité |
|---|---|---|
| Code | nouvel article dans une section qui contient un article cité | 🔴 |
| JORF | modifie un article du Code que tu suis | 🔴 |
| JORF | étend un avenant d'une convention de l'appli | 🟠 (🔴 avec mot-clé) |
| JORF | contient un mot-clé | 🟠 |
| CCN | nouveau texte d'une convention de l'appli (340 IDCC) | 🔴 |
| CCN | nouveau texte d'une autre convention avec mot-clé | 🟠 |
| Jurisprudence (cassation, appel) | applique un article que tu cites | 🔴 |
| Jurisprudence | mot-clé (décisions de moins d'un an) | 🟠 |
| Accords d'entreprise | mot-clé | ⚪ regroupés par thème |

## Articles clés hors Code du travail

Une vingtaine d'articles, listés dans `articles_cles_autres_codes.txt` (dépôt
`droit`) : CGI art. 81 quater (exonération d'impôt des heures sup), Code des
transports L1321-1 à 10, Code rural L713-1 à 6 et L713-13. Suivis comme les
articles cités : texte modifié 🟠 (🔴 si changement de sujet), disparu 🔴.
Un numéro inexistant est simplement ignoré ; la liste se corrige sur GitHub.

## Règles et montants officiels (📐)

Le Code du travail numérique (simulateurs de préavis, indemnités de
licenciement, rupture conventionnelle, retraite, précarité) et l'URSSAF (SMIC,
plafond de la Sécurité sociale, exonération des heures sup, frais pro…)
publient leurs règles de calcul. À chaque nouvelle version, la veille compare
l'ancienne et la nouvelle, valeur par valeur, et ne signale que ce qui a
vraiment changé, avec l'avant / l'après et l'outil de l'appli à revoir.
🔴 si un montant, taux, durée ou coefficient bouge (règle générale ou
convention de l'appli), 🟠 sinon. Mémoire : `regles-officielles.json`.

## Santé de l'aspirateur (🩺 dans Thèmes)

- **Étape en échec** 🔴 : l'aspirateur note chaque étape ratée dans
  `audits/etapes-en-echec.log` (dépôt `droit`) ; le tableau de bord
  l'affiche pendant 7 jours. Avant, un échec (JO du 30/09) passait inaperçu.
- **Dernier passage en échec** 🔴 : état du dernier run lu sur GitHub.
- **Fonds figé** 🟠 : un fonds qui ne reçoit plus rien (JO 10 jours,
  jurisprudence et accords 30 jours, conventions 45 jours).

## Premier passage

Il enregistre l'état de départ **sans aucune alerte** (Code, JO,
conventions, accords, MonLegiTexte). Les alertes commencent au passage
suivant. Un afflux anormal (rattrapage de l'aspirateur) est enregistré sans
alerte, avec juste une carte ⚪ « enregistrés sans alerte ».

## Nouveaux fichiers de mémoire (committés à chaque passage)

- `textes-vus.json` : ce que la veille a déjà vu, plus les alertes des 45
  derniers jours.
- `empreintes-droit.json` : le texte des fichiers cités par les audits de
  MonLegiTexte, pour distinguer un vrai changement d'un simple
  re-téléchargement.

## Aspirateur (dépôt `droit`, branche `veille-textes-aspirateur`)

À fusionner AUSSI, sinon la veille reste partielle :
- **JORF** : le filtre des titres accepte maintenant tes sujets (durée du
  travail, heures sup/complémentaires, temps partiel, repos, nuit, dimanche,
  congés, astreintes…). Avant, un décret « relatif à la durée du travail »
  n'était jamais aspiré.
- **Accords d'entreprise** : date, entreprise et IDCC sont gardés (champ
  `meta`) ; nouveaux thèmes de recherche heures sup, temps partiel, nuit,
  dimanche. Le tableau de bord les affiche et met en tête les accords d'une
  convention de l'appli.
- **Conventions** : nouvelle étape `fetch_recents_details.py` qui récupère le
  texte complet de TOUT avenant des 120 derniers jours (212 en attente
  aujourd'hui), plus seulement salaires / heures sup / forfait / temps
  partiel / classification.

Élargir le filtre JORF fera aspirer d'anciens textes dans les premiers
passages : c'est un rattrapage, ignoré par la veille (seuls les textes
plus récents que le dernier vu sont signalés).

## BOCC — les grilles en PDF (📕, 02/10/2026)

Beaucoup d'avenants « salaires » n'ont dans KALI que leur titre (« tableau non
reproduit, consultable au BOCC ») : la grille est dans le PDF du Bulletin
officiel des conventions collectives.

- **Aspiration** : `bocc.yml` (dépôt `droit`), le mercredi à 5h07 UTC, lit
  l'open data de la DILA (`echanges.dila.gouv.fr/OPENDATA/BOCC/<année>/`),
  télécharge les nouveaux bulletins (PDF, XML ou archives), lit le texte
  (`pdftotext`, OCR français pour les PDF scannés) et le découpe par
  convention dans `output/bocc/<année>/*.json` : IDCC, titre, date de
  signature, « parle de salaires », montants en euros. Mémoire :
  `output/bocc/_vus.json`. Premier passage : seuls les 60 derniers jours.
- **Veille** : chaque texte d'une convention de l'appli remonte dans
  « Conventions » avec le titre « 📕 BOCC — … ». 🔴 si c'est une grille de
  salaires : montants lus, ceux sous le SMIC, et la date de la grille
  actuelle de l'appli pour comparer. Les autres conventions ne remontent
  qu'avec un mot-clé. Rien n'est repris automatiquement : un tableau lu dans
  un PDF peut être mal découpé, tu vérifies dans le bulletin (lien).
- **Santé** : « BOCC » figé au bout de 21 jours sans bulletin ; un échec de
  l'aspiration s'affiche comme les autres étapes (`bocc`).

## BOSS, Parlement, liste DARES (🏛️, 02/10/2026)

Nouvelle section « BOSS, Parlement, liste DARES » (script
`veille-sources-officielles.py`, mémoire `sources-officielles.json`) :

- **BOSS** (boss.gouv.fr) : les pages sur tes sujets (heures sup et
  complémentaires, réduction générale, avantages en nature, frais pro,
  assiette, temps partiel, apprentis…) sont trouvées depuis l'accueil et
  relues à chaque passage. Seuls les paragraphes vraiment ajoutés ou retirés
  remontent (－ avant / ＋ après) ; un simple changement de date de mise à
  jour est ignoré. 🔴 si ça touche un taux, un plafond, le SMIC, une
  exonération ou une majoration.
- **Parlement** : flux RSS du Sénat (textes déposés, affaires sociales) et
  de l'Assemblée (documents, commission des affaires sociales), filtrés par
  tes mots-clés et les mots du travail. 🔴 pour le budget de la Sécu (PLFSS),
  les heures sup, le Code du travail, la durée du travail, le SMIC. Le premier
  passage ne garde que ces textes majeurs (le PLFSS se dépose en octobre).
- **DARES** : alerte si la liste officielle des conventions a plus de 4 mois.
  Côté `droit`, `maj_dares.py` va chercher chaque lundi la dernière version
  (garde l'ancienne si le site bloque) et `aspirateur.yml` installe enfin
  openpyxl : sans lui, la relecture du fichier DARES échouait en silence
  chaque lundi.
- Une source injoignable deux passages de suite = alerte 📡.

## Circulaires, Conseil constitutionnel, Conseil d'État, barèmes sociaux (02/10/2026)

Dans la section « Sources officielles » :
- **📨 Circulaires / instructions** (DGT, DSS…) : `dila-fonds.yml` (dépôt
  `droit`, le mardi) aspire l'open data DILA et garde ce qui touche
  l'écosystème dans `output/circulaires/`.
- **🏛️ Conseil constitutionnel / Conseil d'État** : même aspirateur,
  `output/constit/` et `output/jade/`. « CENSURE / ANNULATION » dans le titre
  quand la décision fait disparaître un article ou un décret ; 🔴 si un
  article cité par l'appli est en cause.
- **🧮 Barèmes hors droit du travail** (chômage, prestations familiales,
  minima sociaux, logement, retraite complémentaire, cotisations, CSG,
  impôt, épargne) : à chaque nouvelle version d'OpenFisca-France (le modèle
  socio-fiscal ouvert de l'État), les valeurs datées des 2 dernières années
  sont comparées ; l'alerte donne les nouvelles valeurs et les outils de
  l'appli à revoir.
- **BOSS** : lu par le Raccourci iPhone (voir A-LIRE-raccourci-boss.md).

## Où traiter chaque alerte + nouvelle présentation (03/10/2026)

Chaque alerte dit maintenant **où elle se traite** dans l'écosystème, avec
les fichiers à ouvrir (liens directs vers GitHub) :

| Destination | Ce que ça couvre |
|---|---|
| 📱 Application | le module précis : M1 compteur annuel, M2 paye, M3 Fox, M4 DTE, M5 Mizuki, M6 Zenji, M7 Mimizuku, Taiko, règles des conventions (ccn/conventions-collectives.js), coquille (menu, sw.js) |
| 🧰 105 outils | l'outil précis (Congés payés, Préavis, Chômage…) ou articles-loi.js |
| 💶 GrillePaye | la convention (IDCC + nom) dans GrillePaye/ccn-data.json, le SMIC |
| 📘 Guide | les pages exactes qui citent l'article ou la convention |
| ⚖️ MonLegiTexte | site et fiches d'articles (souvent « automatique » : ça se met à jour seul) |
| 🩺 Chaîne de veille | aspirateur, sources, tableau de bord : pannes à relancer |

Une alerte peut viser plusieurs endroits (un arrêt sur L3141-3 → Fox, Zenji,
outil Congés payés et les pages du guide qui citent L3141-3).

**Comment c'est calculé** (`scripts/routage.py`, à chaque passage) : la
catégorie de l'alerte, les fichiers qu'elle nomme, les articles de loi cités
(index de TOUS les fichiers de l'appli et du guide), les conventions (IDCC :
grille, règles HS/temps partiel, pages du guide si des montants changent),
les outils que la source désigne elle-même (« Outils de l'appli à revoir »)
et, en dernier, le thème du titre. Rien n'est inventé : une alerte sans
destination reconnue tombe dans « Chaîne de veille › À trier ».

**Écran** : Synthèse (statut, 4 indicateurs, tuiles « Où traiter », actions
prioritaires filtrables par destination, sources surveillées avec leur état),
onglet « Où traiter » (une destination → ses alertes rangées par module,
outil, IDCC ou pages), Textes, Catégories, Historique, Règles. Export
« Plan d'action par destination » : la liste à cocher, rangée par endroit,
avec les fichiers.

`mots-cles.json` : « durées maximales » seul faisait remonter un décret sur la
conservation des données des CAF ; remplacé par « durée(s) maximale(s)
du/de travail ».

## Limite qui reste

Chaque convention n'est relue qu'environ toutes les 5 semaines ; l'arrêté
d'extension au JO arrive souvent avant, d'où l'alerte JORF « concerne une
convention de l'appli ».
