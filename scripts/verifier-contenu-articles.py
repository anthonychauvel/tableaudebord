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
        # Le texte lui-même, et pas seulement son empreinte. Sans lui, l'alerte
        # sait DIRE qu'un article a changé mais pas MONTRER en quoi : il faut
        # aller relire Légifrance à la main pour comprendre. Avec lui, on
        # affiche l'avant et l'après. Coût mesuré : empreintes-articles.json
        # passe de 38 Ko à 477 Ko pour 497 articles — un fichier que Git diffe
        # sans broncher.
        "texte": " ".join(texte.split()),
    }


def extraits_compares(avant, apres, n=300):
    """Montrer les 300 premiers caractères d'un article de 2 000 signes revient
    souvent à afficher deux fois le même paragraphe, la modification étant à la
    fin. On cadre donc les deux extraits autour du premier endroit où les deux
    versions divergent."""
    def couper(t):
        return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"
    a, b = avant or "", apres or ""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if i < n // 2:
        return couper(a), couper(b)
    deb = max(0, i - n // 3)
    espace = a.find(" ", deb)
    deb = espace + 1 if espace > 0 else deb
    return "…" + couper(a[deb:]), "…" + couper(b[deb:])


def ecrire_releve(dossier, num, lieux):
    """La liste intégrale des fichiers va dans un fichier du dépôt, pas dans
    l'alerte : 401 lignes dans un tableau de bord, ce n'est plus un tableau de
    bord. Committée avec le reste, elle reste consultable après coup."""
    try:
        os.makedirs(dossier, exist_ok=True)
        chemin = os.path.join(dossier, num + ".txt")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(f"Fichiers citant {num} — {len(lieux)} au total\n\n")
            f.write("\n".join(f"{t}:{n}" for t, n in lieux) + "\n")
        return os.path.join(os.path.basename(dossier), num + ".txt")
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--guide", help="optionnel")
    ap.add_argument("--fonds", required=True)
    ap.add_argument("--empreintes", required=True,
                     help="Fichier persistant qui garde l'empreinte de chaque article d'un run à l'autre")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    ap.add_argument("--releves", help="Dossier où déposer la liste complète des "
                                       "fichiers citant un article qui a changé")
    ap.add_argument("--sans-fox", action="store_true",
                     help="Exclure fox/ du périmètre")
    args = ap.parse_args()

    vo = charger_module("verifier-outils.py")
    vce = charger_module("verifier-citations-ecosysteme.py")

    # Citations des outils : code explicite, connu via articles-loi.js.
    table_codes = vo.charger_articles_locaux(args.hs)
    citations_outils, _ = vo.citations_dans_outils(args.hs)

    # Citations en texte brut : pas de code explicite, on teste les deux corpus
    # (comme verifier-citations-ecosysteme.py le fait déjà). Le parcours est
    # maintenant élargi à TOUT le .html et le .js des deux dépôts — voir le
    # commentaire de citations_ecosysteme(). Auparavant on ne lisait que le
    # index.html de chaque module et les pages du guide, ce qui laissait 157
    # articles hors de toute surveillance.
    citations_texte_brut, _ = vce.citations_ecosysteme(
        args.hs, args.guide, inclure_fox=not args.sans_fox)

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
            lieux = sorted(set(lieux))
            lien = f"https://monlegitexte.heuressupfrance.workers.dev/?art={num}"
            if code == "CSS":
                lien += "&code=secu"

            # OÙ, pour de bon. L'ancienne version nommait trois lieux et taisait
            # qu'il pouvait y en avoir 400 : L3121-36 est cité dans 401 fichiers.
            # Le compte passe donc devant, l'application avant le guide (c'est
            # elle qu'on édite), et le relevé complet part dans un fichier.
            app = [f"{t}:{n}" for t, n in lieux if t != "guide"]
            gui = [n for t, n in lieux if t == "guide"]
            ou = []
            if app:
                ou.append("dans l'application : " + ", ".join(app[:8])
                          + (f" et {len(app)-8} autre(s)" if len(app) > 8 else ""))
            if gui:
                ou.append(f"{len(gui)} page(s) du guide" if len(gui) > 4
                          else "guide : " + ", ".join(gui))
            releve = ecrire_releve(args.releves, num, lieux) if args.releves else None

            ea, eb = extraits_compares(avant.get("texte"), empr.get("texte"))
            detail = (f"Toujours en vigueur, mais le contenu diffère de la dernière "
                      f"empreinte (version {avant.get('version')} -> {empr['version']}). "
                      f"Cité dans {len(lieux)} fichier(s) — " + " ; ".join(ou) + ".")
            if ea and eb and ea != eb:
                detail += f"\n\nAVANT — {ea}\n\nAPRÈS — {eb}"
            elif not avant.get("texte"):
                detail += ("\n\n(Pas d'avant/après : l'empreinte précédente datait "
                           "d'une version du script qui ne gardait pas le texte.)")
            if releve:
                detail += f"\n\nRelevé complet des lieux : {releve}"

            resultat["alertes"].append({
                "categorie": "contenu-article-modifie",
                "gravite": "moyenne",
                "titre": f"{num} ({code}) : le texte a changé depuis la dernière vérification",
                "detail": detail,
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
