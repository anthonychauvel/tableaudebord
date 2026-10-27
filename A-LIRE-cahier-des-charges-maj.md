# Cahier des charges — routine après chaque mise à jour

Ce document fixe ce qui doit être fait **à chaque fois** que la veille
(plan d'action du tableau de bord) entraîne une modification de l'appli,
des outils, de GrillePaye ou du guide. Le rappel figure en tête de chaque
plan d'action exporté (`🧭 Plan d'action par destination`).

Objectif : que les utilisateurs **voient** que l'écosystème est suivi et
mis à jour, et pas seulement que le code le soit.

---

## 1. Nouveautés de l'appli (`nouveautes.html`) — obligatoire

À chaque livraison qui touche l'appli (grille, texte juridique, règle,
correction) :

1. Ajouter un bloc `version` **tout en haut**, juste après la ligne
   `VERSION LA PLUS RÉCENTE — TOUJOURS EN PREMIER` :
   - `v-date` : la date du jour (« 27 octobre 2026 ») ;
   - `v-num` : la version suivante (v10.13 → v10.14) ;
   - le badge `NOUVEAU` sur ce bloc, **retiré** du bloc précédent.
2. Une ligne `item` par modification, en langage simple, tutoiement,
   1 à 2 phrases, avec le tag :
   - `Légal` (nouveau texte, nouvelle règle) ;
   - `Mise à jour` (grille, montants) ;
   - `Correction` (erreur corrigée) ;
   - `Nouveau` (fonction nouvelle).
3. Citer la source courte (avenant, décret, arrêt) quand il y en a une.
4. Reporter le même numéro de version :
   - en bas de `nouveautes.html` : `localStorage.setItem('NV_SEEN','vX.XX')` ;
   - dans `menu.html` : `var NV_DERNIERE = 'vX.XX';`
   Sans ça, le badge du menu ne réapparaît pas.
5. Changer `CACHE_NAME` dans `sw.js` (et noter la modif dans son
   commentaire), sinon les téléphones gardent les anciens fichiers.

Les modifications **uniquement** dans le guide (site) ne vont pas dans
`nouveautes.html` de l'appli, sauf si l'outil équivalent de l'appli
change aussi.

## 2. Reel des mises à jour du jour — à chaque livraison visible

Une courte vidéo verticale pour les réseaux (Instagram, Facebook, YouTube
Shorts, TikTok), qui reprend les points du bloc Nouveautés du jour.

**Format**
- MP4 H.264, **1080 × 1920** (9:16), 30 images/s, **25 à 35 s**.
- Piste audio silencieuse incluse : la musique s'ajoute dans l'appli du
  réseau social (musique libre de droits de la plateforme uniquement).
- Texte important dans la zone centrale : rien d'essentiel dans les
  ~250 px du haut ni les ~350 px du bas (boutons et légende des réseaux).

**Charte**
- Fond sombre de l'appli (`#1a1208`), doré `#f0c040`, police DM Sans
  (dossier `fonts/` de l'appli), icône `icon-512.png`.
- Mêmes tags et mêmes couleurs que `nouveautes.html` (Légal en doré,
  Mise à jour / Correction en bleu).

**Déroulé**
1. Intro (~3,5 s) : icône, « On a bossé pour toi — Les mises à jour du
   jour », n° de version.
2. Une carte par mise à jour (~4,8 s chacune, 3 à 5 cartes) : emoji,
   tag, titre, **un chiffre ou une règle en très gros**, une phrase
   d'explication, la source en petit. Barre de progression en haut.
3. Fin (~5 s) : « Chaque semaine, on suit les textes », 3 coches
   (Journal officiel & conventions, Cour de cassation & Conseil d'État,
   grilles à jour), bouton « Heures Sup France · gratuit », « Sur Google
   Play · détail dans 🆕 Nouveautés ».

**Règles de contenu**
- Seulement ce qui est réellement livré et vérifié (mêmes faits que
  `nouveautes.html`), jamais une annonce non publiée.
- Pas de nom d'entreprise ni de personne tirés d'un arrêt.
- Pas de logo ni de marque de tiers ; pas de musique protégée.
- Chiffres identiques à ceux de l'appli (montants au centime).

**Légende de publication** (modèle)
> Mises à jour du [date] dans Heures Sup France 🦊
> [1 ligne par point]
> Veille juridique chaque semaine, gratuit sur Google Play.
> #droitdutravail #heuressupplementaires #salaries #conventioncollective

## 3. Tableau de bord

- Les alertes traitées sans modification vont dans `exceptions.json`
  avec une note expliquant pourquoi.
- Les alertes traitées par une modification sont notées traitées (et, au
  besoin, une exception datée avec `expire` pour qu'elles reviennent si
  le problème réapparaît).

---

Historique : routine créée le 27/10/2026 (Nouveautés v10.13, premier
Reel « mises à jour du 27 octobre 2026 »).
