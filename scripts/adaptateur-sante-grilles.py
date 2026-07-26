#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADAPTATEUR-SANTE-GRILLES.PY — sortie JSON pour verifier-grilles.py

Contrairement à verifier-fraicheur.py, verifier-grilles.py n'a pas de
fonctions séparées réutilisables : toute sa logique vit dans main(). Plutôt
que de le refactoriser (risque de régression sur un script déjà déployé et
testé), on le lance en sous-processus et on parse son propre markdown — les
titres de section (##) et les puces sont stables, c'est un contrat suffisant.

Couvre ce que le premier lot du tableau de bord avait oublié de brancher :
liens morts vers MonLegiTexte, grilles sous le SMIC, grilles vieilles de plus
de 18 mois, grilles encore en placeholder.

USAGE
    python3 adaptateur-sante-grilles.py --racine /chemin/vers/hs --idcc-suivis /chemin/vers/droit/idcc_list.txt --json sortie.json
"""
import argparse
import json
import os
import re
import subprocess
import sys


def lancer_original(racine, idcc_suivis):
    ici = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(ici, "verifier-grilles.py")
    cmd = [sys.executable, script, "--racine", racine]
    if idcc_suivis:
        cmd += ["--idcc-suivis", idcc_suivis]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout


def section(md, titre_motif):
    """Isole le contenu d'une section ## jusqu'au prochain ## ou la fin."""
    m = re.search(titre_motif + r"\n(.*?)(?=\n## |\Z)", md, re.S)
    return m.group(1).strip() if m else None


def puces(bloc):
    lignes = re.findall(r"^-\s+(.+)$", bloc, re.M)
    # Les ** de mise en forme markdown peuvent apparaître n'importe où dans la
    # ligne (ex. "**IDCC 675**" — l'emphase ne couvre que le numéro, pas toute
    # la ligne). Un simple ancrage début/fin les aurait laissés au milieu.
    return [l.replace("**", "").strip() for l in lignes]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=".")
    ap.add_argument("--idcc-suivis", help="idcc_list.txt du fonds, pour les liens morts")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    md = lancer_original(args.racine, args.idcc_suivis)
    resultat = {"module": "sante-grilles", "alertes": []}

    # Liens morts : la seule chose ici qui est un vrai bug, pas un fait métier.
    liens_morts = section(md, r"## ⚠️ (\d+) lien\(s\) vers un texte absent du fonds")
    m = re.search(r"## ⚠️ (\d+) lien\(s\) vers un texte absent du fonds", md)
    if m and int(m.group(1)) > 0:
        for ligne in puces(liens_morts or ""):
            resultat["alertes"].append({
                "categorie": "lien-mort-grillepaye",
                "gravite": "haute",
                "titre": "Lien vers un texte absent du fonds",
                "detail": ligne[:140],
            })

    # Grilles réelles sous le SMIC : informationnel — la branche n'a pas
    # renégocié, ce n'est pas une erreur de notre côté. Gravité basse.
    bloc = section(md, r"## ⚠️ \d+ grille\(s\) réelle\(s\) sous le SMIC")
    if bloc:
        for ligne in puces(bloc):
            if ligne.startswith("IDCC"):
                resultat["alertes"].append({
                    "categorie": "grille-sous-smic",
                    "gravite": "basse",
                    "titre": ligne.split(" : ")[0],
                    "detail": "Réelle et sourcée, mais sous le SMIC — la branche n'a pas "
                              "renégocié. Rien à corriger, le SMIC prime automatiquement.",
                })

    # Grilles anciennes : mérite un coup d'œil, sans urgence.
    bloc = section(md, r"## \d+ grille\(s\) non mises à jour depuis plus de \d+ mois")
    if bloc:
        for ligne in puces(bloc):
            resultat["alertes"].append({
                "categorie": "grille-ancienne",
                "gravite": "basse",
                "titre": ligne.split(" : ")[0] if " : " in ligne else ligne[:40],
                "detail": ligne,
            })

    # Placeholders : la vraie liste de travail déjà identifiée précédemment.
    bloc = section(md, r"## \d+ grille\(s\) encore en placeholder")
    if bloc:
        codes = re.findall(r"IDCC \d+", bloc)
        if codes:
            resultat["alertes"].append({
                "categorie": "grilles-placeholder",
                "gravite": "moyenne",
                "titre": f"{len(codes)} grille(s) en placeholder, contenu à sourcer",
                "detail": ", ".join(codes),
            })

    print(f"{len(resultat['alertes'])} alerte(s) santé des grilles.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
