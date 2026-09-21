#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADAPTATEUR-GRILLES.PY — sortie JSON pour le tableau de bord, sans toucher
à verifier-fraicheur.py

verifier-fraicheur.py est déjà déployé et tourne chaque mercredi via GitHub
Actions, en écrivant du markdown. Le modifier pour lui ajouter une sortie
JSON risquerait d'introduire une régression dans un script qui fonctionne
déjà en production, pour un besoin qui ne concerne que ce tableau de bord.

Ce script importe donc verifier-fraicheur.py comme un module et réutilise
SES fonctions de collecte (clauses_salaire, date_de_grille, extrait_montants…)
pour produire directement du JSON. La logique de détection est identique au
script de production ; seule la mise en forme change.

USAGE
    python3 adaptateur-grilles.py --racine /chemin/vers/hs --fonds /chemin/vers/droit --json sortie.json
"""
import argparse
import glob
import importlib.util
import json
import os
import re
from datetime import datetime


def charger_module(chemin):
    spec = importlib.util.spec_from_file_location("verifier_fraicheur", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Date d'ARRIVÉE au fonds ------------------------------------------------
# La date d'un titre est celle de la SIGNATURE. Un avenant n'arrive pourtant au
# fonds que des mois plus tard, une fois étendu et publié. Or exceptions.json
# solde le passé par une coupure de date (« tout ce qui date d'avant le 10/08
# est déjà traité ») : comparée à la signature, elle masquait d'office tout
# avenant signé avant la coupure mais arrivé APRÈS -- c'est-à-dire le cas
# normal. Relevé le 21/09/2026 dans l'historique du fonds :
#     IDCC 7001  avenant 142 signé le 04/03/2026, arrivé le 14/09/2026
#     IDCC 953   avenant 64  signé le 15/01/2026, arrivé le 27/08/2026
# Les deux étaient masqués dès leur arrivée : la coupure ne pouvait rien
# laisser passer d'autre que des textes signés après elle.
#
# `dateModif` est la date de dernière modification Légifrance de la section :
# c'est la meilleure approximation de l'arrivée dont on dispose sans
# historique git (le runner récupère le fonds en profondeur 1).
def date_modif(noeud):
    v = noeud.get("dateModif") if isinstance(noeud, dict) else None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d") if v else None
    except ValueError:
        return None


# Même raisonnement pour les textes que le tableau NE SAVAIT PAS LIRE : jusqu'au
# 21/09/2026, « du 1er août 2023 » n'était pas reconnu comme une date (corrigé
# dans verifier-fraicheur.py). Ces clauses n'ont donc jamais pu être passées en
# revue avant la coupure du 10/08 : pour exceptions.json, elles n'existent que
# depuis le jour où on sait les lire. Exemple : l'IDCC 1307 et son barème
# « applicable au 1er février 2025 », resté invisible jusqu'ici.
_DATE_SANS_1ER = re.compile(r"(\d{1,2})\s+(janvier|f[ée]vrier|mars|avril|mai|juin|juillet"
                            r"|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)\s+(\d{4})"
                            r"|\d{1,2}/\d{1,2}/\d{4}")
LISIBLE_DEPUIS = datetime(2026, 9, 21)


def clauses_detaillees(vf, noeud, acc=None):
    """Comme vf.clauses_salaire, mais garde aussi la date d'arrivée."""
    if acc is None:
        acc = []
    if not isinstance(noeud, dict):
        return acc
    titre = noeud.get("title") or noeud.get("titre") or ""
    if titre and vf.SUJET_SALAIRE.search(titre):
        d = vf.date_du_titre(titre)
        if d:
            dm = date_modif(noeud)
            arrivee = max(d, dm) if dm else d
            if not _DATE_SANS_1ER.search(titre.lower()):
                arrivee = max(arrivee, LISIBLE_DEPUIS)
            acc.append({"d": d, "titre": titre.strip(), "texte": vf.texte_du_noeud(noeud),
                        "arrivee": arrivee})
    for s in (noeud.get("sections") or []):
        clauses_detaillees(vf, s, acc)
    return acc


