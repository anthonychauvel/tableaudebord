#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-AGE-REFERENCE.PY — la grille de RÉFÉRENCE (celle que l'app montre
par défaut) a-t-elle plus de 12 mois, exactement comme l'app le calcule
elle-même pour son propre bandeau "⚠️ Plus de 12 mois" ?

Différent de verifier-fraicheur.py : celui-là compare contre le fonds ("existe-
t-il quelque chose de plus récent qu'on n'a pas encore repris ?"). Celui-ci ne
compare à rien d'extérieur -- il reproduit tel quel le calcul que
GrillePaye/index.html fait pour ses propres utilisateurs (aujourd'hui moins
gd.d, plus de 365 jours -> bandeau affiché).

La raison d'être de ce script : une convention à régions peut être "couverte"
au sens de verifier-fraicheur.py (une région a une date récente) tout en
affichant EXACTEMENT ce bandeau aux utilisateurs qui restent sur l'onglet
Référence -- les deux questions sont légitimes, mais différentes, et
verifier-fraicheur.py ne pouvait pas répondre à celle-ci sans perdre sa
réponse à l'autre. D'où un script séparé plutôt qu'un réglage de plus dans
le même calcul.

Comme dans l'app : st=estimated et st=national sont exclus (déjà couverts par
leurs propres bandeaux ⚠️/🔵, pas celui-ci). La fusion (CCN_FUSIONS) n'exclut
PAS le calcul de l'âge -- l'app ne l'exclut pas non plus, les deux bandeaux
peuvent s'afficher ensemble.

USAGE
    python3 verifier-age-reference.py --hs /chemin/vers/hs --json sortie.json
"""
import argparse
import json
import os
from datetime import datetime, timezone


def date_de_grille(txt):
    """Même format que verifier-fraicheur.py : JJ/MM/AAAA."""
    if not txt or len(txt) < 6:
        return None
    try:
        j, m, a = txt.split("/")
        return datetime(int(a), int(m), int(j), tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True, help="Racine du dépôt de l'application")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    chemin = os.path.join(args.hs, "GrillePaye", "ccn-data.json")
    d = json.load(open(chemin, encoding="utf-8"))
    grilles = d["grilles"]

    resultat = {"module": "age-reference", "alertes": []}
    maintenant = datetime.now(timezone.utc)
    n_verifiees, n_ignorees_etat, n_sans_date = 0, 0, 0

    for idcc, g in sorted(grilles.items(), key=lambda kv: int(kv[0])):
        st = g.get("st")
        if st in ("estimated", "national"):
            n_ignorees_etat += 1
            continue
        d_ref = date_de_grille(g.get("d"))
        if not d_ref:
            n_sans_date += 1
            continue
        n_verifiees += 1
        age_jours = (maintenant - d_ref).days
        if age_jours > 365:
            resultat["alertes"].append({
                "categorie": "reference-plus-12-mois",
                "gravite": "moyenne",
                "titre": f"IDCC {idcc} : la référence affiche \u00ab Plus de 12 mois \u00bb dans l'app",
                "detail": f"Date de référence {g.get('d')} ({age_jours} jours) — "
                          f"c'est exactement le bandeau que voient les utilisateurs qui "
                          f"restent sur l'onglet Référence, qu'une région soit à jour ou non.",
            })

    print(f"{n_verifiees} grille(s) de référence vérifiée(s) "
          f"({n_ignorees_etat} estimée(s)/nationale(s) ignorée(s), {n_sans_date} sans date).")
    print(f"{len(resultat['alertes'])} alerte(s) — référence affichant le bandeau 12 mois.")
    for a in resultat["alertes"][:15]:
        print(f"  {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
