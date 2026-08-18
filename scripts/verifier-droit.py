#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-DROIT.PY — lit les audits déjà produits par le fonds (5 sources)

Ce script ne refait AUCUN diff lui-même : chaque workflow du fonds "droit"
compare déjà le commit courant au précédent et écrit le résultat dans SON
PROPRE fichier d'audit. Reproduire ce diff ici demanderait un historique git
complet (le clone superficiel utilisé pour les autres contrôles n'en a pas)
pour, au final, refaire un travail déjà fait et déjà fiable.

Ce script se contente donc de lire le dernier run de CHAQUE source et d'en
tirer ce qui mérite une alerte :
  - un run a-t-il eu lieu récemment (chaque source a son propre rythme) ?
  - le dernier run a-t-il trouvé un VRAI changement (pas du simple
    rattrapage/routine) ? C'est la seule distinction qui compte.

SOURCES (18/08/2026 — le fonds a grandi au-delà du seul aspirateur France) :
  - index.json                       : aspirateur principal (lundi/jeudi)
  - index-oit.json                   : OIT, texte JORF (vendredi)
  - index-cedh.json                  : CEDH, texte HUDOC (mercredi)
  - index-cgfp-civil-penal.json      : CGFP + Code civil/pénal (vendredi)
  - index-combler-manques.json       : fiches minimales, tous corpus (samedi)

Chaque nouvelle source écrit son entrée via ecrire_audit.py (dans le fonds
droit) -- champ "changements_droit", alors que l'aspirateur principal utilise
"total_changements". Les deux noms sont vérifiés ici (comme le fait déjà
index.html côté appli) plutôt que d'imposer un seul nom.

USAGE
    python3 verifier-droit.py --fonds /chemin/vers/droit --json sortie.json
"""
import argparse
import json
import os
from datetime import datetime, timezone

# (nom_fichier, label humain, cadence normale en jours, marge avant alerte)
SOURCES = [
    ("index.json",                  "Aspirateur principal (France)",        3,  5),
    ("index-oit.json",              "OIT",                                  7,  12),
    ("index-cedh.json",             "CEDH",                                 7,  12),
    ("index-cgfp-civil-penal.json", "CGFP + Code civil/pénal",              7,  12),
    ("index-combler-manques.json",  "Comblement des manques",               7,  12),
]


def nombre_changements(entree):
    """Vérifie les deux noms de champ possibles selon la source qui a écrit
    l'entrée -- l'aspirateur principal utilise total_changements,
    ecrire_audit.py (utilisé par les 4 nouvelles sources) utilise
    changements_droit. Même logique défensive que _majSansChangement() côté
    appli (index.html), pour ne pas imposer un seul nom aux deux générateurs."""
    if isinstance(entree.get("changements_droit"), (int, float)):
        return int(entree["changements_droit"])
    return int(entree.get("total_changements", 0) or 0)


def verifier_source(dossier_audits, nom_fichier, label, cadence_jours, marge_jours, alertes):
    chemin = os.path.join(dossier_audits, nom_fichier)
    if not os.path.isfile(chemin):
        print(f"[{label}] {nom_fichier} absent -- ce workflow n'a peut-être "
              f"jamais tourné, ou pas encore poussé son 1er audit.")
        return

    try:
        runs = json.load(open(chemin, encoding="utf-8"))
    except Exception as e:
        alertes.append({
            "categorie": "audit-illisible",
            "gravite": "moyenne",
            "titre": f"[{label}] Fichier d'audit illisible",
            "detail": f"« {chemin} » n'a pas pu être lu comme JSON valide ({e}).",
        })
        return

    if not runs:
        print(f"[{label}] {nom_fichier} vide -- aucun run enregistré.")
        return

    dernier = runs[0]
    print(f"[{label}] Dernier run : {dernier.get('date','?')} {dernier.get('heure','')}")
    print(f"  {dernier.get('resume','')}")

    try:
        d = datetime.strptime(dernier["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age_jours = (datetime.now(timezone.utc) - d).days
    except Exception:
        age_jours = None

    if age_jours is not None and age_jours > marge_jours:
        alertes.append({
            "categorie": "run-en-retard",
            "gravite": "moyenne",
            "titre": f"[{label}] Dernier run vieux de {age_jours} jours",
            "detail": f"Cadence normale : environ tous les {cadence_jours} jours. "
                      f"{age_jours} jours sans run suggère un cycle manqué ou le "
                      f"workflow en échec silencieux.",
        })

    total = nombre_changements(dernier)
    if total > 0:
        alertes.append({
            "categorie": "changement-reel",
            "gravite": "haute",
            "titre": f"[{label}] {total} changement(s) réel(s) détecté(s)",
            "detail": f"Run du {dernier.get('date','?')} {dernier.get('heure','')} — voir "
                      f"audits/{dernier.get('fichier','?')} pour le détail. Ceci n'est pas "
                      f"du rattrapage : quelque chose a effectivement changé, à distinguer "
                      f"d'un simple complément de collecte.",
        })
    else:
        print(f"  Aucun changement réel signalé.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonds", required=True, help="Racine du dépôt droit (le fonds)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    resultat = {"module": "monlegitexte-droit", "alertes": []}
    dossier_audits = os.path.join(args.fonds, "audits")

    if not os.path.isdir(dossier_audits):
        resultat["alertes"].append({
            "categorie": "audit-introuvable",
            "gravite": "haute",
            "titre": "Aucun dossier d'audits trouvé",
            "detail": f"« {dossier_audits} » est absent. Le workflow aspirateur "
                      f"a-t-il déjà tourné au moins une fois sur ce dépôt ?",
        })
        print("dossier audits/ introuvable.")
        if args.json:
            json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0

    for nom_fichier, label, cadence, marge in SOURCES:
        verifier_source(dossier_audits, nom_fichier, label, cadence, marge, resultat["alertes"])
        print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
