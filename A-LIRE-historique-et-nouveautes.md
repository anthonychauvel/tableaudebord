# Historique complet + nouveautés en rouge

## Le problème du compteur de jours

Le titre d'une alerte de grille ("dépassée de 210 jours") change de nombre
CHAQUE JOUR, même si c'est le même problème non résolu. Comparer le titre
entier l'aurait marquée "nouvelle" tous les jours, à tort. La comparaison se
fait donc sur `catégorie + ce qui précède le ' : '` du titre (l'IDCC, le nom
de fichier...) — stable même quand le reste du texte varie.

Testé précisément sur ce cas : même IDCC, jours différents → pas nouveau.
IDCC différent → nouveau. Confirmé aussi sur le vrai pipeline, pas
seulement en synthétique.

## Ce qui apparaît en rouge

Une alerte réellement nouvelle depuis le dernier run : bordure rouge à
gauche, fond légèrement teinté, badge "NOUVEAU". Elle remonte en haut de sa
section (avant même les alertes "haute" plus anciennes), et sa section
s'ouvre automatiquement — pas besoin de fouiller pour la trouver. Une
pastille rouge dans le résumé du haut compte le total.

Premier run après un déploiement : rien n'est marqué nouveau (il n'y a rien
à comparer) plutôt que de tout marquer rouge d'un coup, ce qui n'aiderait
personne à distinguer quoi que ce soit.

## L'historique

Chaque run sauve maintenant un instantané complet dans `historique/`,
nommé par horodatage (`2026-07-26-101605.json`) — jamais écrasé,
jamais supprimé automatiquement. `donnees.json` reste le seul fichier que
le tableau de bord affiche, mais tout ce qui a existé un jour reste
consultable et comparable directement sur GitHub, en ouvrant n'importe quel
fichier du dossier.

À garder en tête pour plus tard : à raison de 3 runs/semaine, ça fait
environ 150 fichiers par an, quelques centaines de Ko au total — rien
d'ingérable, mais si ça devient trop après un an ou deux, on pourra ajouter
un nettoyage des runs les plus anciens.

## Vérifications

| Contrôle | Résultat |
|---|---|
| Clé stable : même IDCC, jours différents → pas nouveau | testé |
| Clé stable : IDCC différent → nouveau | testé |
| Premier run : rien marqué nouveau | testé |
| Vraie nouveauté injectée : badge, bordure, pastille, section ouverte | testé dans un vrai DOM |
| Historique : deux runs consécutifs → deux fichiers distincts, aucun écrasé | testé |
| Pipeline complet + sw.js + syntaxe | tous OK |
