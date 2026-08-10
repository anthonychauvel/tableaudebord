#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CROISER-ALERTES-TEXTES.PY — le cœur de ce que Chauvel demande depuis le début :
être prévenu quand un texte apparaît sur l'API (JORF ou accord d'entreprise)
qui correspond à une CCN DÉJÀ en alerte.

Le raisonnement : si une convention est en alerte "grille périmée / sous SMIC /
à créer", et qu'un texte récent paru au Journal Officiel ou un accord mentionne
précisément cet IDCC, c'est un signal fort -- très probablement l'avenant qui
résout justement l'alerte. Plutôt que de le découvrir des semaines plus tard,
on le remonte tout de suite, en le rattachant à l'alerte existante.

Ce script ne CRÉE pas d'alerte de grille : il RELIE les textes fraîchement
aspirés aux alertes déjà là. Une CCN qui n'est en alerte pour rien ne
déclenche rien ici, même si un texte la concernant paraît -- le but est de
prioriser ce qui est déjà en attente, pas d'ajouter du bruit.

Comment le lien est fait : on cherche le numéro d'IDCC de chaque CCN en
alerte dans le TITRE de chaque texte JORF/ACCO. C'est volontairement simple
et robuste -- les arrêtés d'extension citent l'IDCC ou le numéro de brochure
dans leur intitulé ("...portant extension d'un avenant à la convention
collective nationale ... (n° XXXX)"). Un faux positif éventuel est sans
gravité (au pire, on regarde un texte qui ne servait pas) ; un faux négatif
serait pire (rater l'avenant attendu), donc on ratisse un peu large.

USAGE
    python3 croiser-alertes-textes.py \
        --donnees ../donnees.json \
        --jorf /chemin/droit/output/jorf \
        --acco /chemin/droit/output/acco \
        --json sortie.json
"""
import argparse
import json
import os
import re
import glob


def idccs_en_alerte(donnees_path):
    """Renvoie {idcc: titre_de_l_alerte} pour toutes les CCN actuellement en
    alerte de grille -- ce sont elles qu'on veut relier à un texte neuf."""
    try:
        d = json.load(open(donnees_path, encoding="utf-8"))
    except Exception:
        return {}
    en_alerte = {}
    for section in d.get("sections", []):
        # On se limite aux sections où un IDCC "en attente" a du sens : les
        # grilles. (Pas les sections techniques comme la syntaxe JS.)
        if section.get("id") not in ("grilles", "age"):
            continue
        for a in section.get("alertes", []):
            m = re.search(r"\bIDCC\s+(\d{1,5})\b", a.get("titre", ""))
            if m:
                en_alerte.setdefault(m.group(1), a.get("titre", ""))
    return en_alerte


def titres_des_textes(dossier):
    """Renvoie [(id, titre), ...] pour tous les textes d'un dossier
    (JORF ou ACCO), en lisant chaque fichier récupéré."""
    out = []
    if not dossier or not os.path.isdir(dossier):
        return out
    for chemin in glob.glob(os.path.join(dossier, "*.json")):
        base = os.path.basename(chemin)
        if base.startswith("_"):  # _summary.json, _debug, etc.
            continue
        try:
            d = json.load(open(chemin, encoding="utf-8"))
        except Exception:
            continue
        titre = d.get("titre") or ""
        if titre:
            out.append((os.path.splitext(base)[0], titre))
    return out


def cherche_idcc_dans_titre(idcc, titre):
    """Le numéro d'IDCC apparaît-il dans le titre, en tant que NOMBRE ENTIER
    (pas au milieu d'un autre nombre) ? '1605' ne doit pas matcher '16050'."""
    return re.search(r"(?<!\d)" + re.escape(idcc) + r"(?!\d)", titre) is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", required=True, help="donnees.json (les alertes déjà calculées)")
    ap.add_argument("--jorf", help="Dossier output/jorf du dépôt droit")
    ap.add_argument("--acco", help="Dossier output/acco du dépôt droit")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    en_alerte = idccs_en_alerte(args.donnees)
    resultat = {"module": "croisement-textes", "alertes": []}

    if not en_alerte:
        print("Aucune CCN en alerte à croiser -- rien à faire.")
        if args.json:
            json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0

    textes = []
    for dossier, source in ((args.jorf, "Journal Officiel"), (args.acco, "accord d'entreprise")):
        for tid, titre in titres_des_textes(dossier):
            textes.append((tid, titre, source))

    print(f"{len(en_alerte)} CCN en alerte, {len(textes)} texte(s) JORF/ACCO à croiser.")

    n_liens = 0
    for idcc, titre_alerte in sorted(en_alerte.items(), key=lambda kv: int(kv[0])):
        correspondances = [(tid, titre, source) for tid, titre, source in textes
                           if cherche_idcc_dans_titre(idcc, titre)]
        if not correspondances:
            continue
        n_liens += 1
        # Une alerte par CCN, listant le(s) texte(s) trouvé(s).
        lignes = []
        for tid, titre, source in correspondances[:5]:
            lignes.append(f"• [{source}] {titre[:90]}")
        detail = (f"Cette convention est déjà en alerte (« {titre_alerte} »), et un ou "
                  f"plusieurs textes viennent de paraître qui la mentionnent — "
                  f"probablement de quoi lever l'alerte :\n" + "\n".join(lignes))
        # Date du texte le plus récent parmi les correspondances, pour la
        # coupure par date dans exceptions.json (mode « jusqu_au »). On lit
        # « du J MOIS AAAA » dans le titre ; à défaut, pas de date_texte et
        # l'alerte reste visible.
        _MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
                 "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
                 "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
                 "decembre": 12}
        dates_iso = []
        for _tid, _titre, _src in correspondances:
            m = re.search(r"\bdu\s+(\d{1,2})\s+([a-zûéèà]+)\s+(20\d\d)", _titre.lower())
            if m and m.group(2) in _MOIS:
                dates_iso.append(f"{int(m.group(3)):04d}-{_MOIS[m.group(2)]:02d}-{int(m.group(1)):02d}")
        alerte = {
            "categorie": "texte-pour-ccn-en-alerte",
            "gravite": "haute",  # c'est exactement ce qu'on veut voir en priorité
            "titre": f"IDCC {idcc} : un texte est paru pour cette CCN en attente",
            "detail": detail,
        }
        if dates_iso:
            alerte["date_texte"] = max(dates_iso)
        resultat["alertes"].append(alerte)

    print(f"{n_liens} CCN en alerte ont un texte JORF/ACCO correspondant.")
    for a in resultat["alertes"][:10]:
        print(f"  {a['titre']}")

    if args.json:
        json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
