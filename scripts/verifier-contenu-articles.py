#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-CONTENU-ARTICLES.PY — un article cité a-t-il changé de CONTENU
depuis la dernière vérification, même sans être abrogé ?

Le trou signalé : verifier-outils.py et verifier-citations-ecosysteme.py
regardent si un article existe encore et n'est pas abrogé -- jamais si son
TEXTE a changé. Une loi peut être amendée (seuils, montants, formulation)
tout en restant "en vigueur" du premier au dernier jour. Dans ce cas, aucun
des deux autres scripts ne verrait de problème, alors que la logique de
calcul de l'app pourrait reposer sur une version du texte qui n'est plus
la bonne.

Principe : à chaque run, pour chaque article actuellement cité quelque part
(outils, guide, modules), on relève trois signaux depuis le fonds --
versionArticle, dateDebut, et un hash du texte -- et on les compare à ce
qu'on avait relevé la dernière fois. Un empreinte gardée dans
empreintes-articles.json, jamais dans donnees.json (qui, lui, est
entièrement régénéré à chaque run).

Premier run pour un article donné : on enregistre l'empreinte de départ,
sans alerter -- comparer à du vide flagrait chaque article comme "changé"
à tort, exactement le même piège que pour les alertes "nouveau".

USAGE
    python3 verifier-contenu-articles.py --hs /chemin/hs --guide /chemin/Guide --fonds /chemin/droit --empreintes /chemin/empreintes-articles.json --json sortie.json
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys


def charger_module(nom_fichier):
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), nom_fichier)
    spec = importlib.util.spec_from_file_location(nom_fichier[:-3].replace("-", "_"), chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def empreinte_article(fonds, code, num):
    """Renvoie (version, dateDebut, hash_texte) ou None si l'article est
    introuvable dans le corpus indiqué."""
    sous_dossier = "code-secu" if code == "CSS" else "code-travail"
    chemin = os.path.join(fonds, "output", sous_dossier, num + ".json")
    if not os.path.isfile(chemin):
        return None
    try:
        d = json.load(open(chemin, encoding="utf-8"))
    except Exception:
        return None
    art = d.get("article")
    if not art:
        return None
    texte = (art.get("texte") or "") + (art.get("nota") or "")
    h = hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]
    return {
        "version": art.get("versionArticle"),
        "dateDebut": art.get("dateDebut"),
        "hash": h,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--guide", help="optionnel")
    ap.add_argument("--fonds", required=True)
    ap.add_argument("--empreintes", required=True,
                     help="Fichier persistant qui garde l'empreinte de chaque article d'un run à l'autre")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    vo = charger_module("verifier-outils.py")
    vce = charger_module("verifier-citations-ecosysteme.py")

    # Citations des outils : code explicite, connu via articles-loi.js.
    table_codes = vo.charger_articles_locaux(args.hs)
    citations_outils, _ = vo.citations_dans_outils(args.hs)

    # Citations du guide + des 8 modules : pas de code explicite, on teste
    # les deux corpus (comme verifier-citations-ecosysteme.py le fait déjà).
    citations_texte_brut = {}
    for nom, rel in vce.decouvrir_modules(args.hs).items():
        chemin = os.path.join(args.hs, rel)
        for art in vce.citations_fichier(chemin):
            citations_texte_brut.setdefault(art, []).append(("module", nom))
    if args.guide:
        import glob
        for chemin in glob.glob(os.path.join(args.guide, "*.html")):
            for art in vce.citations_fichier(chemin):
                citations_texte_brut.setdefault(art, []).append(("guide", os.path.basename(chemin)))

    # Empreintes précédentes.
    empreintes_avant = {}
    if os.path.isfile(args.empreintes):
        try:
            empreintes_avant = json.load(open(args.empreintes, encoding="utf-8"))
        except Exception as e:
            print(f"empreintes-articles.json illisible, traité comme premier run : {e}", file=sys.stderr)

    empreintes_apres = {}
    resultat = {"module": "contenu-articles", "alertes": []}
    n_verifies, n_premiere_fois = 0, 0

    def traiter(cle, code, num, lieux):
        nonlocal n_verifies, n_premiere_fois
        empr = empreinte_article(args.fonds, code, num)
        if empr is None:
            return
        n_verifies += 1
        empreintes_apres[cle] = empr
        avant = empreintes_avant.get(cle)
        if avant is None:
            n_premiere_fois += 1
            return
        a_change = (avant.get("hash") != empr["hash"]
                    or avant.get("version") != empr["version"]
                    or avant.get("dateDebut") != empr["dateDebut"])
        if a_change:
            lieux_txt = ", ".join(f"{t}:{n}" for t, n in lieux[:3])
            lien = f"https://monlegitexte.heuressupfrance.workers.dev/?art={num}"
            if code == "CSS":
                lien += "&code=secu"
            resultat["alertes"].append({
                "categorie": "contenu-article-modifie",
                "gravite": "moyenne",
                "titre": f"{num} ({code}) : le texte a changé depuis la dernière vérification",
                "detail": f"Toujours en vigueur, mais le contenu diffère de la dernière empreinte "
                          f"(version {avant.get('version')} -> {empr['version']}). "
                          f"Cité dans {lieux_txt} — à relire pour vérifier l'impact sur les calculs.",
                "lien": lien,
            })

    # Fusionner les DEUX sources par clé (code:num) AVANT de traiter -- un
    # article cité à la fois par un outil et par le guide ne doit être
    # vérifié et alerté qu'UNE fois, avec tous ses lieux réunis.
    a_traiter = {}  # cle -> (code, num, [lieux])
    for num, code in table_codes.items():
        if num in citations_outils:
            cle = f"{code}:{num}"
            a_traiter.setdefault(cle, (code, num, []))[2].extend(
                ("outil", f) for f in citations_outils[num])

    for num, lieux in citations_texte_brut.items():
        for code in ("CT", "CSS"):
            cle = f"{code}:{num}"
            if cle in a_traiter:
                a_traiter[cle][2].extend(lieux)
                break
            if empreinte_article(args.fonds, code, num) is not None:
                a_traiter[cle] = (code, num, list(lieux))
                break

    for cle, (code, num, lieux) in a_traiter.items():
        traiter(cle, code, num, lieux)

    with open(args.empreintes, "w", encoding="utf-8") as f:
        json.dump(empreintes_apres, f, ensure_ascii=False, indent=2)

    print(f"{n_verifies} article(s) vérifié(s) ({n_premiere_fois} pour la première fois -- "
          f"empreinte enregistrée, pas d'alerte).")
    print(f"{len(resultat['alertes'])} alerte(s) de contenu modifié.")
    for a in resultat["alertes"]:
        print(f"  {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
