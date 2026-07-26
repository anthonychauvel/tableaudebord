#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-JSONLD.PY — le balisage schema.org du guide est-il valide ?

Un bloc JSON-LD mal formé ne casse rien à l'écran (les navigateurs l'ignorent
silencieusement), mais Google aussi — la page perd ses extraits enrichis
sans qu'aucun signe visible ne le trahisse en la consultant normalement.
Repéré en note dès le premier lot de ce tableau de bord ("hors périmètre"),
jamais construit depuis. Le voici.

USAGE
    python3 verifier-jsonld.py --guide /chemin/vers/Guide --json sortie.json
"""
import argparse
import glob
import json
import os
import re

BLOC = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guide", required=True, help="Racine du dépôt Guide")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    resultat = {"module": "jsonld-guide", "alertes": []}
    n_pages, n_blocs, n_sans_bloc = 0, 0, 0

    for chemin in sorted(glob.glob(os.path.join(args.guide, "*.html"))):
        nom = os.path.basename(chemin)
        html = open(chemin, encoding="utf-8", errors="replace").read()
        blocs = BLOC.findall(html)
        n_pages += 1
        if not blocs:
            n_sans_bloc += 1
            continue
        for i, bloc in enumerate(blocs):
            n_blocs += 1
            try:
                data = json.loads(bloc)
            except json.JSONDecodeError as e:
                resultat["alertes"].append({
                    "categorie": "jsonld-invalide",
                    "gravite": "moyenne",
                    "titre": f"{nom} : bloc JSON-LD #{i+1} invalide",
                    "detail": f"{e} — Google ignorera ce bloc, silencieusement.",
                })
                continue
            if not isinstance(data, dict) or "@context" not in data or "@type" not in data:
                resultat["alertes"].append({
                    "categorie": "jsonld-incomplet",
                    "gravite": "basse",
                    "titre": f"{nom} : bloc JSON-LD #{i+1} sans @context/@type",
                    "detail": "JSON valide mais probablement pas exploitable par Google tel quel.",
                })

    print(f"{n_pages} page(s), {n_blocs} bloc(s) JSON-LD, {n_sans_bloc} page(s) sans aucun bloc.")
    print(f"{len(resultat['alertes'])} alerte(s).")
    for a in resultat["alertes"][:15]:
        print(f"  [{a['gravite']}] {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
