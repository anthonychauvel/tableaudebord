#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-GUIDE.PY — le guide cite-t-il une convention fusionnée sans le dire ?

Ce contrôle prolonge une vérification déjà faite manuellement le 23/07 : sur
181 IDCC cités dans le guide, 18 conventions fusionnées sur 20 étaient déjà
correctement présentées comme historiques, et 2 pages avaient été identifiées
comme à corriger (IDCC 800 « hôtellerie-chaîne », IDCC 1314 « alimentation
succursales »). Ce script généralise ce contrôle ponctuel pour qu'il tourne
seul à chaque run, au lieu de nécessiter une relecture manuelle.

MÉTHODE
Un IDCC est considéré "à risque" s'il apparaît dans CCN_FUSIONS (GrillePaye) —
donc officiellement repris par une autre convention. La page est flaggée SEULE-
MENT si elle ne contient AUCUN mot du champ lexical "c'est du passé" à proximité
(fusion, historique, repris, n'existe plus, a cessé). Ce n'est pas une preuve
formelle que le contexte est correct, juste un signal : "cette page mérite une
relecture", pas "cette page est fautive".

USAGE
    python3 verifier-guide.py --guide /chemin/vers/Guide --hs /chemin/vers/hs --json sortie.json
"""
import argparse
import glob
import json
import os
import re

CIT_IDCC = re.compile(r"IDCC\s+(?:n°\s*)?(\d{2,5})")
MENTION_HISTORIQUE = re.compile(
    r"fusion|repris par|historique|n'existe plus|a cess[ée]|"
    r"ancienne convention|convention abrog[ée]e|ne s'applique plus|"
    r"absorb[ée]e?",
    re.I)


def charger_fusions(racine_hs):
    chemin = os.path.join(racine_hs, "GrillePaye", "index.html")
    s = open(chemin, encoding="utf-8", errors="replace").read()
    m = re.search(r"const CCN_FUSIONS=(\{.*?\});", s, re.S)
    return json.loads(m.group(1)) if m else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guide", required=True, help="Racine du dépôt Guide")
    ap.add_argument("--hs", required=True, help="Racine du dépôt de l'application (pour CCN_FUSIONS)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    fusions = charger_fusions(args.hs)
    resultat = {"module": "guide-seo", "alertes": []}

    pages = glob.glob(os.path.join(args.guide, "*.html"))
    n_avec_idcc = 0
    a_verifier = []

    for chemin in pages:
        s = open(chemin, encoding="utf-8", errors="replace").read()
        cites = set(CIT_IDCC.findall(s))
        if not cites:
            continue
        n_avec_idcc += 1
        for idcc in cites:
            if idcc in fusions and not MENTION_HISTORIQUE.search(s):
                nom_repreneur = fusions[idcc][1]
                a_verifier.append((os.path.basename(chemin), idcc, nom_repreneur))

    for fichier, idcc, repreneur in sorted(a_verifier):
        resultat["alertes"].append({
            "categorie": "convention-perimee-sans-mention",
            "gravite": "moyenne",
            "titre": f"{fichier} : cite IDCC {idcc}, fusionnée, sans le dire",
            "detail": f"Reprise par « {repreneur} ». Aucun mot du champ "
                      f"fusion/historique/repris trouvé sur la page — probablement "
                      f"présentée comme active alors qu'elle ne l'est plus.",
        })

    print(f"{len(pages)} pages, {n_avec_idcc} citent au moins un IDCC.")
    print(f"{len(a_verifier)} page(s) à vérifier (convention fusionnée, sans mention historique).")
    for a in resultat["alertes"]:
        print(f"  [{a['gravite']}] {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"\nÉcrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
