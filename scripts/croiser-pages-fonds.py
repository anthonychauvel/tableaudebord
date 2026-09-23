#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CROISER-PAGES-FONDS.PY — les articles VISIBLES à l'écran existent-ils encore ?
(complément de verifier-pages.py, 22/09/2026)

verifier-citations-ecosysteme.py lit le CODE SOURCE : tout ce qui est écrit en
dur dans un .html ou un .js. Il ne peut pas voir un article assemblé au dernier
moment par du JavaScript (numéro construit par morceaux, choisi selon la
convention de l'utilisateur, injecté depuis une donnée). verifier-pages.py, lui,
ouvre chaque page pour de vrai et relève ce que l'utilisateur LIT vraiment :
c'est cette liste (pages-articles.json) qu'on croise ici avec le fonds.

Deux façons de voir la même chose, donc, mais pas le même angle : la première
couvre le code, la seconde couvre l'écran. Un article qui n'apparaît que dans
la seconde est exactement celui qu'aucun contrôle ne voyait jusqu'ici.

RÉUTILISE verifier-citations-ecosysteme.py plutôt que de refaire sa logique :
mêmes fonctions de lecture du fonds (etat_reel : code du travail puis code de
la sécu), mêmes codes hors périmètre, mêmes exceptions déjà confirmées à la
main. Rien à tenir à jour en double.

USAGE
    python3 croiser-pages-fonds.py --articles ../pages-articles.json \
        --hs ../_hs --fonds ../_droit --json sortie.json
"""
import argparse
import ast
import importlib.util
import json
import os
import re


def charger_module(chemin):
    spec = importlib.util.spec_from_file_location("verif_citations", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def exceptions_confirmees(chemin):
    """Les exceptions vivent dans le main() de verifier-citations-ecosysteme.py :
    on lit le dictionnaire dans le fichier plutôt que d'en garder une copie ici,
    qui aurait divergé au premier ajout."""
    try:
        s = open(chemin, encoding="utf-8").read()
        m = re.search(r"EXCEPTIONS_CONFIRMEES\s*=\s*(\{.*?\n\s*\})", s, re.S)
        return ast.literal_eval(m.group(1)) if m else {}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--articles", required=True, help="pages-articles.json écrit par verifier-pages.py")
    ap.add_argument("--hs", required=True)
    ap.add_argument("--guide", help="Racine du dépôt Guide (pour ne pas redire ce que le contrôle du code source dit déjà)")
    ap.add_argument("--fonds", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    resultat = {"module": "pages-fonds", "alertes": []}
    if not os.path.isfile(args.articles):
        print("pages-articles.json absent : les pages n'ont pas été ouvertes (Playwright manquant ?).")
        if args.json:
            json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0

    ici = os.path.dirname(os.path.abspath(__file__))
    chemin_vc = os.path.join(ici, "verifier-citations-ecosysteme.py")
    vc = charger_module(chemin_vc)
    exceptions = exceptions_confirmees(chemin_vc)
    declares = vc.codes_declares(args.hs)

    data = json.load(open(args.articles, encoding="utf-8"))
    pages = data.get("pages", {})
    ou = {}                       # article -> pages où il est lisible
    for page, arts in pages.items():
        for a in arts:
            ou.setdefault(a, []).append(page)

    # Ce que verifier-citations-ecosysteme.py voit déjà dans le code source :
    # inutile de le répéter ici. On ne garde que ce qui n'existe QU'à l'écran,
    # c'est-à-dire ce qu'aucun contrôle ne voyait avant.
    try:
        deja, _ = vc.citations_ecosysteme(args.hs, args.guide)
    except Exception as e:
        print(f"citations du code source illisibles ({e}) : on croise tout.")
        deja = {}

    abroges, non_confirmes, hors, connus = [], [], [], 0
    for art in sorted(ou):
        if art in exceptions:
            continue
        if art in deja:
            connus += 1
            continue
        if declares.get(art) in vc.CODES_HORS_PERIMETRE:
            hors.append(art)
            continue
        code, etat = vc.etat_reel(args.fonds, art)
        if etat == "ABROGE":
            abroges.append((art, code, sorted(ou[art])))
        elif etat != "VIGUEUR":
            non_confirmes.append((art, code, etat, sorted(ou[art])))

    def resume(lieux, n=3):
        txt = ", ".join(lieux[:n])
        return f"{len(lieux)} pages, dont {txt}" if len(lieux) > n else txt

    for art, code, lieux in abroges:
        resultat["alertes"].append({
            "categorie": "article-abroge-ecosysteme",
            "gravite": "haute",
            "titre": f"{art} ({code}) : abrogé, mais affiché à l'écran",
            "detail": (f"Vu à l'écran, une fois le JavaScript exécuté, dans {resume(lieux)}. "
                       "La loi a changé : ce texte ne s'applique plus."),
        })
    for art, code, etat, lieux in non_confirmes:
        raison = ("aucun des deux corpus (travail/sécu) ne le confirme"
                  if code is None else f"état « {etat} »")
        resultat["alertes"].append({
            "categorie": "citation-ecosysteme-non-confirmee",
            "gravite": "basse",
            "titre": f"{art} : {raison} (vu à l'écran)",
            "detail": f"Lisible dans {resume(lieux)} après exécution du JavaScript.",
        })

    print(f"{len(pages)} page(s) avec citations, {len(ou)} article(s) distinct(s) lisibles à l'écran "
          f"({connus} déjà vus dans le code source, laissés à verifier-citations-ecosysteme.py).")
    print(f"  {len(abroges)} abrogé(s), {len(non_confirmes)} non confirmé(s)"
          + (f", {len(hors)} hors périmètre du fonds" if hors else ""))
    if args.json:
        json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
