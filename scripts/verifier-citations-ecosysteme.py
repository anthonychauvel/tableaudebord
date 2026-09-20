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


# Les commentaires ne sont pas des citations. outils/articles-loi.js ouvre sur
# 200 lignes de journal d'audit qui mentionnent des articles au passage
# ("FMD CORRIGÉ ... (Art. D3261-15-2 CT ; urssaf.fr)") : ces numéros ne sont
# affichés à personne. Les compter reviendrait à alerter sur les notes de
# maintenance. On les retire donc avant de chercher.
COMMENTAIRE_JS = re.compile(r"/\*.*?\*/|(?<![:\w])//[^\n]*", re.S)
COMMENTAIRE_HTML = re.compile(r"<!--.*?-->", re.S)


def citations_fichier_utiles(chemin):
    """Comme citations_fichier(), mais sans ce qui est en commentaire."""
    if not os.path.isfile(chemin):
        return set()
    s = open(chemin, encoding="utf-8", errors="replace").read()
    s = COMMENTAIRE_HTML.sub(" ", s)
    if chemin.endswith(".js"):
        s = COMMENTAIRE_JS.sub(" ", s)
    return set(CIT_TEXTE.findall(s))


# ── Parcours élargi ──────────────────────────────────────────────────────
#
# POURQUOI CETTE FONCTION S'AJOUTE À decouvrir_modules()
# decouvrir_modules() ne lit que le index.html de chaque module, et
# verifier-outils.py ne voit dans les outils que les citations STRUCTURÉES
# (data-art / SH.art). Tout ce qui est écrit dans un .js échappait donc aux
# deux : 157 articles cités nulle part ailleurs, mesurés le 20/09/2026.
#
#      61  fox/js/          (son registre d'articles + le moteur)
#      43  le JS des modules (module4/5/6/7…)
#      42  outils/articles-loi.js lui-même
#      38  outils/*.html, cités en toutes lettres et non via SH.art
#      24  legi-ref.js
#
# Les deux derniers sont les plus gênants : legi-ref.js fabrique les liens
# vers MonLegiTexte, et articles-loi.js porte les phrases d'explication. Ce
# sont précisément les fichiers où un article modifié fait le plus de dégâts.
#
# On parcourt donc TOUT le .html et le .js des deux dépôts. Le coût est nul
# (505 + 985 fichiers, une lecture chacun) et la liste s'entretient toute
# seule : un nouveau module, un nouvel outil ou une nouvelle page y entrent
# sans que personne ait à y penser.

# fox porte 165 définitions rédigées, lues à l'écran par l'utilisateur. Mettre
# ceci à False l'exclut du périmètre sans toucher au reste (53 articles ne sont
# alors plus surveillés du tout, ils ne sont cités que là).
INCLURE_FOX = True

EXTENSIONS = {"app": (".html", ".js"), "guide": (".html",)}


def _zone(rel):
    """Étiquette lisible de l'endroit où vit un fichier de l'application.
    Sert au rendu des alertes : « outil:module-cet.html » se comprend seul."""
    tete = rel.split("/")[0]
    if tete == "outils":
        return "outil"
    if tete == "fox":
        return "fox"
    if "/" not in rel:
        return "racine"          # legi-ref.js, glossaire.js, menu.html…
    return "module"              # module4/js/..., heures/..., paye/...