# --- Contrôle par les MONTANTS -------------------------------------------------
# Comparer des dates ne suffit pas. Trois grilles en ligne le 21/09/2026 étaient
# fausses sans qu'aucune date ne le trahisse :
#     573   grille datée 01/03/2026, accord du 17/03/2026 : 16 jours, sous la marge
#     112   grille datée 01/01/2026, avenant du 22/01/2026 : 21 jours
#     1512  grille datée 01/01/2026, avenant du 12/01/2026 : 11 jours
# et un champ « d » peut être avancé sans que les montants suivent.
#
# Ici on cherche les montants de la grille DANS les textes. Si elle correspond
# à un texte (au moins la moitié de ses montants s'y retrouvent) et qu'un texte
# plus récent de la même portée existe, elle a été construite sur l'ancien.
# Très peu de bruit : 5 alertes sur 341 grilles au relevé du 21/09, toutes
# réelles. Le cas « montants retrouvés nulle part » (141 grilles) n'est PAS
# signalé : valeurs de point, taux horaires, annexes non extraites… trop de
# causes légitimes pour en faire des alertes.
_ESP = r"[ \u00a0\u202f]"
_M_MOIS = re.compile(r"(?<![\d,.])(\d{1,3}(?:" + _ESP + r"\d{3})+|\d{4,6})(?:,(\d{1,2}))?(?!\d)")
_M_HOR = re.compile(r"(?<![\d,.])(\d{1,2}),(\d{2,3})(?!\d)")
_SEUIL_CORRESPONDANCE = 0.5


def montants_du_texte(txt):
    """Montants mensuels (annuels ramenés au mois) et taux horaires d'un texte."""
    mensuels, horaires = set(), set()
    for m in _M_MOIS.finditer(txt or ""):
        v = float(re.sub(_ESP, "", m.group(1)) + "." + (m.group(2) or "0"))
        if 1000 <= v <= 20000:
            mensuels.add(round(v, 2))
        elif 12000 <= v <= 300000:          # RAM, forfait annuel
            mensuels.add(round(v / 12, 2))
    for m in _M_HOR.finditer(txt or ""):
        v = float(m.group(1) + "." + m.group(2))
        if 9 <= v <= 80:
            horaires.add(v)
    return mensuels, horaires


def _couvert(b, mensuels, horaires):
    return (any(abs(b - x) <= 0.6 for x in mensuels)
            or any(abs(b - h * 151.67) <= 1.0 for h in horaires))


def portee(titre):
    """Ce qui distingue deux textes qui ne se remplacent pas l'un l'autre.

    - la région en tête de titre : « Île-de-France Accord du … » -> une grille
      bâtie sur l'accord IDF ne se compare qu'aux accords IDF (1596/1597) ;
    - le numéro d'annexe : « annexe 1 » (fleurs, fruits et légumes) n'est pas
      remplacée par « annexe 3 » (teillage du lin) dans l'IDCC 7028, ni
      l'annexe I (minima mensuels) par l'annexe I bis (RAM) dans l'IDCC 112.
    Une annexe absente d'un des deux titres ne bloque pas la comparaison.
    """
    m = re.match(r"^(.*?)\s*(?:Accord|Avenant|Annexe|Protocole|Arrêté|Rectificatif)\b", titre)
    region = m.group(1).strip() if m else ""
    a = re.search(r"\bannexe\s+([ivx]+|\d+)(\s*(?:bis|ter))?\b", titre.lower())
    annexe = (a.group(1) + (a.group(2) or "").strip()) if a else None
    return region, annexe


def meme_portee(t1, t2):
    (r1, a1), (r2, a2) = portee(t1), portee(t2)
    return r1 == r2 and (a1 is None or a2 is None or a1 == a2)


