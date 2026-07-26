# Audit de couverture — avant de créer le dépôt

11 vérifications maintenant (contre 5 dans le premier lot), 147 alertes réelles
(contre 126). Ce qui suit sert à décider si c'est suffisant pour créer le dépôt,
ou s'il manque encore quelque chose d'important.

## Ce qui a été ajouté dans cette passe

| Vérification | Pourquoi elle manquait | Ce qu'elle trouve maintenant |
|---|---|---|
| **Santé des grilles** (`verifier-grilles.py`, déjà existant) | Construit, testé, jamais branché au tableau de bord — un oubli pur et simple du premier lot | 3 sous le SMIC, 8 anciennes, 12 placeholders |
| **Cohérence CCN** (`verifier-ccn.py`, déjà existant) | Même oubli | 72 hors référentiel DARES (résumé, pas listés un par un) |
| **Liens internes cassés** | Aucune vérification ne couvrait les `<a href>`, seulement les images/scripts | A trouvé `outils/outils.html` — un doublon orphelin avec ses propres liens faux |
| **Livrables de session** | Aucun moyen de savoir ce qui, de notre travail ensemble, est réellement en ligne | Confirme : mode sobre du menu, encart Taiko, mode sobre outils, onglet Nos sources — tous encore en bac à sable |

## Couverture par catégorie, maintenant

| Catégorie | Vérifications | Alertes |
|---|---|---|
| Grilles CCN | fraîcheur + santé (SMIC, ancienneté, placeholders) | 129 |
| MonLegiTexte | lecture du dernier audit du fonds | 0 |
| 8 modules | présence, assets cassés, cohérence CCN, liens internes, livrables de session | 8 |
| 105 outils | citations d'articles, liens internes | 7 |
| Guide SEO | conventions périmées non signalées, liens internes | 3 |

## Ce qui reste délibérément hors périmètre

Pas oublié — évalué et laissé de côté pour de vraies raisons, pas par manque
de temps :

- **JSON-LD du guide** (validité du balisage schema.org) — les 982 pages n'ont
  pas été relues pour ça ; ajoutable si tu veux, mais pas fait ici.
- **IDCC disparus sans repreneur** (comme l'ex-1314) — `CCN_FUSIONS` ne
  couvre que les fusions AVEC repreneur nommé. Une deuxième liste serait
  nécessaire pour ce cas, déjà signalé dans le lot précédent.
- **Contenu des 92 « grilles à créer »** — volontairement laissé en simple
  liste : leur trier un ordre de priorité mérite ta lecture, pas un script.
- **Vérification du contenu des 3 clauses non lisibles trouvées par
  `verifier-outils`** (L431-1, L461-1, R351-12) — le script signale l'échec
  de récupération, il ne devine pas le bon numéro à ta place.

## Ce qui pourrait encore être ajouté, si tu veux aller plus loin

Deux idées non construites, pour ne pas gonfler ce lot indéfiniment sans ton
accord :
- Un contrôle de **cohérence entre le menu et les modules réels** (un module
  référencé dans `menu.html` mais absent du dépôt, ou l'inverse) — extension
  naturelle de ce qui existe déjà pour les assets.
- Un contrôle **JSON-LD** pour le guide, si le référencement Google t'importe
  au point de vouloir une alerte dessus.

Dis-moi si l'un des deux te semble utile, ou si tu préfères créer le dépôt
maintenant avec cette couverture.
