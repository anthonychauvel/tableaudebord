#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-NOINDEX-LIVE.PY — MonLegiTexte est-il vraiment protégé, en
production, maintenant ?

Différent de tous les autres scripts de ce tableau de bord : ceux-là lisent
des fichiers (le dépôt source). Celui-ci fait un VRAI appel réseau vers le
site en ligne — le seul moyen de savoir si l'en-tête X-Robots-Tag est
réellement envoyé par le Worker déployé, pas seulement présent dans le code
source (verification.yml, à la racine de l'app, fait déjà ce contrôle —
repris ici pour l'avoir centralisé au même endroit que tout le reste).

Non testé en conditions réelles au moment où ce script a été écrit : mon
bac à sable n'a pas accès à workers.dev (liste d'autorisation réseau
restreinte). Le code suit un patron HTTP standard, mais vérifie-le au
premier run réel avant de t'y fier pleinement.

USAGE
    python3 verifier-noindex-live.py --url https://monlegitexte.heuressupfrance.workers.dev/ --json sortie.json
"""
import argparse
import json
import urllib.error
import urllib.request


def requete(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "veille-perso-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(2000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), ""
    except Exception as e:
        return None, {}, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://monlegitexte.heuressupfrance.workers.dev/",
                     help="URL de MonLegiTexte en production")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    resultat = {"module": "noindex-live", "alertes": []}

    statut, entetes, corps = requete(args.url)
    if statut is None:
        resultat["alertes"].append({
            "categorie": "site-injoignable",
            "gravite": "haute",
            "titre": "MonLegiTexte ne répond pas",
            "detail": f"{args.url} — {corps[:150]}",
        })
    else:
        entetes_bas = {k.lower(): v for k, v in entetes.items()}
        xrt = entetes_bas.get("x-robots-tag", "")
        if "noindex" not in xrt.lower():
            resultat["alertes"].append({
                "categorie": "noindex-absent",
                "gravite": "haute",
                "titre": "X-Robots-Tag: noindex absent de la réponse réelle",
                "detail": f"Statut {statut}. En-tête reçu : {xrt or '(absent)'}. "
                          f"Le site est indexable tel quel, même si le code source dit le contraire.",
            })
        if "noindex" not in corps.lower():
            resultat["alertes"].append({
                "categorie": "noindex-meta-absent",
                "gravite": "basse",
                "titre": "Balise <meta robots noindex> non trouvée dans le HTML reçu",
                "detail": "Redondant avec l'en-tête HTTP si celui-ci est bien présent — "
                          "pas grave seul, mais à vérifier si l'en-tête l'est aussi.",
            })

    n_alertes = len(resultat["alertes"])
    print(f"Statut HTTP : {statut}")
    print(f"{n_alertes} alerte(s).")
    for a in resultat["alertes"]:
        print(f"  [{a['gravite']}] {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