def analyse_montants(grille, clauses, smic):
    """Situe la grille par rapport aux textes, d'après ses montants.

    ("ancien", texte correspondant, texte plus récent, taux)
        la grille correspond à un texte, et un texte plus récent de même
        portée existe : elle a été construite sur l'ancien ;
    ("a_jour", texte correspondant, None, taux)
        la grille correspond au texte le plus récent de sa portée ;
    None
        pas assez de montants pour conclure (point, horaire non converti…).
    """
    montants = [r.get("b") for r in grille.get("g", [])
                if isinstance(r.get("b"), (int, float)) and r.get("t") != "pct"
                and r["b"] >= 500 and not (smic and abs(r["b"] - smic) < 0.01)]
    if len(montants) < 3:
        return None
    notes = []
    for c in clauses:
        mens, hor = montants_du_texte(c["texte"])
        if len(mens) + len(hor) < 4:
            continue
        taux = sum(_couvert(b, mens, hor) for b in montants) / len(montants)
        notes.append((taux, c))
    if not notes:
        return None
    taux, source = max(notes, key=lambda x: (x[0], x[1]["d"]))
    if taux < _SEUIL_CORRESPONDANCE:
        return None
    plus_recents = sorted((c for t, c in notes
                           if c["d"] > source["d"] and t < taux
                           and meme_portee(c["titre"], source["titre"])),
                          key=lambda c: c["d"], reverse=True)
    if plus_recents:
        return ("ancien", source, plus_recents[0], taux)
    return ("a_jour", source, None, taux)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=".")
    ap.add_argument("--fonds", required=True)
    ap.add_argument("--marge", type=int, default=30)
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    ici = os.path.dirname(os.path.abspath(__file__))
    vf = charger_module(os.path.join(ici, "verifier-fraicheur.py"))

    gp = os.path.join(args.racine, "GrillePaye")
    data = json.load(open(os.path.join(gp, "ccn-data.json"), encoding="utf-8"))
    grilles = data["grilles"]
    smic = data.get("_smic")

    # Même garde-fou que dans verifier-fraicheur.py : une CCN fusionnée vers
    # une autre qui a déjà une vraie grille n'est pas "à créer".
    s_idx = open(os.path.join(gp, "index.html"), encoding="utf-8", errors="replace").read()
    mf = re.search(r"const CCN_FUSIONS=(\{.*?\});", s_idx, re.S)
    fusions = json.loads(mf.group(1)) if mf else {}

    resultat = {"module": "grilles-ccn", "alertes": []}

    for chemin in sorted(glob.glob(os.path.join(args.fonds, "output", "ccn", "*.json"))):
        idcc = os.path.splitext(os.path.basename(chemin))[0]
        if idcc.startswith("_"):
            continue
        try:
            fonds_data = json.load(open(chemin, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(fonds_data, dict) or "_error" in fonds_data:
            continue

        clauses = clauses_detaillees(vf, fonds_data)
        if not clauses:
            continue
        clauses.sort(key=lambda c: c["d"], reverse=True)
        d_fonds, titre, texte = clauses[0]["d"], clauses[0]["titre"], clauses[0]["texte"]
        # Date qui sert à la coupure d'exceptions.json : l'arrivée, pas la signature.
        arrivee = clauses[0]["arrivee"].strftime("%Y-%m-%d")

        # Même raison qu'ailleurs : une fusion ne sera plus mise à jour
        # individuellement, sa propre grille peut être vide ou cassée sans
        # que ça compte -- exclue avant même de la regarder, pas seulement
        # quand elle est totalement absente.
        if idcc in fusions:
            continue

        g = grilles.get(idcc)
        if not g:
            resultat["alertes"].append({
                "categorie": "grille-a-creer",
                "gravite": "basse",
                "titre": f"IDCC {idcc} : clause au fonds, aucune grille dans l'app",
                "detail": f"{titre} ({d_fonds.strftime('%d/%m/%Y')})",
                "date_texte": arrivee,
            })
            continue

        analyse = analyse_montants(g, clauses, smic)
        if analyse and analyse[0] == "ancien":
            _, source, recent, taux = analyse
            montants = vf.extrait_montants(recent["texte"])
            resultat["alertes"].append({
                "categorie": "grille-sur-texte-ancien",
                "gravite": "haute",
                "titre": f"IDCC {idcc} : grille construite sur un texte remplacé",
                "detail": (f"Les montants de la grille correspondent à « {source['titre']} » "
                           f"({taux:.0%} retrouvés), mais le fonds contient plus récent : "
                           f"« {recent['titre']} »."
                           + (" — " + " · ".join(montants[:2]) if montants else "")),
                "date_texte": recent["arrivee"].strftime("%Y-%m-%d"),
            })
            continue   # l'alerte de date ferait doublon, en moins précis
        if analyse and analyse[0] == "a_jour":
            # Les montants SONT ceux du texte le plus récent de sa portée : un
            # écart de dates n'est alors que le piège de la date d'application
            # (accord signé en mars, applicable au 1er janvier) ou un texte
            # d'une autre région / annexe. Rien à signaler.
            continue

        d_grille = vf.date_de_grille(g.get("d"))
        if not d_grille:
            resultat["alertes"].append({
                "categorie": "grille-sans-date",
                "gravite": "basse",
                "titre": f"IDCC {idcc} : pas de date exploitable",
                "detail": "Impossible de comparer à la veille tant que le champ date n'est pas renseigné.",
            })
            continue

        # Même garde-fou que dans verifier-fraicheur.py : une région à jour
        # suffit, même quand la référence n'a pas bougé. Ce script réutilise
        # les FONCTIONS de verifier-fraicheur.py mais a sa propre boucle de
        # comparaison — le correctif "régions" n'y était pas automatique.
        d_plus_recente = d_grille
        for region in (g.get("regions") or {}).values():
            d_region = vf.date_de_grille(region.get("d"))
            if d_region and d_region > d_plus_recente:
                d_plus_recente = d_region

        ecart = (d_fonds - d_plus_recente).days
        if ecart > args.marge:
            montants = vf.extrait_montants(texte)
            resultat["alertes"].append({
                "categorie": "grille-perimee",
                "gravite": "haute" if ecart > 180 else "moyenne",
                "titre": f"IDCC {idcc} : grille dépassée de {ecart} jours",
                "detail": f"{titre} — " + (" · ".join(montants[:2]) if montants else
                          "aucun montant repérable, ouvrir la clause"),
                "date_texte": arrivee,
            })

    print(f"{len(resultat['alertes'])} alerte(s) grilles.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
