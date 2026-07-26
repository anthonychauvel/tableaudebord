#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-SYNTAXE-JS.PY — une page qui ne charge pas du tout, pas juste une
donnée périmée.

Aucune des autres vérifications ne détecte ça : une virgule oubliée dans un
template literal, une accolade en trop, une chaîne mal fermée — le genre
d'erreur trouvée à la main, encore et encore, cette session (jusqu'à trois
fois sur le même fichier certains jours). Une page avec une erreur de syntaxe
JS ne casse pas juste une fonctionnalité : la page entière reste blanche.

Extrait chaque <script> inline (pas les scripts externes, déjà couverts par
leur propre historique git) et le fait passer par `node --check` — une
vérification de syntaxe pure, aucune exécution du code.

USAGE
    python3 verifier-syntaxe-js.py --hs /chemin/vers/hs --json sortie.json
"""
import argparse
import glob
import json
import os
import re
import subprocess
import tempfile

SCRIPT_INLINE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S | re.I)

# Fichiers à la racine de l'app, en plus des modules et des outils.
RACINE = ["index.html", "menu.html", "outils.html", "mentions-legales.html",
          "nouveautes.html", "privacy.html", "taiko.html"]
MODULES = ["heures/index.html", "paye/index.html", "fox/index.html",
           "module4/index.html", "module5/index.html", "module6/index.html",
           "module7/index.html"]
AUTRES = ["GrillePaye/index.html"]


def verifier_fichier(chemin):
    """Renvoie None si la syntaxe est valide, sinon le message d'erreur de node."""
    if not os.path.isfile(chemin):
        return None  # absence déjà couverte par verifier-modules.py, pas ici
    html = open(chemin, encoding="utf-8", errors="replace").read()
    scripts = SCRIPT_INLINE.findall(html)
    if not scripts:
        return None
    combine = "\n;\n".join(scripts)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False,
                                       encoding="utf-8") as f:
        f.write(combine)
        chemin_tmp = f.name
    try:
        r = subprocess.run(["node", "--check", chemin_tmp],
                            capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            # La ligne utile est celle qui commence par un type d'erreur JS
            # (SyntaxError, ReferenceError…) -- ni la première ni la dernière
            # ligne de la sortie de node, qui contiennent surtout du contexte
            # (extrait de code, numéro de version) sans intérêt ici.
            m = re.search(r"^(\w*Error: .+)$", r.stderr, re.M)
            return m.group(1) if m else (r.stderr.strip().splitlines() or ["erreur non détaillée"])[0]
        return None
    except subprocess.TimeoutExpired:
        return "délai dépassé (fichier trop gros ou boucle au parsing)"
    finally:
        os.unlink(chemin_tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True, help="Racine du dépôt de l'application")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    resultat = {"module": "syntaxe-js", "alertes": []}

    cibles = [(nom, "racine") for nom in RACINE]
    cibles += [(nom, "module") for nom in MODULES]
    cibles += [(nom, "app") for nom in AUTRES]
    cibles += [(os.path.relpath(p, args.hs), "outil")
               for p in sorted(glob.glob(os.path.join(args.hs, "outils", "*.html")))]

    n_verifies = 0
    for rel, categorie in cibles:
        chemin = os.path.join(args.hs, rel)
        if not os.path.isfile(chemin):
            continue
        n_verifies += 1
        erreur = verifier_fichier(chemin)
        if erreur:
            resultat["alertes"].append({
                "categorie": "syntaxe-js-cassee",
                "gravite": "haute",
                "titre": f"{rel} : la page ne charge pas du tout",
                "detail": erreur[:200],
            })

    print(f"{n_verifies} fichier(s) vérifié(s), {len(resultat['alertes'])} en erreur.")
    for a in resultat["alertes"]:
        print(f"  {a['titre']} — {a['detail']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
