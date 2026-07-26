# Le max de vérification — 4 nouvelles catégories, 9 au total

## Ce qui était vraiment un trou, maintenant couvert

**Syntaxe JS (page cassée)** — `verifier-syntaxe-js.py`. Aucune autre
vérification ne détectait "cette page ne charge plus du tout" — seulement
"cette donnée est périmée". Une virgule oubliée dans un template literal,
ça a cassé des pages plusieurs fois cette session. Passe `node --check` sur
121 fichiers (racine, 8 modules, GrillePaye, 105 outils).

**Structure** — `verifier-jsonld.py` + `verifier-outils-orphelins.py`.
Le JSON-LD était noté "hors périmètre" dès le tout premier lot de ce
tableau de bord, jamais construit depuis — 2763 blocs vérifiés. Les outils
orphelins vérifient dans les deux sens : une clé sans fichier (lien mort),
un fichier sans catégorie (page invisible, inatteignable même par la
recherche interne).

**MonLegiTexte en direct** — `verifier-noindex-live.py`. Le seul script de
tout ce tableau de bord qui fait un vrai appel réseau, plutôt que de lire
un fichier. Vérifie que l'en-tête `X-Robots-Tag: noindex` est réellement
envoyé par le Worker déployé — pas seulement présent dans le code source.

## Un aveu, pas caché

**Je n'ai pas pu tester `verifier-noindex-live.py` en conditions réelles.**
Mon bac à sable n'a pas accès à `workers.dev` (liste d'autorisation réseau
restreinte) — chaque tentative renvoie une erreur `host_not_allowed` de MON
PROPRE environnement, pas une vraie réponse du site. Le code suit un patron
HTTP standard et compile sans erreur, mais son tout premier vrai test sera
le premier run réel sur GitHub Actions. Vérifie ce que ça donne les
premières fois.

## Deux bugs trouvés en construisant, pas juste des scripts qui marchent du premier coup

- **`verifier-outils-orphelins.py`** signalait au départ la quasi-totalité
  des 105 outils comme orphelins — pas plausible. Cause : un antislash
  parasite dans ma chaîne de recherche (`/\*` au lieu de `/*`), qui ne
  matchait jamais le vrai texte. Corrigé et revérifié : 105 fichiers, 105
  clés, zéro orphelin réel.
- **`verifier-syntaxe-js.py`** capturait le mauvais bout de la sortie
  d'erreur de Node (le numéro de version, pas le message d'erreur). Testé
  avec une vraie erreur injectée avant de livrer, pas juste sur du code sain.

## Toujours hors périmètre, par choix, pas par oubli

- **Le calcul lui-même** — aucun script ne vérifie qu'un résultat de calcul
  est juste, seulement que les données sont fraîches et les fichiers
  intègres.
- **Les erreurs JS à l'exécution** — tout ici est de l'analyse statique
  (le code est lu, jamais exécuté dans un vrai navigateur). Un bug qui ne
  se déclenche qu'au clic reste invisible.
- **UI, accessibilité, performance** — hors sujet depuis le début.

## Vérifications

| Contrôle | Résultat |
|---|---|
| Syntaxe JS : 121 fichiers, 0 en erreur — et détecte bien une vraie erreur injectée | testé |
| JSON-LD : 2763 blocs, 982 pages | testé |
| Outils orphelins : bug trouvé et corrigé, 0 orphelin réel confirmé | testé |
| MonLegiTexte en direct | **non testable ici**, à vérifier au premier run réel |
| Pipeline complet : 9 catégories, 154 alertes, aucun plantage | testé |
