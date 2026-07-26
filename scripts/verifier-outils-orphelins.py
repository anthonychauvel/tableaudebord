#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-OUTILS-ORPHELINS.PY — les 105 outils sont-ils tous atteignables, et
rien de plus ?

Deux sens de vérification, pas un seul :
  - une clé du TOOLS de outils.html sans fichier correspondant -> un lien mort,
    l'utilisateur tombe sur une 404 au clic ;
  - un fichier outils/module-xxx.html qui existe mais n'apparaît dans AUCUNE
    catégorie -> une page orpheline, jamais atteignable par personne, même
    pas par la recherche interne, alors qu'elle prend de la place et peut
    contenir du contenu obsolète qui traîne sans que rien ne le signale.

USAGE
    python3 verifier-outils-orphelins.py --hs /chemin/vers/hs --json sortie.json
"""
import argparse
import glob
import json
import os
import re


def cles_tools(html):
    i = html.find("const TOOLS")
    j = html.find("\nconst CATS", i)
    if i < 0 or j < 0:
        return set()
    return set(re.findall(r"'([\w-]+)':\s*\{", html[i:j]))


def cles_categorisees(html):
    """Union de tous les ids référencés dans les catégories (CATS[...].ids)."""
    i = html.find("const CATS")
    j = html.find("\n\n/* ===== ICÔNES", i)
    if j < 0:
        j = html.find("const SVGP", i)
    if i < 0 or j < 0:
        return set()
    return set(re.findall(r"'([\w-]+)'", html[i:j]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True, help="Racine du dépôt de l'application")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    chemin_outils_html = os.path.join(args.hs, "outils.html")
    html = open(chemin_outils_html, encoding="utf-8", errors="replace").read()

    cles = cles_tools(html)
    categorisees = cles_categorisees(html)

    fichiers_reels = set()
    for p in glob.glob(os.path.join(args.hs, "outils", "*.html")):
        nom = os.path.splitext(os.path.basename(p))[0]
        if nom.startswith("module-") or nom == "module8":
            fichiers_reels.add(nom)

    resultat = {"module": "outils-orphelins", "alertes": []}

    # Clé déclarée dans TOOLS mais fichier absent -> lien mort au clic.
    for cle in sorted(cles - fichiers_reels):
        resultat["alertes"].append({
            "categorie": "outil-fichier-manquant",
            "gravite": "haute",
            "titre": f"{cle} : référencé dans outils.html, fichier introuvable",
            "detail": f"outils/{cle}.html n'existe pas — 404 garantie au clic.",
        })

    # Fichier réel mais absent de TOUTES les catégories -> orphelin, invisible.
    for cle in sorted(fichiers_reels - categorisees):
        resultat["alertes"].append({
            "categorie": "outil-orphelin",
            "gravite": "basse",
            "titre": f"{cle} : le fichier existe, mais n'apparaît dans aucune catégorie",
            "detail": "Personne ne peut l'atteindre par la navigation normale, "
                      "même pas par la recherche interne.",
        })

    print(f"{len(fichiers_reels)} fichier(s) réel(s), {len(cles)} clé(s) déclarée(s) dans TOOLS.")
    print(f"{len(resultat['alertes'])} alerte(s).")
    for a in resultat["alertes"]:
        print(f"  [{a['gravite']}] {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
