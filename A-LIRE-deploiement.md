# Tableau de bord de veille perso — installation

Un nouveau dépôt, une PWA installable, privée (`robots.txt` interdit tout,
`<meta name="robots" content="noindex">` en plus). Cinq catégories, chacune
avec de vraies alertes calculées à partir de tes trois dépôts existants.

---

## Créer le dépôt

1. Sur `github.com`, crée un nouveau dépôt (public ou privé — voir remarque
   plus bas). Nomme-le comme tu veux, par exemple `veille`.
2. Dépose-y tout le contenu de ce dossier, **en n'oubliant pas** `.github/workflows/regenerer.yml`
   (masqué sur iOS — voir la méthode habituelle : Safari → Add file → Create
   new file → taper le chemin complet avec les `/`).

## Sur la confidentialité

`robots.txt` et la balise `noindex` empêchent l'indexation, mais **n'importe
qui connaissant l'URL peut ouvrir la page** — ce n'est pas une authentification.
Les alertes exposent des détails internes (bugs, citations cassées, grilles
en retard) que tu ne montrerais pas à un visiteur. Deux options :
- **Dépôt privé** sur GitHub, hébergé en Cloudflare Pages/Workers avec le
  domaine non communiqué nulle part (le plus simple, cohérent avec ce que
  tu fais déjà) ;
- Si tu veux une vraie protection par mot de passe plus tard, Cloudflare
  Access peut se greffer devant sans changer le code.

## Héberger

Même geste que tes autres sites : connecte le dépôt à Cloudflare Pages
(ou active GitHub Pages, selon ta préférence). Aucun secret à configurer —
les trois dépôts sources (`tonytonic/hs`, `anthonychauvel/droit`,
`tonytonic/Guide`) sont tous publics, le workflow les lit sans jeton.

## Installer sur ton téléphone

Ouvre l'URL dans Safari → icône partager → **Sur l'écran d'accueil**. L'icône
et le nom (« Veille ») apparaissent, elle s'ouvre en plein écran comme une
vraie app.

## Tenir à jour tout seul

`.github/workflows/regenerer.yml` tourne lundi, mercredi et jeudi à 9h UTC —
après les runs de l'aspirateur et de la vérification des grilles, pour
toujours refléter les données les plus récentes. Il régénère `donnees.json`
et le commit ; si Cloudflare Pages est branché sur push, le tableau de bord
se met à jour automatiquement.

Lançable aussi à la main depuis l'app GitHub (Actions → Régénérer les
données de veille → Run workflow).

---

## Les 5 catégories, ce qu'elles vérifient réellement

| Catégorie | Vérifie | Résultat du premier run |
|---|---|---|
| **Grilles CCN** | Réutilise `verifier-fraicheur.py` (inchangé) sans le modifier | 117 alertes |
| **MonLegiTexte** | Lit le dernier audit déjà généré par le fonds — ne refait aucun diff | 0 (rien de réel depuis le dernier run) |
| **8 modules** | Présence des 8 modules + références cassées (img/script vers un fichier absent) | 1 (taiko pas en prod — normal, tu l'as confirmé) |
| **105 outils** | Chaque citation d'article (`data-art`, `SH.art()`) existe-t-elle réellement, et est-elle encore en vigueur d'après le fonds ? | 5 (2 citations orphelines, 3 non confirmées) |
| **Guide SEO** | Conventions fusionnées citées sans mention historique | 3 (dont 2 déjà connues, 1 nouvelle) |

## Ce que ce premier run a trouvé de concret

- **2 citations d'articles absentes d'`articles-loi.js`** (`L1214-8-2`,
  `L225-102-1`) — la citation s'affiche vide sur la page qui les utilise.
- **3 articles de code de la sécu** (`L431-1`, `L461-1`, `R351-12`) que le
  fonds a tentés mais où Légifrance n'a rien renvoyé — à vérifier que le
  numéro cité est le bon.
- **Une page de guide non repérée manuellement** :
  `femme-valet-chambre-hs.html` cite l'IDCC 800 (fusionné) sans le dire,
  en plus de la page déjà connue.

## Une limite honnête, pas cachée

Le contrôle du guide ne détecte que les fusions **avec repreneur nommé**
(table `CCN_FUSIONS`). L'IDCC 1314, qui avait disparu **sans repreneur**,
n'est pas re-détecté par ce mécanisme — il faudrait une deuxième liste
(DARES : conventions closes sans succession) pour le couvrir. Pas construite
dans ce premier lot, à ajouter si tu veux fermer ce trou.

## Un changement de ton, sur ta remarque

L'alerte « module absent » (taiko) est passée de gravité **haute** à
**basse**, et son texte ne suppose plus un oubli : un module en bac à sable
qui n'est pas encore sur la branche de production est un état de travail
normal, pas une alerte à traiter. Le script constate, il ne juge pas — c'est
toi qui sais si l'absence est voulue.
