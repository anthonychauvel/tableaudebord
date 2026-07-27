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
    """Renvoie un bout de phrase sur ce que le fonds a trouvé de plus récent
    pour cette CCN -- vide si pas de croisement possible (pas de --fonds
    fourni, pas de fichier, rien d'exploitable)."""
    if vf is None or not fonds_racine:
        return ""
    chemin_fonds = os.path.join(fonds_racine, f"{idcc}.json")
    if not os.path.isfile(chemin_fonds):
        return " Pas de fichier fonds pour cet IDCC."
    try:
        fonds_data = json.load(open(chemin_fonds, encoding="utf-8"))
        clauses = vf.clauses_salaire(fonds_data)
    except Exception:
        clauses = []
    if not clauses:
        return " Le fonds n'a aucune clause salaire exploitable pour cette CCN."

    clauses.sort(key=lambda c: c[0], reverse=True)
    d_fonds, titre, _ = clauses[0]
    d_fonds_naive = d_fonds.replace(tzinfo=None) if d_fonds.tzinfo else d_fonds

    if d_fonds_naive <= d_ref:
        return (" Le fonds n'a rien de plus récent que la référence actuelle -- "
                "personne n'a renégocié depuis, pas une correction en attente de ta part.")

    # Une région couvre-t-elle déjà ce que le fonds a trouvé ? Sinon l'alerte
    # suggérerait d'aller chercher un texte déjà présent, juste pas sous
    # l'onglet Référence.
    for region in (g.get("regions") or {}).values():
        d_region = date_de_grille(region.get("d"))
        if d_region and d_region >= d_fonds_naive:
            return (f" Le fonds a trouvé {titre[:70]} ({d_fonds.strftime('%d/%m/%Y')}) -- "
                     f"déjà couvert par une région existante, ce n'est pas la référence "
                     f"elle-même qui a besoin de ce texte précis.")

    return (f" Le fonds a trouvé plus récent : {titre[:90]} "
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

        if age_jours > 365:
            n_plus_12 += 1
            titre_alerte = f"IDCC {idcc} : la référence affiche \u00ab Plus de 12 mois \u00bb dans l'app"
            gravite = "moyenne"
            intro = (f"Date de référence {g.get('d')} ({age_jours} jours) — c'est exactement le "
                     f"bandeau que voient les utilisateurs qui restent sur l'onglet Référence, "
                     f"qu'une région soit à jour ou non.")
        elif age_jours > 90:
            n_plus_3 += 1
            titre_alerte = f"IDCC {idcc} : référence de plus de 3 mois — signal précoce"
            gravite = "basse"
            intro = (f"Date de référence {g.get('d')} ({age_jours} jours) — pas encore ce que "
                     f"l'app montre aux utilisateurs (ça, c'est à 12 mois), mais un signal pour "
                     f"vérifier en amont plutôt que d'attendre.")
        else:
            continue

        detail = intro + croisement_fonds(vf, args.fonds, idcc, g, d_ref)
        resultat["alertes"].append({
            "categorie": "reference-plus-12-mois" if age_jours > 365 else "reference-plus-3-mois",
            "gravite": gravite,
            "titre": titre_alerte,
            "detail": detail,
        })

    print(f"{n_verifiees} grille(s) de référence vérifiée(s) "
          f"({n_ignorees_etat} estimée(s)/nationale(s), {n_ignorees_fusion} déjà fusionnée(s) "
          f"ignorée(s), {n_sans_date} sans date).")
    print(f"{n_plus_12} de plus de 12 mois, {n_plus_3} entre 3 et 12 mois.")
    for a in resultat["alertes"][:15]:
        print(f"  {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
