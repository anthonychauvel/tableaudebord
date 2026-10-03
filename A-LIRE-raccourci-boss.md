# Raccourci iPhone « Veille BOSS » (02/10/2026)

boss.gouv.fr bloque les serveurs (GitHub : délai dépassé ; Cloudflare : erreur 520).
Ton iPhone, lui, y accède. Le Raccourci lit chaque lundi les pages listées dans
`boss-pages.txt` et dépose le tout dans `boss-capture.json` ; le tableau de bord
compare avec la capture précédente (－ avant / ＋ après) au passage de 9h07 UTC.

## 1. Jeton GitHub (une fois)
github.com → photo → Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token :
- Nom : raccourci-boss · Expiration : 1 an
- Repository access : Only select repositories → tableaudebord
- Permissions → Repository permissions → Contents : Read and write
Copie le jeton (github_pat_…) : il ne s'affiche qu'une fois.

## 2. Le Raccourci (app Raccourcis → +)
Nom : Veille BOSS. Actions, dans l'ordre :
1. Texte : colle ton jeton → Renommer la variable : Jeton
2. URL : https://raw.githubusercontent.com/anthonychauvel/tableaudebord/main/boss-pages.txt
3. Obtenir le contenu de l'URL
4. Diviser le texte : Nouvelles lignes
5. Dictionnaire (vide) → Définir la variable : Pages
6. Répéter avec chaque élément (Texte divisé) :
   - Si Élément répété commence par https
     - Obtenir le contenu de l'URL (Élément répété)
     - Définir la valeur du dictionnaire : clé Élément répété, valeur Contenu de l'URL, dans Pages
     - Définir la variable : Pages (Dictionnaire)
   - Fin si
7. Date actuelle → Formater la date : ISO 8601
8. Définir la valeur du dictionnaire : clé _date, valeur Date formatée, dans Pages → Définir la variable : Pages
9. Obtenir le contenu de l'URL : https://api.github.com/repos/anthonychauvel/tableaudebord/contents/boss-capture.json
   Méthode GET · En-têtes : Authorization = Bearer [Jeton] ; Accept = application/vnd.github+json
10. Obtenir la valeur du dictionnaire : clé sha → Définir la variable : SHA
11. Texte : [Pages] → Encoder en base64 (Retours à la ligne : Aucun)
12. Obtenir le contenu de l'URL : même adresse qu'en 9, Méthode PUT, mêmes en-têtes,
    Corps de la requête JSON : message (Texte) = BOSS capture iPhone ;
    content (Texte) = Texte encodé en base64 ; sha (Texte) = SHA
13. Afficher la notification : Capture BOSS envoyée

## 3. Automatisation
Raccourcis → Automatisation → + → Heure de la journée → 7:00, Hebdomadaire, lundi →
Exécuter immédiatement → Veille BOSS.

## Ajouter des pages
Dans Safari, ouvre une rubrique du BOSS utile (heures supplémentaires, réduction
générale, avantages en nature…), copie l'adresse et ajoute-la à `boss-pages.txt`
sur GitHub (crayon ✏️). Le tableau de bord ajoute aussi tout seul les liens qu'il
repère, quand le Raccourci envoie la page en HTML.

## Alertes
- 🏛️ BOSS — page modifiée (🔴 si taux, plafond, SMIC, exonération…)
- 📡 « le Raccourci n'a rien envoyé depuis X jours » au-delà de 10 jours
