#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTER-DROIT.PY — ouvrir un ticket GitHub quand le droit CITÉ a bougé.

POURQUOI CE SCRIPT ?
Le tableau de bord est muet. Il écrit donnees.json, commite, et attend qu'on
l'ouvre. Tant qu'il produisait 178 alertes dont 118 fausses, ça n'avait pas
d'importance : on l'ouvrait pour faire le tri. Maintenant qu'il est fiable, il
est silencieux presque tout le temps — et c'est précisément ce qui fait qu'on
arrête de l'ouvrir, juste avant le jour où il a quelque chose à dire.

GitHub sait notifier : un ticket ouvert dans un dépôt qu'on suit envoie un mail
et une notification sur l'app mobile, sans rien installer. Ce script décide
s'il faut en ouvrir un, et prépare son contenu.

CE QU'IL NE TICKETTE PAS
Uniquement le droit CITÉ par l'écosystème, c'est-à-dire les catégories listées
dans CATEGORIES ci-dessous. Volontairement absent :

  - changement-reel : le fonds a changé quelque part (17 articles du CGFP la
    semaine dernière). C'est une information sur le CORPUS, pas sur ce que
    l'application affiche. La ticketter reviendrait à être notifié chaque
    semaine pour du droit qu'on ne cite pas.
  - citation-ecosysteme-non-confirmee : gravité basse, le fonds n'a pas de
    fiche pour ce numéro. À examiner une fois, puis à basculer dans
    EXCEPTIONS_CONFIRMEES — ce n'est pas un événement.
  - tout ce qui touche aux grilles, aux liens, à la syntaxe : ça se voit en
    ouvrant le tableau, ça n'a pas à réveiller qui que ce soit.

Si tu veux en ajouter une, elle va dans CATEGORIES. Rien d'autre à changer.

USAGE
    python3 alerter-droit.py --donnees ../donnees.json --sortie /tmp/ticket.md
"""
import argparse
import json
import os
import sys

# Les seules catégories qui méritent de te déranger : un article que
# l'écosystème cite a changé de texte, ou a été abrogé alors qu'on le présente
# comme en vigueur.
CATEGORIES = {
    "contenu-article-modifie":   "Le texte a changé",
    "article-abroge-ecosysteme": "Abrogé, cité comme en vigueur",
    "article-abroge":            "Abrogé, cité comme en vigueur",
}

ORDRE = {"haute": 0, "moyenne": 1, "basse": 2}


def retenues(donnees):
    out = []
    for section in donnees.get("sections", []):
        for a in section.get("alertes", []):
            if a.get("categorie") in CATEGORIES:
                out.append(a)
    return sorted(out, key=lambda a: ORDRE.get(a.get("gravite"), 9))


def corps(alertes, depot, run_id, serveur):
    L = ["Le tableau de bord a détecté que du droit **cité par l'écosystème** a",
         "changé depuis le passage précédent.", ""]
    for a in alertes:
        L += [f"### {a.get('titre', '(sans titre)')}", ""]
        detail = (a.get("detail") or "").strip()
        if detail:
            L += [detail, ""]
        if a.get("lien"):
            L += [f"[Lire l'article sur MonLegiTexte]({a['lien']})", ""]
    L += ["---", ""]
    if run_id and depot and serveur:
        L.append(f"[Voir le run]({serveur}/{depot}/actions/runs/{run_id}) · "
                 f"le détail complet est dans `donnees.json`, et l'historique "
                 f"des textes dans `empreintes-articles.json`.")
    L += ["",
          "_Ce ticket ne se referme pas tout seul : un changement de droit est un",
          "événement qui demande une relecture, pas une panne qui se répare._"]
    return "\n".join(L)


def titre(alertes):
    if len(alertes) == 1:
        # « L3123-29 (CT) : le texte a changé depuis… » -> « L3123-29 (CT) »
        t = alertes[0].get("titre", "")
        return "Droit modifié — " + (t.split(" : ", 1)[0] if " : " in t else t)
    return f"Droit modifié — {len(alertes)} articles cités ont changé"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", required=True)
    ap.add_argument("--sortie", default="/tmp/ticket.md")
    args = ap.parse_args()

    try:
        donnees = json.load(open(args.donnees, encoding="utf-8"))
    except (OSError, ValueError) as e:
        # Pas de ticket plutôt qu'un ticket faux : si donnees.json est
        # illisible, le problème est ailleurs et le run l'aura déjà signalé.
        print(f"donnees.json illisible ({e}) — aucun ticket.", file=sys.stderr)
        donnees = {}

    alertes = retenues(donnees)
    if alertes:
        texte = corps(alertes,
                      os.environ.get("GITHUB_REPOSITORY", ""),
                      os.environ.get("GITHUB_RUN_ID", ""),
                      os.environ.get("GITHUB_SERVER_URL", "https://github.com"))
        with open(args.sortie, "w", encoding="utf-8") as f:
            f.write(texte)
        print(f"{len(alertes)} alerte(s) de droit cité — ticket à ouvrir.")
        for a in alertes:
            print("  " + a.get("titre", ""))
    else:
        print("Aucun changement du droit cité — pas de ticket.")

    sortie_gh = os.environ.get("GITHUB_OUTPUT")
    if sortie_gh:
        # Le format de GITHUB_OUTPUT est « clé=valeur » sur UNE ligne : un
        # retour à la ligne dans le titre couperait la valeur en deux et
        # casserait l'étape suivante. Le titre est aussi injecté dans une
        # commande shell, d'où le guillemet droit neutralisé.
        t = " ".join((titre(alertes) if alertes else "").split()).replace('"', "'")
        with open(sortie_gh, "a", encoding="utf-8") as f:
            f.write("alerte=%d\n" % (1 if alertes else 0))
            f.write("titre=%s\n" % t[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