def citations_ecosysteme(racine_hs, racine_guide=None, inclure_fox=None):
    """{article: [(zone, chemin), ...]} sur TOUT le .html et le .js des deux
    dépôts. Remplace, pour les appelants qui veulent la couverture complète,
    la paire decouvrir_modules() + glob du guide."""
    if inclure_fox is None:
        inclure_fox = INCLURE_FOX
    citations = {}
    n_fichiers = 0
    plans = [("app", racine_hs)] + ([("guide", racine_guide)] if racine_guide else [])
    for etiquette, racine in plans:
        if not racine or not os.path.isdir(racine):
            continue
        for dossier, sous, fichiers in os.walk(racine):
            sous[:] = [d for d in sous if d != ".git"]
            for f in sorted(fichiers):
                if not f.endswith(EXTENSIONS[etiquette]):
                    continue
                rel = os.path.relpath(os.path.join(dossier, f), racine).replace(os.sep, "/")
                zone = "guide" if etiquette == "guide" else _zone(rel)
                if zone == "fox" and not inclure_fox:
                    continue
                n_fichiers += 1
                for art in citations_fichier_utiles(os.path.join(dossier, f)):
                    citations.setdefault(art, []).append((zone, rel))
    return citations, n_fichiers


# Codes que l'écosystème déclare lui-même dans outils/articles-loi.js mais que
# le fonds ne descend pas : il n'aspire que le travail et la sécu. Ce n'est pas
# une anomalie à signaler, c'est un périmètre. Les lire depuis le champ `code`
# évite d'avoir à tenir une exception à la main pour chacun.
CODES_HORS_PERIMETRE = {"transports": "code des transports",
                        "com.": "code de commerce"}


def codes_declares(racine_hs):
    """{num: code} d'après outils/articles-loi.js — la seule table de
    l'écosystème qui dise explicitement de quel code relève un numéro."""
    chemin = os.path.join(racine_hs, "outils", "articles-loi.js")
    if not os.path.isfile(chemin):
        return {}
    s = open(chemin, encoding="utf-8", errors="replace").read()
    i = s.find("var ARTICLES")
    if i < 0:
        return {}
    return {m.group(1): m.group(2) for m in
            re.finditer(r"'([A-Z]?\d[\w-]*)':\s*\{\s*code:\s*'([\w.]+)'", s[i:])}


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
    ap.add_argument("--sans-fox", action="store_true",
                     help="Exclure fox/ du périmètre (voir INCLURE_FOX)")
    args = ap.parse_args()

    # {article: [(zone, chemin), ...]} — tout le .html et le .js des deux dépôts.
    citations, n_fichiers = citations_ecosysteme(
        args.hs, args.guide, inclure_fox=not args.sans_fox)

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

    declares = codes_declares(args.hs)
    hors_perimetre = []

    for art, lieux in sorted(citations.items()):
        if art in EXCEPTIONS_CONFIRMEES:
            continue
        declare = declares.get(art)
        if declare in CODES_HORS_PERIMETRE:
            hors_perimetre.append((art, CODES_HORS_PERIMETRE[declare]))
            continue
        code, etat = etat_reel(args.fonds, art)
        lieux_uniques = sorted(set(lieux))
        if etat == "ABROGE":
            abroges.append((art, code, lieux_uniques))
        elif etat not in ("VIGUEUR",):
            non_confirmes.append((art, code, etat, lieux_uniques))

    def resume_lieux(lieux, n=3):
        """Le compte total vient EN PREMIER : « cité dans 401 fichiers » est
        l'information utile, les trois exemples ne sont qu'une illustration.
        Avant, l'alerte nommait trois lieux et taisait qu'il y en avait 398
        autres."""
        txt = ", ".join(f"{typ}:{nom}" for typ, nom in lieux[:n])
        if len(lieux) > n:
            txt = f"{len(lieux)} fichiers, dont {txt}"
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

    print(f"{n_fichiers} fichier(s) parcouru(s) (html + js, app et guide), "
          f"{len(citations)} article(s) distinct(s) cité(s) en texte brut.")
    print(f"  {len(abroges)} abrogé(s)")
    print(f"  {len(non_confirmes)} non confirmé(s)")
    if hors_perimetre:
        print(f"  {len(hors_perimetre)} hors périmètre du fonds, d'après leur "
              f"propre champ `code` : "
              + ", ".join(f"{a} ({q})" for a, q in hors_perimetre))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
