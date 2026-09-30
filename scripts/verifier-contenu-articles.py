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
import difflib
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone


def charger_module(nom_fichier):
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), nom_fichier)
    spec = importlib.util.spec_from_file_location(nom_fichier[:-3].replace("-", "_"), chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def empreinte_article(fonds, code, num):
    """Renvoie (version, dateDebut, hash_texte) ou None si l'article est
    introuvable dans le corpus indiqué."""
    art = lire_article(fonds, code, num)
    if not art:
        return None
    texte = (art.get("texte") or "") + (art.get("nota") or "")
    h = hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]
    return {
        "version": art.get("versionArticle"),
        "dateDebut": art.get("dateDebut"),
        "hash": h,
        # Identifiant Légifrance et section : servent à retrouver le
        # remplaçant le jour où le numéro disparaît (voir chercher_remplacant).
        "id": art.get("id"),
        "section": art.get("sectionParentCid"),
        "sectionTitre": art.get("sectionParentTitre"),
        # Le texte lui-même, et pas seulement son empreinte. Sans lui, l'alerte
        # sait DIRE qu'un article a changé mais pas MONTRER en quoi : il faut
        # aller relire Légifrance à la main pour comprendre. Avec lui, on
        # affiche l'avant et l'après. Coût mesuré : empreintes-articles.json
        # passe de 38 Ko à 477 Ko pour 497 articles — un fichier que Git diffe
        # sans broncher.
        "texte": " ".join(texte.split()),
    }


# En dessous de 35 % de texte commun, on parle de « changement de sujet ».
SEUIL_SUJET = 0.35

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veille_commun import lien_monlegitexte  # noqa: E402


def dossier_code(fonds, code):
    return os.path.join(fonds, "output", "code-secu" if code == "CSS" else "code-travail")


def lire_article(fonds, code, num):
    """L'article du fonds, ou None s'il n'y est pas (fichier absent OU
    « "article": null »)."""
    chemin = os.path.join(dossier_code(fonds, code), num + ".json")
    if not os.path.isfile(chemin):
        return None
    try:
        return json.load(open(chemin, encoding="utf-8")).get("article")
    except Exception:
        return None


def statut_fonds(fonds, code, num):
    """« present » / « introuvable » (le fonds a interrogé Légifrance sur ce
    numéro et n'a rien reçu : l'article n'existe plus sous ce numéro) /
    « jamais-tente » (pas de fichier : on ne sait rien, on ne conclut rien)."""
    chemin = os.path.join(dossier_code(fonds, code), num + ".json")
    if not os.path.isfile(chemin):
        return "jamais-tente"
    try:
        d = json.load(open(chemin, encoding="utf-8"))
    except Exception:
        return "jamais-tente"
    if "_error" in d:
        return "jamais-tente"
    return "present" if d.get("article") else "introuvable"


def ressemblance(a, b):
    """0 = rien en commun, 1 = identique. Comparé MOT à mot, pas lettre à
    lettre : deux phrases françaises sans rapport partagent tant de lettres
    qu'une comparaison par caractère les jugeait « à 50 % semblables ».
    Sur les 500 premiers mots : largement assez pour juger, et reste rapide."""
    a = (a or "").lower().split()[:500]
    b = (b or "").lower().split()[:500]
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def chercher_remplacant(fonds, code, num, ancien):
    """Un article cité a disparu : qui l'a remplacé ?
    1. un article actuel qui porte une CONCORDANCE vers l'ancien numéro
       (recodification : L212-7 -> L3121-36) ;
    2. sinon, dans la MÊME section, l'article dont le texte ressemble le plus
       au dernier texte connu (renumérotation : le texte déménage, le numéro
       change) — retenu seulement au-dessus de 60 % de ressemblance.
    Pré-filtre sur le texte brut du fichier avant tout décodage JSON : on lit
    les ~20 000 fiches, on n'en décode qu'une poignée."""
    dossier = dossier_code(fonds, code)
    if not os.path.isdir(dossier):
        return None
    cle_conc = f'"articleNum": "{num}"'
    section = (ancien or {}).get("section")
    cle_sect = f'"sectionParentCid": "{section}"' if section else None
    texte_ancien = (ancien or {}).get("texte") or ""
    meilleur = None
    for e in os.scandir(dossier):
        if not e.name.endswith(".json") or e.name.startswith("_") or e.name == num + ".json":
            continue
        try:
            brut = open(e.path, encoding="utf-8").read()
        except Exception:
            continue
        conc = cle_conc in brut
        sect = bool(cle_sect) and cle_sect in brut
        if not conc and not sect:
            continue
        try:
            art = json.loads(brut).get("article")
        except Exception:
            continue
        if not art or art.get("etat") != "VIGUEUR":
            continue
        if conc and any(l.get("articleNum") == num for l in (art.get("lienConcordes") or [])):
            return _remplacant(art, "concordance officielle", 1.0)
        if sect and texte_ancien:
            r = ressemblance(" ".join((art.get("texte") or "").split()), texte_ancien)
            if r >= 0.6 and (meilleur is None or r > meilleur[1]):
                meilleur = (art, r)
    if meilleur:
        return _remplacant(meilleur[0], "texte presque identique dans la même section", meilleur[1])
    return None


