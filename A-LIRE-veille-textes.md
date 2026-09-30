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
| Accords d'entreprise | mot-clé | ⚪ regroupés par thème |

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

## Limites connues (voir aussi la réponse de Claude)

- L'aspirateur (dépôt `droit`) ne garde au JORF que les textes dont le
  **titre** contient des mots RH : un décret « relatif à la durée du
  travail » peut ne jamais arriver. À corriger côté `droit`.
- Accords d'entreprise : ni date, ni IDCC stockés par l'aspirateur.
- Conventions : le corps n'est récupéré que pour les avenants salaires /
  heures sup / forfait / temps partiel / classification ; pour les autres,
  seul le titre est lu.
- Chaque convention n'est relue qu'environ toutes les 5 semaines ;
  l'extension au JO arrive souvent avant, d'où l'alerte JORF.
