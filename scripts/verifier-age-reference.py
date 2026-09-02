#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-AGE-REFERENCE.PY — la grille de RÉFÉRENCE a-t-elle pris de l'âge,
sur DEUX paliers distincts, pour toutes les CCN sans exception ?

  - Plus de 12 mois : reproduit fidèlement le bandeau "⚠️ Plus de 12 mois"
    que GrillePaye affiche déjà lui-même aux utilisateurs sur l'onglet
    Référence. Un signal qu'un vrai utilisateur voit aujourd'hui.
  - Plus de 3 mois (et jusqu'à 12) : signal plus précoce, avant que ça
    n'atteigne le bandeau visible par les utilisateurs -- pour agir en amont
    plutôt que de découvrir la même chose une fois que l'app le montre déjà.

Une seule alerte par CCN (le palier le plus significatif, jamais les deux à
la fois pour la même entrée) -- chacune enrichie par ce que le fonds a trouvé
de plus récent, et si une région couvre déjà ce texte.

Différent de verifier-fraicheur.py : celui-là compare contre le fonds
("existe-t-il quelque chose de plus récent qu'on n'a pas encore repris ?").
Celui-ci part de l'âge absolu de la référence elle-même, comme l'app le fait
pour son propre bandeau, et enrichit ensuite avec le fonds.

USAGE
    python3 verifier-age-reference.py --hs /chemin/hs --fonds /chemin/droit/output/ccn --json sortie.json
"""
import argparse
import importlib.util
import json
import os
import re
from datetime import datetime, timezone

# Par défaut, la section « âge » ne remonte PLUS une alerte par CCN : sur ~340
# grilles, ~200 portent une date d'application au 01/01 (rétroactive) et
# tombaient dans « 3-12 mois » alors qu'elles sont parfaitement à jour — le
# piège de la date, répété 200 fois. À la place, on émet un RÉSUMÉ conscient du
# fonds (combien de références vieilles, et sur combien le fonds a réellement du
# plus récent — ces dernières étant déjà listées en « Grilles CCN » comme
# périmées, c'est là qu'on agit). Mettre True pour retrouver le détail par CCN.
DETAIL_PAR_CCN = False


def charger_verifier_fraicheur():
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verifier-fraicheur.py")
    spec = importlib.util.spec_from_file_location("verifier_fraicheur", chemin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def date_de_grille(txt):
    """Même format que verifier-fraicheur.py : JJ/MM/AAAA."""
    if not txt or len(txt) < 6:
        return None
    try:
        j, m, a = txt.split("/")
        return datetime(int(a), int(m), int(j))
    except (ValueError, IndexError):
        return None


def croisement_fonds(vf, fonds_racine, idcc, g, d_ref):
    """Renvoie (verdict, phrase). Le verdict dit si l'âge est ACTIONNABLE :
      - "plus-recent"       : le fonds a un texte strictement plus récent, non
                              couvert par une région -> action possible
                              (= déjà une périmée dans « Grilles CCN »).
      - "couvert-region"    : plus récent existe mais déjà pris par une région.
      - "rien-de-plus-recent": le fonds ne connaît rien de plus récent (piège de
                              la date d'application / branche non renégociée).
      - "pas-de-clause"     : fichier fonds présent mais aucune clause salaire.
      - "pas-de-fichier"    : pas de fichier fonds (IDCC hors corpus).
      - "pas-de-fonds"      : --fonds non fourni.
    La phrase reste lisible pour le mode détaillé (DETAIL_PAR_CCN=True)."""
    if vf is None or not fonds_racine:
        return "pas-de-fonds", ""
    chemin_fonds = os.path.join(fonds_racine, f"{idcc}.json")
    if not os.path.isfile(chemin_fonds):
        return "pas-de-fichier", " Pas de fichier fonds pour cet IDCC."
    try:
        fonds_data = json.load(open(chemin_fonds, encoding="utf-8"))
        clauses = vf.clauses_salaire(fonds_data)
    except Exception:
        clauses = []
    if not clauses:
        return "pas-de-clause", " Le fonds n'a aucune clause salaire exploitable pour cette CCN."

    clauses.sort(key=lambda c: c[0], reverse=True)
    d_fonds, titre, _ = clauses[0]
    d_fonds_naive = d_fonds.replace(tzinfo=None) if d_fonds.tzinfo else d_fonds

    if d_fonds_naive <= d_ref:
        return "rien-de-plus-recent", (
            " Le fonds n'a rien de plus récent que la référence actuelle -- "
            "personne n'a renégocié depuis, pas une correction en attente de ta part.")

    # Une région couvre-t-elle déjà ce que le fonds a trouvé ? Sinon l'alerte
    # suggérerait d'aller chercher un texte déjà présent, juste pas sous
    # l'onglet Référence.
    for region in (g.get("regions") or {}).values():
        d_region = date_de_grille(region.get("d"))
        if d_region and d_region >= d_fonds_naive:
            return "couvert-region", (
                f" Le fonds a trouvé {titre[:70]} ({d_fonds.strftime('%d/%m/%Y')}) -- "
                f"déjà couvert par une région existante, ce n'est pas la référence "
                f"elle-même qui a besoin de ce texte précis.")

    return "plus-recent", (
        f" Le fonds a trouvé plus récent : {titre[:90]} "
        f"({d_fonds.strftime('%d/%m/%Y')}) — c'est probablement celui-ci qui "
        f"manque à la référence.")


def charger_fusions(racine_hs):
    chemin = os.path.join(racine_hs, "GrillePaye", "index.html")
    s = open(chemin, encoding="utf-8", errors="replace").read()
    m = re.search(r"const CCN_FUSIONS=(\{.*?\});", s, re.S)
    return json.loads(m.group(1)) if m else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True, help="Racine du dépôt de l'application")
    ap.add_argument("--fonds", help="Dossier output/ccn du dépôt droit -- optionnel, "
                     "enrichit chaque alerte avec ce que le fonds a trouvé de plus récent")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    vf = charger_verifier_fraicheur() if args.fonds else None
    fusions = charger_fusions(args.hs)

    chemin = os.path.join(args.hs, "GrillePaye", "ccn-data.json")
    d = json.load(open(chemin, encoding="utf-8"))
    grilles = d["grilles"]

    resultat = {"module": "age-reference", "alertes": []}
    maintenant = datetime.now(timezone.utc).replace(tzinfo=None)
    n_verifiees, n_ignorees_etat, n_ignorees_fusion, n_sans_date = 0, 0, 0, 0
    n_plus_12, n_plus_3 = 0, 0
    # Combien de références vieilles ont RÉELLEMENT un texte plus récent au
    # fonds (verdict "plus-recent") -> les seules actionnables, et déjà en
    # « Grilles CCN » comme périmées.
    rec_plus_12, rec_plus_3 = 0, 0

    for idcc, g in sorted(grilles.items(), key=lambda kv: int(kv[0])):
        st = g.get("st")
        if st in ("estimated", "national"):
            n_ignorees_etat += 1
            continue
        if idcc in fusions:
            # Convention déjà fusionnée : sa référence est volontairement
            # gelée à titre historique, jamais quelque chose qu'on va mettre
            # à jour. L'app peut légitimement montrer les deux bandeaux
            # (fusion + âge) à un utilisateur -- mais côté veille, ce n'est
            # pas actionnable, donc pas la peine d'en reparler à chaque run.
            n_ignorees_fusion += 1
            continue
        d_ref = date_de_grille(g.get("d"))
        if not d_ref:
            n_sans_date += 1
            continue
        n_verifiees += 1
        age_jours = (maintenant - d_ref).days
        if age_jours <= 90:
            continue

        verdict, phrase = croisement_fonds(vf, args.fonds, idcc, g, d_ref)
        if age_jours > 365:
            n_plus_12 += 1
            if verdict == "plus-recent":
                rec_plus_12 += 1
        else:
            n_plus_3 += 1
            if verdict == "plus-recent":
                rec_plus_3 += 1

        if DETAIL_PAR_CCN:
            if age_jours > 365:
                titre_alerte = f"IDCC {idcc} : la référence affiche \u00ab Plus de 12 mois \u00bb dans l'app"
                gravite = "moyenne"
                intro = (f"Date de référence {g.get('d')} ({age_jours} jours) — c'est exactement le "
                         f"bandeau que voient les utilisateurs qui restent sur l'onglet Référence, "
                         f"qu'une région soit à jour ou non.")
            else:
                titre_alerte = f"IDCC {idcc} : référence de plus de 3 mois — signal précoce"
                gravite = "basse"
                intro = (f"Date de référence {g.get('d')} ({age_jours} jours) — pas encore ce que "
                         f"l'app montre aux utilisateurs (ça, c'est à 12 mois), mais un signal pour "
                         f"vérifier en amont plutôt que d'attendre.")
            resultat["alertes"].append({
                "categorie": "reference-plus-12-mois" if age_jours > 365 else "reference-plus-3-mois",
                "gravite": gravite,
                "titre": titre_alerte,
                "detail": intro + phrase,
            })

    # Résumé par défaut : une seule alerte informative au lieu de ~246 lignes.
    if not DETAIL_PAR_CCN and (n_plus_12 or n_plus_3):
        stale_12 = n_plus_12 - rec_plus_12
        detail = (
            f"{n_plus_12} référence(s) dépassent 12 mois — le bandeau « Plus de 12 mois » "
            f"que voient les utilisateurs sur l'onglet Référence.\n"
            f"  • {rec_plus_12} ont un texte plus récent au fonds → déjà listées en "
            f"« Grilles CCN » comme périmées, c'est là qu'on agit "
            f"(peut inclure le même avenant à date de signature plus tardive).\n"
            f"  • {stale_12} n'ont rien de plus récent au fonds (branche non renégociée ou "
            f"hors corpus) — rien à reprendre depuis la veille.\n"
            f"{n_plus_3} référence(s) entre 3 et 12 mois (signal précoce), dont {rec_plus_3} "
            f"avec un texte plus récent au fonds.\n"
            f"Détail par CCN masqué pour éviter le bruit (≈200 grilles au 01/01 rétroactif) ; "
            f"mets DETAIL_PAR_CCN=True en tête du script pour le rétablir.")
        resultat["alertes"].append({
            "categorie": "reference-age-resume",
            "gravite": "basse",
            "titre": "Âge des références : synthèse (bandeau « Plus de 12 mois » de l'app)",
            "detail": detail,
        })

    print(f"{n_verifiees} grille(s) de référence vérifiée(s) "
          f"({n_ignorees_etat} estimée(s)/nationale(s), {n_ignorees_fusion} déjà fusionnée(s) "
          f"ignorée(s), {n_sans_date} sans date).")
    print(f"{n_plus_12} de plus de 12 mois ({rec_plus_12} avec du plus récent au fonds), "
          f"{n_plus_3} entre 3 et 12 mois ({rec_plus_3} avec du plus récent au fonds).")
    print("Mode : " + ("détail par CCN" if DETAIL_PAR_CCN else "résumé (1 alerte de synthèse)"))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
