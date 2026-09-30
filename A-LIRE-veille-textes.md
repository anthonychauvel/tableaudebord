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

## Limite qui reste

Chaque convention n'est relue qu'environ toutes les 5 semaines ; l'arrêté
d'extension au JO arrive souvent avant, d'où l'alerte JORF « concerne une
convention de l'appli ».
