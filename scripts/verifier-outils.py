#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-OUTILS.PY — intégrité des citations d'articles dans les 105 outils

Deux niveaux de vérification pour chaque citation trouvée (data-art="…" et
SH.art()/SH.artLien() dans le code JS des pages) :

  1. INTERNE : l'article existe-t-il dans articles-loi.js (la table ARTICLES) ?
     S'il n'y est pas, la citation affichera un texte vide ou un repli — un
     bug immédiat et visible.

  2. RÉEL : d'après le fonds (droit), cet article est-il toujours EN VIGUEUR ?
     Un article peut très bien exister dans articles-loi.js — construit il y a
     des mois — alors que la loi l'a abrogé ou renuméroté depuis. C'est le
     seul des deux contrôles qui vieillit tout seul, silencieusement.

Ce script ne vérifie pas le contenu métier des outils (leurs calculs), seulement
que ce qu'ils citent comme fondement légal est réel et à jour.

USAGE
    python3 verifier-outils.py --racine /chemin/vers/hs --fonds /chemin/vers/droit --json sortie.json
"""
import argparse
import json
import os
import re
import sys

CIT_DATA_ART = re.compile(r'data-art="([^"]+)"')
CIT_SH_ART = re.compile(r"SH\.art(?:Lien)?\('([^']+)'\)")


def charger_articles_locaux(racine):
    """Table ARTICLES d'articles-loi.js : {num: {code, titre, texte}}."""
    chemin = os.path.join(racine, "outils", "articles-loi.js")
    if not os.path.isfile(chemin):
        return {}
    s = open(chemin, encoding="utf-8", errors="replace").read()
    i = s.find("var ARTICLES")
    if i < 0:
        return {}
    # Extraction ligne à ligne : plus robuste qu'un regex global sur un objet
    # JS non strictement JSON (guillemets simples, commentaires internes).
    table = {}
    for m in re.finditer(r"'([A-Z]?\d[\w-]*)':\s*\{\s*code:\s*'([A-Z]+)'", s[i:]):
        table[m.group(1)] = m.group(2)
    return table


def citations_dans_outils(racine):
    """Parcourt les 105 outils et collecte {article: [fichiers qui le citent]}."""
    dossier = os.path.join(racine, "outils")
    citations = {}
    n_fichiers = 0
    for nom in sorted(os.listdir(dossier)):
        if not nom.endswith(".html"):
            continue
        n_fichiers += 1
        chemin = os.path.join(dossier, nom)
        s = open(chemin, encoding="utf-8", errors="replace").read()
        trouves = set(m.group(1) for m in CIT_DATA_ART.finditer(s)) | \
                  set(m.group(1) for m in CIT_SH_ART.finditer(s))
        for art in trouves:
            citations.setdefault(art, []).append(nom)
    return citations, n_fichiers


def etat_reel(fonds, code, num):
    """Interroge le fonds : VIGUEUR / ABROGE / jamais tenté / échec de récupération.

    Un fichier peut exister sur disque tout en contenant `"article": null` —
    le fonds a bien tenté de le récupérer, mais Légifrance n'a rien renvoyé
    d'exploitable. C'est un signal plus concret qu'un simple "pas encore dans
    le corpus" : ça peut trahir un numéro d'article mal formé dans la citation
    elle-même, pas seulement un retard de collecte.
    """
    sous_dossier = "code-secu" if code == "CSS" else "code-travail"
    chemin = os.path.join(fonds, "output", sous_dossier, num + ".json")
    if not os.path.isfile(chemin):
        return "jamais-tente"
    try:
        d = json.load(open(chemin, encoding="utf-8"))
    except Exception:
        return "illisible"
    art = d.get("article")
    if art is None:
        return "echec-recuperation"
    return art.get("etat") or "etat-vide"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=".", help="Racine du dépôt de l'application")
    ap.add_argument("--fonds", required=True, help="Racine du dépôt droit (le fonds)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    articles_locaux = charger_articles_locaux(args.racine)
    citations, n_fichiers = citations_dans_outils(args.racine)

    resultat = {"module": "105-outils", "alertes": []}
    manquants_locaux, abroges, non_confirmes = [], [], []

    for art, fichiers in sorted(citations.items()):
        code = articles_locaux.get(art)
        if code is None:
            manquants_locaux.append((art, fichiers))
            continue
        etat = etat_reel(args.fonds, code, art)
        if etat == "ABROGE":
            abroges.append((art, code, fichiers))
        elif etat == "echec-recuperation":
            non_confirmes.append((art, code, "le fonds l'a tenté, Légifrance n'a rien renvoyé — "
                                              "vérifier que le numéro cité est correct", fichiers))
        elif etat == "jamais-tente":
            non_confirmes.append((art, code, "jamais demandé au fonds", fichiers))
        elif etat not in ("VIGUEUR",):
            non_confirmes.append((art, code, f"état « {etat} »", fichiers))

    for art, fichiers in manquants_locaux:
        resultat["alertes"].append({
            "categorie": "citation-orpheline",
            "gravite": "haute",
            "titre": f"{art} : cité mais absent d'articles-loi.js",
            "detail": f"Cité dans {', '.join(fichiers[:3])}"
                      f"{' et ' + str(len(fichiers)-3) + ' autre(s)' if len(fichiers) > 3 else ''} "
                      f"— la citation s'affichera vide.",
        })
    for art, code, fichiers in abroges:
        resultat["alertes"].append({
            "categorie": "article-abroge",
            "gravite": "haute",
            "titre": f"{art} ({code}) : abrogé selon le fonds",
            "detail": f"Cité comme en vigueur dans {', '.join(fichiers[:3])} — la loi a changé, "
                      f"le texte cité par l'outil ne s'applique plus.",
        })
    for art, code, raison, fichiers in non_confirmes:
        gravite = "moyenne" if "Légifrance n'a rien renvoyé" in raison else "basse"
        resultat["alertes"].append({
            "categorie": "article-non-confirme",
            "gravite": gravite,
            "titre": f"{art} ({code}) : {raison}",
            "detail": f"Cité dans {', '.join(fichiers[:3])}"
                      f"{' et ' + str(len(fichiers)-3) + ' autre(s)' if len(fichiers) > 3 else ''}.",
        })

    print(f"{n_fichiers} fichiers outils parcourus, {len(citations)} article(s) distinct(s) cité(s).")
    print(f"  {len(manquants_locaux)} absent(s) d'articles-loi.js")
    print(f"  {len(abroges)} abrogé(s) d'après le fonds")
    print(f"  {len(non_confirmes)} non confirmé(s) (pas dans le corpus du fonds)")
    for a in resultat["alertes"][:20]:
        print(f"  [{a['gravite']:<6}] {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"\nÉcrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
