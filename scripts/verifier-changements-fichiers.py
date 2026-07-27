#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-CHANGEMENTS-FICHIERS.PY — un fichier de l'app, du guide ou de
MonLegiTexte a-t-il changé depuis le dernier run, que ce changement soit
prévu ou non ?

Différent de tout le reste de ce tableau de bord : ça ne juge rien (pas de
"c'est périmé", pas de "cette citation est fausse") -- ça dit juste "ceci a
changé depuis la dernière fois", pour repérer une modification qu'on
n'attendait pas autant qu'une qu'on attendait.

Principe identique à verifier-contenu-articles.py, appliqué aux fichiers
plutôt qu'aux articles de loi : hash de chaque fichier, comparé à l'empreinte
du run précédent, stockée dans son propre fichier persistant. Premier run
pour un fichier donné : on enregistre juste la référence, sans alerter --
comparer à du vide flaguerait tout, à tort.

MonLegiTexte est différent des deux autres : c'est un site déployé, pas un
dépôt cloné. Un seul fetch réseau (comme verifier-noindex-live.py), pas des
centaines de fichiers -- isolé du reste pour la même raison qu'ailleurs
dans ce tableau de bord : une panne réseau ponctuelle ne doit pas se
confondre avec un vrai changement de contenu.

USAGE
    python3 verifier-changements-fichiers.py --hs /chemin/hs --guide /chemin/Guide --empreintes /chemin/empreintes-fichiers.json --monlegitexte-url https://... --json sortie.json
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error


def hash_fichier(chemin):
    try:
        with open(chemin, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return None


def fichiers_a_surveiller(racine_hs, racine_guide):
    """Renvoie {cle: chemin_absolu} -- la clé identifie le fichier de façon
    stable d'un run à l'autre, indépendamment d'où les dépôts sont clonés."""
    cibles = {}

    # Fichiers HTML à la racine de l'app : découverts automatiquement, pas
    # une liste à tenir à jour -- un nouveau fichier racine (ex. si taiko.html
    # est un jour déployé) apparaît tout seul au run suivant.
    for nom in sorted(os.listdir(racine_hs)):
        chemin = os.path.join(racine_hs, nom)
        if os.path.isfile(chemin) and nom.endswith(".html"):
            cibles[f"app:{nom}"] = chemin

    # Fichiers non-HTML spécifiques à la racine -- ceux-là ne se multiplient
    # pas au même rythme qu'un module ou une page, liste explicite qui reste
    # simple à tenir à jour si un nouveau venait à s'ajouter un jour.
    for nom in ["manifest.json", "sw.js", "articles-loi.js", "legi-ref.js"]:
        chemin = os.path.join(racine_hs, nom)
        if os.path.isfile(chemin):
            cibles[f"app:{nom}"] = chemin

    # Les modules : un dossier à la racine avec un index.html EST un module,
    # sauf GrillePaye (suivi séparément juste après) -- même principe, aucune
    # liste à tenir à jour pour un nouveau module.
    for nom in sorted(os.listdir(racine_hs)):
        chemin_dossier = os.path.join(racine_hs, nom)
        if nom == "GrillePaye" or not os.path.isdir(chemin_dossier):
            continue
        chemin = os.path.join(chemin_dossier, "index.html")
        if os.path.isfile(chemin):
            cibles[f"app:module:{nom}"] = chemin

    # GrillePaye -- séparé, changé souvent par ce même travail de veille.
    for nom in ["index.html", "ccn-data.json"]:
        chemin = os.path.join(racine_hs, "GrillePaye", nom)
        if os.path.isfile(chemin):
            cibles[f"app:grillepaye:{nom}"] = chemin

    # Les 105 outils.
    for chemin in sorted(glob.glob(os.path.join(racine_hs, "outils", "*.html"))):
        nom = os.path.basename(chemin)
        cibles[f"app:outil:{nom}"] = chemin

    # Le guide -- ~980 pages, une empreinte chacune.
    if racine_guide:
        for chemin in sorted(glob.glob(os.path.join(racine_guide, "*.html"))):
            nom = os.path.basename(chemin)
            cibles[f"guide:{nom}"] = chemin

    return cibles


def contenu_monlegitexte(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "veille-perso-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--guide", help="optionnel")
    ap.add_argument("--empreintes", required=True,
                     help="Fichier persistant qui garde le hash de chaque fichier d'un run à l'autre")
    ap.add_argument("--monlegitexte-url", default="https://monlegitexte.heuressupfrance.workers.dev/",
                     help="URL de MonLegiTexte en production, pour détecter un changement de contenu réel")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    args = ap.parse_args()

    empreintes_avant = {}
    if os.path.isfile(args.empreintes):
        try:
            empreintes_avant = json.load(open(args.empreintes, encoding="utf-8"))
        except Exception as e:
            print(f"empreintes-fichiers.json illisible, traité comme premier run : {e}", file=sys.stderr)

    resultat = {"module": "changements-fichiers", "alertes": []}
    empreintes_apres = {}
    n_verifies, n_premiere_fois, n_changes = 0, 0, 0

    cibles = fichiers_a_surveiller(args.hs, args.guide)
    for cle, chemin in cibles.items():
        h = hash_fichier(chemin)
        if h is None:
            continue
        n_verifies += 1
        empreintes_apres[cle] = h
        avant = empreintes_avant.get(cle)
        if avant is None:
            n_premiere_fois += 1
            continue
        if avant != h:
            n_changes += 1
            resultat["alertes"].append({
                "categorie": "fichier-modifie",
                "gravite": "basse",
                "titre": f"{cle} : a changé depuis le dernier run",
                "detail": "Constat neutre, pas un jugement -- peut être un changement voulu "
                          "(session de travail) ou une modification à vérifier si elle est "
                          "inattendue.",
            })

    # MonLegiTexte : un seul fetch, isolé du reste.
    contenu = contenu_monlegitexte(args.monlegitexte_url)
    if contenu is not None:
        h_mlt = hashlib.sha256(contenu).hexdigest()[:16]
        n_verifies += 1
        empreintes_apres["monlegitexte:site"] = h_mlt
        avant_mlt = empreintes_avant.get("monlegitexte:site")
        if avant_mlt is None:
            n_premiere_fois += 1
        elif avant_mlt != h_mlt:
            n_changes += 1
            resultat["alertes"].append({
                "categorie": "fichier-modifie",
                "gravite": "basse",
                "titre": "MonLegiTexte (site déployé) : a changé depuis le dernier run",
                "detail": "Constat neutre -- déploiement récent probable, à vérifier si inattendu.",
            })

    with open(args.empreintes, "w", encoding="utf-8") as f:
        json.dump(empreintes_apres, f, ensure_ascii=False, indent=2)

    print(f"{n_verifies} fichier(s)/page(s) vérifié(s) ({n_premiere_fois} pour la première fois -- "
          f"empreinte enregistrée, pas d'alerte).")
    print(f"{n_changes} changement(s) détecté(s).")
    for a in resultat["alertes"][:20]:
        print(f"  {a['titre']}")
    if len(resultat["alertes"]) > 20:
        print(f"  ... et {len(resultat['alertes'])-20} de plus")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
