#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-CITATIONS-ECOSYSTEME.PY — le guide et les 8 modules citent-ils des
articles réels, encore en vigueur ?

verifier-outils.py fait déjà ce travail pour les 105 outils, via le mécanisme
structuré data-art/SH.art() qui connaît le CODE (travail ou sécu) de chaque
article grâce à articles-loi.js. Le guide et les 8 modules ne passent PAS par
ce mécanisme : ils citent en texte brut, au fil du contenu ("article
L1237-1-1"). Sans code explicite, ce script teste les DEUX corpus du fonds
(code du travail, code de la sécu) et retient celui qui répond.

Ce script ne duplique donc pas verifier-outils.py : il couvre exactement ce
que celui-ci ne peut pas voir — le croisement pour le reste de l'écosystème.

USAGE
    python3 verifier-citations-ecosysteme.py --guide /chemin/Guide --hs /chemin/hs --fonds /chemin/droit --json sortie.json
"""
import argparse
import glob
import json
import os
import re

CIT_TEXTE = re.compile(r"\b([LRD]\d{3,4}-\d{1,3}(?:-\d+)?)\b")

def decouvrir_modules(racine_hs):
    """Un dossier à la racine de l'app avec un index.html EST un module --
    sauf GrillePaye, la seule exception connue. Pas de liste à tenir à jour :
    un nouveau module (dossier + index.html) apparaît tout seul au run
    suivant. taiko.html s'ajoute à part, un fichier racine plutôt qu'un
    dossier -- inclus seulement s'il existe (pas encore déployé partout).
    """
    EXCLUS = {"GrillePaye"}
    modules = {}
    for nom in sorted(os.listdir(racine_hs)):
        chemin_dossier = os.path.join(racine_hs, nom)
        if nom in EXCLUS or not os.path.isdir(chemin_dossier):
            continue
        chemin_index = os.path.join(nom, "index.html")
        if os.path.isfile(os.path.join(racine_hs, chemin_index)):
            modules[nom] = chemin_index
    if os.path.isfile(os.path.join(racine_hs, "taiko.html")):
        modules["taiko"] = "taiko.html"
    return modules


def citations_fichier(chemin):
    if not os.path.isfile(chemin):
        return set()
    s = open(chemin, encoding="utf-8", errors="replace").read()
    return set(CIT_TEXTE.findall(s))


def etat_reel(fonds, num):
    """Teste code-travail PUIS code-secu (pas de code explicite ici, contrairement
    aux outils). Renvoie (code_trouve, etat)."""
    for sous_dossier, code in (("code-travail", "CT"), ("code-secu", "CSS")):
        chemin = os.path.join(fonds, "output", sous_dossier, num + ".json")
        if not os.path.isfile(chemin):
            continue
        try:
            d = json.load(open(chemin, encoding="utf-8"))
        except Exception:
            continue
        art = d.get("article")
        if art is None:
            continue  # tenté par le fonds, rien d'exploitable -- on regarde l'autre corpus
        return code, (art.get("etat") or "etat-vide")
    return None, "jamais-tente"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guide", help="Racine du dépôt Guide (optionnel)")
    ap.add_argument("--hs", required=True, help="Racine du dépôt de l'application")
    ap.add_argument("--fonds", required=True, help="Racine du dépôt droit (le fonds)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    # {article: [(lieu, fichier), ...]}
    citations = {}
    n_pages_guide = 0

    for nom, rel in decouvrir_modules(args.hs).items():
        chemin = os.path.join(args.hs, rel)
        for art in citations_fichier(chemin):
            citations.setdefault(art, []).append(("module", nom))

    if args.guide:
        for chemin in glob.glob(os.path.join(args.guide, "*.html")):
            n_pages_guide += 1
            nom = os.path.basename(chemin)
            for art in citations_fichier(chemin):
                citations.setdefault(art, []).append(("guide", nom))

    resultat = {"module": "citations-ecosysteme", "alertes": []}
    abroges, non_confirmes = [], []

    # Même principe que dans verifier-outils.py : des citations vérifiées par
    # une recherche externe, que ce script ne peut structurellement pas
    # confirmer -- mauvais code testé, contenu vide côté fonds, ou citées à
    # dessein pour leur historique (un article abrogé, mentionné pour
    # expliquer ce qui l'a remplacé, reste une citation correcte).
    EXCEPTIONS_CONFIRMEES = {
        "D351-1-5": "Confirmé en vigueur (CSS) -- contenu vide côté fonds, pas une absence réelle.",
        "L113-9": "Code de la propriété intellectuelle -- hors périmètre CT/CSS.",
        "L211-23": "Explicitement \"CT-Lux\" dans la page -- droit luxembourgeois, jamais un code français.",
        "L2123-2": "Code général des collectivités territoriales -- hors périmètre CT/CSS.",
        "L2323-47": "Abrogé en 2017 (CSE) -- cité à dessein pour expliquer l'historique, contexte déjà ajouté dans le guide.",
        "L351-15": "Abrogé en 2023 (réforme retraites) -- cité à dessein pour l'historique, contexte déjà ajouté dans le guide.",
        "L461-1": "Confirmé en vigueur (CSS) -- contenu vide côté fonds, pas une absence réelle.",
        "L8222-2": "Confirmé en vigueur (CT) -- contenu vide côté fonds, pas une absence réelle.",
        "R3324-22": "Confirmé en vigueur (CT) -- contenu vide côté fonds, pas une absence réelle.",
    }

    for art, lieux in sorted(citations.items()):
        if art in EXCEPTIONS_CONFIRMEES:
            continue
        code, etat = etat_reel(args.fonds, art)
        lieux_uniques = sorted(set(lieux))
        if etat == "ABROGE":
            abroges.append((art, code, lieux_uniques))
        elif etat not in ("VIGUEUR",):
            non_confirmes.append((art, code, etat, lieux_uniques))

    def resume_lieux(lieux, n=3):
        txt = ", ".join(f"{typ}:{nom}" for typ, nom in lieux[:n])
        if len(lieux) > n:
            txt += f" et {len(lieux)-n} autre(s)"
        return txt

    for art, code, lieux in abroges:
        resultat["alertes"].append({
            "categorie": "article-abroge-ecosysteme",
            "gravite": "haute",
            "titre": f"{art} ({code}) : abrogé, cité comme en vigueur",
            "detail": f"Cité dans {resume_lieux(lieux)} — la loi a changé, ce texte ne s'applique plus.",
        })
    for art, code, etat, lieux in non_confirmes:
        raison = ("aucun des deux corpus (travail/sécu) ne le confirme"
                   if code is None else f"état « {etat} »")
        resultat["alertes"].append({
            "categorie": "citation-ecosysteme-non-confirmee",
            "gravite": "basse",
            "titre": f"{art} : {raison}",
            "detail": f"Cité dans {resume_lieux(lieux)}.",
        })

    print(f"{n_pages_guide} page(s) de guide + 8 modules parcourus, "
          f"{len(citations)} article(s) distinct(s) cité(s) en texte brut.")
    print(f"  {len(abroges)} abrogé(s)")
    print(f"  {len(non_confirmes)} non confirmé(s)")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
