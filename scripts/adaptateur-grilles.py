#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADAPTATEUR-GRILLES.PY — sortie JSON pour le tableau de bord, sans toucher
à verifier-fraicheur.py

verifier-fraicheur.py est déjà déployé et tourne chaque mercredi via GitHub
Actions, en écrivant du markdown. Le modifier pour lui ajouter une sortie
JSON risquerait d'introduire une régression dans un script qui fonctionne
déjà en production, pour un besoin qui ne concerne que ce tableau de bord.

Ce script importe donc verifier-fraicheur.py comme un module et réutilise
SES fonctions de collecte (clauses_salaire, date_de_grille, extrait_montants…)
pour produire directement du JSON. La logique de détection est identique au
script de production ; seule la mise en forme change.

USAGE
    python3 adaptateur-grilles.py --racine /chemin/vers/hs --fonds /chemin/vers/droit --json sortie.json
"""
import argparse
import glob
import importlib.util
import json
import os
import re


def charger_module(chemin):
    spec = importlib.util.spec_from_file_location("verifier_fraicheur", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=".")
    ap.add_argument("--fonds", required=True)
    ap.add_argument("--marge", type=int, default=30)
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    ici = os.path.dirname(os.path.abspath(__file__))
    vf = charger_module(os.path.join(ici, "verifier-fraicheur.py"))

    gp = os.path.join(args.racine, "GrillePaye")
    data = json.load(open(os.path.join(gp, "ccn-data.json"), encoding="utf-8"))
    grilles = data["grilles"]

    # Même garde-fou que dans verifier-fraicheur.py : une CCN fusionnée vers
    # une autre qui a déjà une vraie grille n'est pas "à créer".
    s_idx = open(os.path.join(gp, "index.html"), encoding="utf-8", errors="replace").read()
    mf = re.search(r"const CCN_FUSIONS=(\{.*?\});", s_idx, re.S)
    fusions = json.loads(mf.group(1)) if mf else {}

    resultat = {"module": "grilles-ccn", "alertes": []}

    for chemin in sorted(glob.glob(os.path.join(args.fonds, "output", "ccn", "*.json"))):
        idcc = os.path.splitext(os.path.basename(chemin))[0]
        if idcc.startswith("_"):
            continue
        try:
            fonds_data = json.load(open(chemin, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(fonds_data, dict) or "_error" in fonds_data:
            continue

        clauses = vf.clauses_salaire(fonds_data)
        if not clauses:
            continue
        clauses.sort(key=lambda c: c[0], reverse=True)
        d_fonds, titre, texte = clauses[0]  # d_fonds est déjà un datetime

        # Même raison qu'ailleurs : une fusion ne sera plus mise à jour
        # individuellement, sa propre grille peut être vide ou cassée sans
        # que ça compte -- exclue avant même de la regarder, pas seulement
        # quand elle est totalement absente.
        if idcc in fusions:
            continue

        g = grilles.get(idcc)
        if not g:
            resultat["alertes"].append({
                "categorie": "grille-a-creer",
                "gravite": "basse",
                "titre": f"IDCC {idcc} : clause au fonds, aucune grille dans l'app",
                "detail": f"{titre} ({d_fonds.strftime('%d/%m/%Y')})",
            })
            continue

        d_grille = vf.date_de_grille(g.get("d"))
        if not d_grille:
            resultat["alertes"].append({
                "categorie": "grille-sans-date",
                "gravite": "basse",
                "titre": f"IDCC {idcc} : pas de date exploitable",
                "detail": "Impossible de comparer à la veille tant que le champ date n'est pas renseigné.",
            })
            continue

        # Même garde-fou que dans verifier-fraicheur.py : une région à jour
        # suffit, même quand la référence n'a pas bougé. Ce script réutilise
        # les FONCTIONS de verifier-fraicheur.py mais a sa propre boucle de
        # comparaison — le correctif "régions" n'y était pas automatique.
        d_plus_recente = d_grille
        for region in (g.get("regions") or {}).values():
            d_region = vf.date_de_grille(region.get("d"))
            if d_region and d_region > d_plus_recente:
                d_plus_recente = d_region

        ecart = (d_fonds - d_plus_recente).days
        if ecart > args.marge:
            montants = vf.extrait_montants(texte)
            resultat["alertes"].append({
                "categorie": "grille-perimee",
                "gravite": "haute" if ecart > 180 else "moyenne",
                "titre": f"IDCC {idcc} : grille dépassée de {ecart} jours",
                "detail": f"{titre} — " + (" · ".join(montants[:2]) if montants else
                          "aucun montant repérable, ouvrir la clause"),
            })

    print(f"{len(resultat['alertes'])} alerte(s) grilles.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
