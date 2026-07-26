#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADAPTATEUR-COHERENCE-CCN.PY — sortie JSON pour verifier-ccn.py

Même principe que l'adaptateur des grilles : verifier-ccn.py tourne en
sous-processus, on parse son markdown plutôt que de le réécrire.

Le signal qui compte vraiment ici est la DIVERGENCE entre fichiers : un même
IDCC décrit différemment selon lequel des 5 fichiers CCN on regarde. C'est
la classe de bug qui a demandé le plus de travail correctif cette session
(2120, 5021, 1776…) — s'il en réapparaît une, c'est prioritaire.

Le compte des « absents du référentiel DARES » (72 aujourd'hui) est résumé en
UNE alerte informative plutôt que 72 lignes individuelles : la plupart sont
déjà des cas connus et classés (mentions pédagogiques, alias internes) — les
lister un par un noierait le signal qui compte sous du bruit déjà vu.

USAGE
    python3 adaptateur-coherence-ccn.py --racine /chemin/vers/hs --dares /chemin/vers/droit/ccn/Dares_*.xlsx --json sortie.json
"""
import argparse
import json
import os
import re
import subprocess
import sys


def lancer_original(racine, dares):
    ici = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(ici, "verifier-ccn.py")
    cmd = [sys.executable, script, "--racine", racine]
    if dares:
        cmd += ["--dares", dares]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=".")
    ap.add_argument("--dares", help="Fichier DARES .xlsx du fonds")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    md = lancer_original(args.racine, args.dares)
    resultat = {"module": "coherence-ccn", "alertes": []}

    m = re.search(r"## ⚠️ (\d+) code\(s\) décrits différemment selon le fichier\n\n(.*?)(?=\n## |\Z)",
                  md, re.S)
    if m:
        n = int(m.group(1))
        bloc = m.group(2)
        codes = re.findall(r"\*\*IDCC (\d+)\*\*", bloc)
        resultat["alertes"].append({
            "categorie": "identite-divergente",
            "gravite": "haute",
            "titre": f"{n} IDCC décrits différemment selon le fichier",
            "detail": f"Un même code désigne deux conventions différentes selon le fichier : "
                      f"{', '.join('IDCC ' + c for c in codes[:6])}"
                      f"{'…' if len(codes) > 6 else ''}. Un des cinq fichiers CCN se trompe.",
        })

    m2 = re.search(r"## (\d+) code\(s\) absent\(s\) du référentiel DARES", md)
    if m2 and int(m2.group(1)) > 0:
        resultat["alertes"].append({
            "categorie": "hors-referentiel-dares",
            "gravite": "basse",
            "titre": f"{m2.group(1)} code(s) absents du référentiel DARES",
            "detail": "Pour la plupart des mentions pédagogiques ou des alias internes déjà "
                      "classés. Voir le rapport complet si tu veux les repasser en revue.",
        })

    print(f"{len(resultat['alertes'])} alerte(s) cohérence CCN.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
