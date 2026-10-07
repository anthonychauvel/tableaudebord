# Trois nouveautés — croisement, exceptions, code d'accès

## 1. Croisement guide + 8 modules vs le fonds

Nouveau : `scripts/verifier-citations-ecosysteme.py`, nouvelle section
« Citations juridiques » dans le tableau de bord.

Les 105 outils citent leurs articles via un mécanisme structuré
(`data-art`, déjà couvert par `verifier-outils.py`). Le guide et les 8
modules citent en texte brut, au fil du contenu (« article L1237-1-1 ») —
sans code (travail/sécu) explicite. Ce script teste les deux corpus du fonds
pour chaque article trouvé et retient celui qui répond.

Premier run : 303 articles distincts cités à travers 982 pages de guide + 8
modules, 0 abrogé, 14 non confirmés (le fonds ne les a pas encore, ou n'a
rien renvoyé d'exploitable).

## 2. Exceptions manuelles — `exceptions.json`

Tu peux maintenant fermer une alerte toi-même, directement en éditant
`exceptions.json` sur GitHub — pas besoin de repasser par moi.

Format :
```json
{
  "categorie": "grille-perimee",
  "cle": "IDCC 3250",
  "note": "Pourquoi tu l'ignores",
  "date": "2026-07-26"
}
```
`categorie` doit correspondre exactement à celle vue dans `donnees.json`.
`cle` est un texte qui doit apparaître dans le titre de l'alerte — copie-le
depuis ce que tu vois dans le tableau de bord.

Un exemple réel y est déjà : IDCC 3250 (grille en valeur de point, annexe
jamais extraite) est fermée par cet exemple. Modifie-le ou ajoutes-en
d'autres à la suite.

Les alertes ignorées ne sont pas juste cachées en silence : `donnees.json`
garde le compte (`exceptions_appliquees`), donc rien ne disparaît sans trace.

## 3. Code d'accès

Un écran demande **19871502** avant de montrer le tableau de bord. Une fois
tapé, retenu sur ton appareil (`localStorage`) — tu n'as à le taper qu'une
fois.

**À prendre pour ce que c'est, pas plus** : c'est une barrière côté
navigateur, pas une vraie authentification. Elle arrête quelqu'un qui tombe
sur l'URL par hasard — pas quelqu'un qui la cible délibérément et regarde le
code source ou appelle `donnees.json` directement. Pour une vraie protection
(mot de passe côté serveur), il faudrait Cloudflare Access ou équivalent —
pas construit ici, à voir si tu en as besoin plus tard.

## Sur module5/module6

Confirmé : le mode sobre de Mizuki n'était pas suivi dans
`verifier-modules.py` — rien à retirer, ta décision de ne pas le déployer
n'a besoin d'aucun changement de ce côté.

## Vérifications

| Contrôle | Résultat |
|---|---|
| Citations écosystème : 303 articles, 0 abrogé | testé |
| Exceptions : IDCC 3250 correctement retiré des alertes actives | testé |
| Code d'accès : mauvais code rejeté, bon code déverrouille | testé |
| Persistance après rechargement (localStorage) | testé |
| Tous les scripts compilent, JSON valides, JS valide | oui |

## Règles anti-bruit (07/10/2026)

Le passage du 06/10/2026 affichait 110 points à faire, dont environ 95 de bruit.
Les règles sont regroupées en tête de `exceptions.json`, entre les deux lignes
`=== RÈGLES ANTI-BRUIT … ===`. Une règle = un type de bruit ; pour en couper
une, supprime son bloc.

Nouveaux champs facultatifs d'une exception (les anciennes marchent comme avant) :

| Champ | Effet |
|---|---|
| `motif` | masque si l'expression est dans le titre ou le détail (sans accents, minuscules) |
| `sauf` | ne masque PAS si cette expression est présente |
| `champ: "titre"` | `motif` et `sauf` ne regardent que le titre |
| `avant_jours` | ne masque que les textes datés de plus de N jours (glissant) |
| `expire` | l'exception s'arrête à cette date : l'alerte revient toute seule |
| `categorie: "*"` | vise toutes les catégories |

À la source aussi : `veille-sources-officielles.py` ignore désormais les
circulaires et décisions datées de plus de 180 jours (`DILA_MAX_JOURS`), au lieu
de les signaler comme nouvelles quand l'aspirateur rattrape ses archives.

Simulation sur les données du 06/10/2026 : 189 points → 15.