def _remplacant(art, comment, score):
    loi = ""
    for l in sorted(art.get("lienModifications") or [],
                    key=lambda l: l.get("datePubliTexte") or "", reverse=True):
        if l.get("linkType") in ("DEPLACE", "TRANSFERE", "CREE", "CODIFICATION", "MODIFIE"):
            loi = l.get("textTitle") or ""
            break
    return {"num": art.get("num"), "loi": loi, "comment": comment,
            "score": round(score, 2), "id": art.get("id")}


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

    def decrire_lieux(num, lieux):
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
        return f"Cité dans {len(lieux)} fichier(s) — " + " ; ".join(ou), releve

    def signaler_disparu(cle, code, num, lieux, memoire):
        """(b) + (a) : un article cité, en vigueur la dernière fois, n'existe
        plus sous ce numéro. Alerte haute, avec son dernier texte connu et,
        si on le trouve, son remplaçant."""
        aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        memoire.setdefault("disparu_depuis", aujourd_hui)
        if "remplacant" not in memoire:
            memoire["remplacant"] = chercher_remplacant(args.fonds, code, num, memoire)
        rempl = memoire.get("remplacant")
        ou, releve = decrire_lieux(num, sorted(set(lieux)))
        detail = (f"Introuvable au fonds depuis le {memoire['disparu_depuis']} : Légifrance ne "
                  f"renvoie plus rien pour ce numéro (abrogé, transféré ou renuméroté). {ou}.")
        lien = lien_monlegitexte(num, code)
        if rempl:
            detail = (f"➡️ REMPLACÉ PAR {rempl['num']}"
                      + (f" — {rempl['loi']}" if rempl.get("loi") else "")
                      + f" (trouvé par {rempl['comment']}).\n\n" + detail)
            lien = lien_monlegitexte(rempl["num"], code)
        else:
            detail += "\n\nAucun remplaçant trouvé automatiquement : chercher sur Légifrance."
        if memoire.get("texte"):
            t = memoire["texte"]
            detail += "\n\nDERNIER TEXTE CONNU — " + (t if len(t) <= 700 else t[:700].rsplit(" ", 1)[0] + "…")
        if releve:
            detail += f"\n\nRelevé complet des lieux : {releve}"
        alerte = {
            "categorie": "article-introuvable",
            "gravite": "haute",
            "titre": f"{num} ({code}) : n'existe plus sous ce numéro"
                     + (f", remplacé par {rempl['num']}" if rempl else ""),
            "detail": detail,
            "lien": lien,
            "date_texte": memoire["disparu_depuis"],
        }
        if rempl:
            alerte["remplace_par"] = rempl["num"]
        resultat["alertes"].append(alerte)

    def traiter(cle, code, num, lieux):
        nonlocal n_verifies, n_premiere_fois
        empr = empreinte_article(args.fonds, code, num)
        avant = empreintes_avant.get(cle)
        if empr is None:
            if avant is None:
                return
            # On garde la mémoire : sans elle, le dernier texte connu serait
            # perdu au passage suivant, et l'alerte avec.
            empreintes_apres[cle] = dict(avant)
            if statut_fonds(args.fonds, code, num) == "introuvable":
                signaler_disparu(cle, code, num, lieux, empreintes_apres[cle])
            return
        n_verifies += 1
        empreintes_apres[cle] = empr
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
            ou, releve = decrire_lieux(num, lieux)

            ea, eb = extraits_compares(avant.get("texte"), empr.get("texte"))
            detail = (f"Toujours en vigueur, mais le contenu diffère de la dernière "
                      f"empreinte (version {avant.get('version')} -> {empr['version']}). "
                      + ou + ".")
            if ea and eb and ea != eb:
                detail += f"\n\nAVANT — {ea}\n\nAPRÈS — {eb}"
            elif not avant.get("texte"):
                detail += ("\n\n(Pas d'avant/après : l'empreinte précédente datait "
                           "d'une version du script qui ne gardait pas le texte.)")
            if releve:
                detail += f"\n\nRelevé complet des lieux : {releve}"

            alerte = {
                "categorie": "contenu-article-modifie",
                "gravite": "moyenne",
                "titre": f"{num} ({code}) : le texte a changé depuis la dernière vérification",
                "detail": detail,
                "lien": lien,
            }
            # (c) Le texte a presque ENTIÈREMENT changé : ce n'est plus un
            # seuil ou une virgule, l'article parle d'autre chose — la
            # citation de l'appli est peut-être devenue fausse.
            r = ressemblance(avant.get("texte"), empr.get("texte"))
            if avant.get("texte") and r < SEUIL_SUJET:
                alerte["gravite"] = "haute"
                alerte["etiquettes"] = ["Changement de sujet"]
                alerte["detail"] = (f"⚠️ CHANGEMENT DE SUJET : l'ancien et le nouveau texte n'ont "
                                    f"plus que {round(r*100)} % en commun.\n\n" + detail)
            resultat["alertes"].append(alerte)

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
            # « or cle in empreintes_avant » : un article disparu du fonds
            # n'a plus d'empreinte actuelle, mais on se souvient de lui.
            if empreinte_article(args.fonds, code, num) is not None or cle in empreintes_avant:
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
