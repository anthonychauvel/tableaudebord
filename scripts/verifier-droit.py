#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-DROIT.PY — lit le dernier audit déjà produit par le fonds

Ce script ne refait AUCUN diff lui-même : `generate_audit_report.py` compare
déjà le commit courant au précédent via git, à chaque run de l'aspirateur
(lundi/jeudi), et écrit le résultat dans audits/index.json. Reproduire ce
diff ici demanderait un historique git complet (le clone superficiel utilisé
pour les autres contrôles n'en a pas) pour, au final, refaire un travail déjà
fait et déjà fiable.

Ce script se contente donc de lire le dernier run et d'en tirer ce qui
mérite une alerte :
  - un run a-t-il eu lieu récemment (l'aspirateur tourne lundi et jeudi) ?
  - le dernier run a-t-il trouvé un VRAI changement du droit (pas du simple
    rattrapage) ? C'est la seule distinction qui compte : le rattrapage est
    du bruit de fond attendu, un vrai changement mérite d'être lu.

USAGE
    python3 verifier-droit.py --fonds /chemin/vers/droit --json sortie.json
"""
import argparse
import json
import os
from datetime import datetime, timezone

MAX_JOURS_SANS_RUN = 5  # lundi/jeudi : plus de 5 jours = un cycle a été manqué


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonds", required=True, help="Racine du dépôt droit (le fonds)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    resultat = {"module": "monlegitexte-droit", "alertes": []}

    chemin_index = os.path.join(args.fonds, "audits", "index.json")
    if not os.path.isfile(chemin_index):
        resultat["alertes"].append({
            "categorie": "audit-introuvable",
            "gravite": "haute",
            "titre": "Aucun historique d'audit trouvé",
            "detail": f"« {chemin_index} » est absent. Le workflow aspirateur a-t-il "
                      f"déjà tourné au moins une fois sur ce dépôt ?",
        })
        print("index.json introuvable.")
        if args.json:
            json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0

    runs = json.load(open(chemin_index, encoding="utf-8"))
    if not runs:
        print("index.json vide — aucun run enregistré.")
        return 0

    dernier = runs[0]
    print(f"Dernier run : {dernier['date']} {dernier['heure']}")
    print(f"  {dernier['resume']}")

    # Fraîcheur du run lui-même
    try:
        d = datetime.strptime(dernier["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age_jours = (datetime.now(timezone.utc) - d).days
    except Exception:
        age_jours = None

    if age_jours is not None and age_jours > MAX_JOURS_SANS_RUN:
        resultat["alertes"].append({
            "categorie": "run-en-retard",
            "gravite": "moyenne",
            "titre": f"Dernier run vieux de {age_jours} jours",
            "detail": f"L'aspirateur tourne normalement lundi et jeudi. {age_jours} jours "
                      f"sans run suggère un cycle manqué ou le workflow en échec silencieux.",
        })

    # Le signal qui compte réellement : un vrai changement du droit, pas du rattrapage.
    total = dernier.get("total_changements", 0)
    if total and total > 0:
        resultat["alertes"].append({
            "categorie": "changement-reel",
            "gravite": "haute",
            "titre": f"{total} changement(s) réel(s) du droit détecté(s)",
            "detail": f"Run du {dernier['date']} {dernier['heure']} — voir "
                      f"audits/{dernier['fichier']} pour le détail. Ceci n'est pas du "
                      f"rattrapage : quelque chose a effectivement changé dans la loi ou une "
                      f"convention, à distinguer d'un simple complément de collecte.",
        })
    else:
        print(f"  Aucun changement réel — {dernier.get('rattrapages', 0)} rattrapage(s) "
              f"(collecte de fond, rien à lire).")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"\nÉcrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
