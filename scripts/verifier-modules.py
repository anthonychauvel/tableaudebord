#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-MODULES.PY — alertes sur les 8 modules principaux de l'app

Deux choses vérifiées, choisies parce qu'elles sont concrètement détectables
sans aucune ambiguïté d'interprétation (contrairement aux grilles de salaire) :

  1. Présence : chacun des 8 modules attendus existe-t-il dans le dépôt ?
     C'est ce qui a révélé que taiko.html n'était pas encore déployé.

  2. Assets cassés : chaque référence locale (img, script, lien vers un autre
     module) pointe-t-elle vers un fichier qui existe réellement ? C'est le
     mécanisme qui aurait détecté le Mizuki.PNG manquant avant que quelqu'un
     ne tombe dessus par hasard.

Ce script ne vérifie PAS le contenu métier des modules (ça, c'est verifier-ccn.py
et verifier-grilles.py) : uniquement leur intégrité structurelle.

USAGE
    python3 verifier-modules.py --racine /chemin/vers/hs --json sortie.json
"""
import argparse
import json
import os
import re
import sys

# Un module peut être un DOSSIER (module5/index.html) ou un FICHIER isolé à la
# racine (taiko.html). Les deux formes coexistent dans ce projet.
MODULES_ATTENDUS = {
    "heures": "heures/index.html",
    "paye": "paye/index.html",
    "fox": "fox/index.html",
    "module4": "module4/index.html",
    "module5": "module5/index.html",
    "module6": "module6/index.html",
    "module7": "module7/index.html",
    "taiko": "taiko.html",
}

EXT_LOCALES = re.compile(r'(?:src|href)="([^"]+\.(?:png|jpe?g|svg|json|js|css))"', re.I)


def racine_module(chemin_index):
    """Dossier de référence pour résoudre les chemins relatifs du module."""
    return os.path.dirname(chemin_index) or "."


def cible_reelle(racine, base_module, ref):
    """Résout une référence vers un chemin disque, en tenant compte des deux
    conventions présentes dans ce projet : chemin relatif au dossier du module
    (« icon.png »), ou absolu depuis la racine du site (« /apple-touch-icon.png »,
    « /hs/… »). Une première version de ce script traitait tout comme relatif
    au module et signalait à tort des icônes de la racine comme cassées.
    """
    if ref.startswith("/"):
        # « /apple-touch-icon.png » -> racine/apple-touch-icon.png
        # « /hs/apple-touch-icon.png » -> le préfixe /hs/ est le nom du dépôt
        # tel que servi en production ; on le retire pour retomber sur la racine
        # locale du clone.
        sans_prefixe = re.sub(r"^/hs/", "/", ref)
        return os.path.normpath(os.path.join(racine, sans_prefixe.lstrip("/")))
    return os.path.normpath(os.path.join(base_module, ref))


def assets_casses(racine, chemin_index):
    """Repère les références locales qui ne pointent vers aucun fichier réel."""
    casses = []
    html = open(chemin_index, encoding="utf-8", errors="replace").read()
    base = racine_module(chemin_index)
    vus = set()
    for m in EXT_LOCALES.finditer(html):
        ref = m.group(1)
        # On ignore les URL absolues (http, https, //) et les data-URI.
        if re.match(r"^(https?:)?//|^data:", ref):
            continue
        if ref in vus:
            continue
        vus.add(ref)
        cible = cible_reelle(racine, base, ref)
        if not os.path.isfile(cible):
            casses.append(ref)
    return casses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--racine", default=".", help="Racine du dépôt de l'application")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    resultat = {"module": "8-modules", "alertes": []}

    absents = []
    for nom, rel in MODULES_ATTENDUS.items():
        chemin = os.path.join(args.racine, rel)
        if not os.path.isfile(chemin):
            absents.append((nom, rel))

    for nom, rel in absents:
        resultat["alertes"].append({
            "categorie": "module-absent-de-prod",
            # Basse, pas haute : un module en développement qui n'est pas encore
            # sur la branche de production est un état de travail NORMAL, pas un
            # oubli. Seul toi sais si c'est voulu — ce script constate, il ne juge pas.
            "gravite": "basse",
            "module": nom,
            "titre": f"{nom} : pas sur la branche de production",
            "detail": f"« {rel} » absent de cette branche. Probablement encore en "
                      f"bac à sable — à vérifier seulement si ce n'est pas le cas.",
        })

    for nom, rel in MODULES_ATTENDUS.items():
        chemin = os.path.join(args.racine, rel)
        if not os.path.isfile(chemin):
            continue  # déjà signalé ci-dessus
        casses = assets_casses(args.racine, chemin)
        for ref in casses:
            resultat["alertes"].append({
                "categorie": "asset-casse",
                "gravite": "moyenne",
                "module": nom,
                "titre": f"{nom} : référence cassée",
                "detail": f"« {ref} » est référencé mais n'existe pas sur le disque. "
                          f"Provoque une image manquante ou un script qui ne charge pas.",
            })

    print(f"{len(MODULES_ATTENDUS)} modules attendus, {len(absents)} absent(s).")
    n_assets = sum(1 for a in resultat["alertes"] if a["categorie"] == "asset-casse")
    print(f"{n_assets} référence(s) cassée(s) au total.")
    for a in resultat["alertes"]:
        print(f"  [{a['gravite']:<6}] {a['titre']} — {a['detail'][:70]}")

    # Marqueurs des livrables de cette session : pas un bug, un simple constat
    # de ce qui est en ligne ou encore en bac à sable. Sert à ne pas perdre le
    # fil de ce qui reste à déployer sans avoir à s'en souvenir soi-même.
    LIVRABLES = {
        "menu.html": [
            ("toggleModePro", "Mode sobre du menu"),
            ("taikoRecap", "Encart du jour (récap Taiko)"),
        ],
        "outils.html": [
            ("toggleAtelierPro", "Mode sobre de la trousse à outils"),
        ],
        "GrillePaye/index.html": [
            ("suivi-public.json", "Onglet « Nos sources »"),
        ],
    }
    for fichier, marqueurs in LIVRABLES.items():
        chemin = os.path.join(args.racine, fichier)
        if not os.path.isfile(chemin):
            continue
        contenu = open(chemin, encoding="utf-8", errors="replace").read()
        for marqueur, nom in marqueurs:
            if marqueur in contenu:
                continue  # en ligne -- plus rien à signaler, ce n'était qu'un suivi de déploiement
            resultat["alertes"].append({
                "categorie": "livrable-session",
                "gravite": "basse",
                "titre": f"{nom} : pas encore en ligne",
                "detail": f"Marqueur « {marqueur} » absent de {fichier}.",
            })

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"\nÉcrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
