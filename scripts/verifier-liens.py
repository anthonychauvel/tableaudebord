#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-LIENS.PY — liens internes cassés (hrefs, pas seulement les assets)

verifier-modules.py vérifie déjà les images/scripts. Ce script fait la même
chose pour les LIENS (href vers une autre page du même site) — un mécanisme
différent car un lien cassé ne casse rien visuellement (pas d'image manquante
à l'œil), il attend qu'un utilisateur clique pour se révéler. C'est ce qui a
permis de trouver outils/outils.html : un doublon orphelin de outils.html,
avec ses propres liens relatifs faux, jamais visité par personne — inoffensif,
mais bon à nettoyer.

Portée volontairement limitée aux liens SÛRS à vérifier : relatifs, vers un
fichier .html du même dépôt. Les ancres (#section), les liens externes
(http/https) et les protocoles spéciaux (mailto:, tel:) sont ignorés.

LES PAGES D'APERÇU SONT HORS PORTÉE (--ignorer)
Le guide contient des pages qui montrent à quoi ressemble l'APPLICATION :
apercu.html, apercu-sommaire.html, apercu-nouveautes.html. Elles recopient la
structure de l'app — « heures/index.html », « outils/module-astreintes.html »,
« module6/index.html » — pour donner envie de la télécharger. Ces fichiers
n'existent évidemment pas dans le dépôt du guide, et c'est voulu : ces boutons
ne sont pas censés fonctionner depuis le guide, dont le seul rôle est de mener
au téléchargement.

Les compter comme des liens cassés produisait 118 alertes, soit la TOTALITÉ de
la section « Guide SEO » du tableau de bord. Une section entièrement fausse
apprend à ne plus la lire, et le jour où un vrai lien casse dans le guide, il
se perd au milieu du bruit.

USAGE
    python3 verifier-liens.py --cible /chemin/vers/hs/outils --json sortie.json
    python3 verifier-liens.py --cible /chemin/vers/Guide --ignorer 'apercu*.html' --json sortie.json
"""
import argparse
import fnmatch
import json
import os
import re

HREF = re.compile(r'href="([^"#][^"]*\.html)"')
JS_NAV = re.compile(r"location\.href\s*=\s*'([^'#][^']*\.html)'")


def liens_casses_fichier(chemin, racine_site):
    dossier = os.path.dirname(chemin)
    html = open(chemin, encoding="utf-8", errors="replace").read()
    casses = set()
    for motif in (HREF, JS_NAV):
        for m in motif.finditer(html):
            ref = m.group(1)
            if re.match(r"^https?://|^mailto:|^tel:", ref):
                continue
            cible = os.path.normpath(os.path.join(dossier, ref))
            if not os.path.isfile(cible):
                casses.add(ref)
    return casses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cible", required=True, help="Dossier à parcourir (récursif)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    ap.add_argument("--nom-module", default="liens-internes")
    ap.add_argument("--ignorer", action="append", default=[], metavar="MOTIF",
                     help="Motif de fichier à ne pas contrôler, façon glob "
                          "(ex. 'apercu*.html'). Répétable.")
    args = ap.parse_args()

    resultat = {"module": args.nom_module, "alertes": []}
    n_fichiers = 0
    n_ignores = 0

    for base, _, fichiers in os.walk(args.cible):
        for nom in fichiers:
            if not nom.endswith(".html"):
                continue
            chemin = os.path.join(base, nom)
            # Le motif est testé sur le nom seul ET sur le chemin relatif, pour
            # pouvoir viser soit une famille de fichiers ('apercu*.html'), soit
            # un dossier entier ('vitrine/*').
            rel_test = os.path.relpath(chemin, args.cible).replace(os.sep, "/")
            if any(fnmatch.fnmatch(nom, m) or fnmatch.fnmatch(rel_test, m)
                   for m in args.ignorer):
                n_ignores += 1
                continue
            n_fichiers += 1
            # Chemin RELATIF à la racine scannée : deux fichiers peuvent porter
            # le même nom dans des dossiers différents (outils.html existe à la
            # fois à la racine et, par erreur, dans outils/) — le nom seul ne
            # suffirait pas à savoir lequel des deux est en cause.
            chemin_rel = os.path.relpath(chemin, args.cible)
            casses = liens_casses_fichier(chemin, args.cible)
            for ref in casses:
                resultat["alertes"].append({
                    "categorie": "lien-interne-casse",
                    "gravite": "moyenne",
                    "titre": f"{chemin_rel} : lien vers « {ref} » introuvable",
                    "detail": "Ce lien ne se révèle qu'au clic — rien ne le signale visuellement.",
                })

    print(f"{n_fichiers} fichiers parcourus, {len(resultat['alertes'])} lien(s) cassé(s)"
          + (f" ({n_ignores} fichier(s) hors portée : {', '.join(args.ignorer)})."
             if n_ignores else "."))
    for a in resultat["alertes"][:15]:
        print(f"  {a['titre']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"\nÉcrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
