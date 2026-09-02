#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_TEST-VEILLE-PERTINENCE.PY — vérifie, SANS le corpus, la logique anti-faux-
positifs ajoutée à la veille :
  1. classer_texte : salaire / extension / autre (le salaire l'emporte)
  2. date_iso_du_titre : lecture « du J MOIS AAAA »
  3. croiser_en_memoire :
       - ne lit QUE les grilles périmées/à créer (pas la section âge, pas les
         états informatifs)
       - supprime les CCN dont TOUS les textes sont des arrêtés d'extension
       - pose date_texte (pour que la coupure par date fonctionne)
  4. _exception_couvre (mode jusqu_au) : masque avant la date, garde après.

Lancer :  python3 _test-veille-pertinence.py
"""
import importlib.util
import os

ICI = os.path.dirname(os.path.abspath(__file__))


def charger(nom_fichier, nom_module):
    spec = importlib.util.spec_from_file_location(nom_module, os.path.join(ICI, nom_fichier))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cd = charger("construire-donnees.py", "construire_donnees")

ok = 0
ko = 0


def check(nom, condition):
    global ok, ko
    if condition:
        ok += 1
        print(f"  ✅ {nom}")
    else:
        ko += 1
        print(f"  ❌ {nom}")


print("1) classer_texte")
check("avenant salaires -> salaire",
      cd.classer_texte("Avenant n° 42 du 3 mars 2026 relatif aux salaires minima") == "salaire")
check("arrêté d'extension d'un avenant SALAIRES -> salaire (le salaire gagne)",
      cd.classer_texte("Arrêté du 5 mai 2026 portant extension d'un avenant relatif aux salaires (n° 1580)") == "salaire")
check("arrêté d'extension classification -> extension (aucun minimum)",
      cd.classer_texte("Arrêté du 5 mai 2026 portant extension d'un avenant relatif aux classifications (n° 1580)") == "extension")
check("agrément seul -> extension",
      cd.classer_texte("Arrêté du 1er juin 2026 portant agrément d'un accord (n° 405)") == "extension")
check("titre neutre -> autre",
      cd.classer_texte("Avenant n° 7 du 12 février 2026 (n° 1424)") == "autre")

print("2) date_iso_du_titre")
check("du 3 mars 2026 -> 2026-03-03",
      cd.date_iso_du_titre("Avenant du 3 mars 2026 relatif aux salaires") == "2026-03-03")
check("du 1er juin 2026 -> 2026-06-01 (le « er » n'empêche pas)",
      cd.date_iso_du_titre("Accord du 1er juin 2026") == "2026-06-01")
check("sans date -> None",
      cd.date_iso_du_titre("Avenant relatif aux salaires") is None)


print("3) croiser_en_memoire (source + pertinence + date_texte)")

# Sections synthétiques : une périmée, une à créer, une sous-SMIC (informative),
# et une alerte d'ÂGE. Seules les 2 premières doivent être croisées.
sections = [
    {"id": "grilles", "alertes": [
        {"categorie": "grille-perimee", "titre": "IDCC 1580 : grille de référence dépassée"},
        {"categorie": "grille-a-creer", "titre": "IDCC 7027 : aucune grille, un texte existe au fonds"},
        {"categorie": "grille-sous-smic", "titre": "IDCC 4444 : 1er niveau sous le SMIC"},
    ]},
    {"id": "age", "alertes": [
        {"categorie": "reference-plus-3-mois", "titre": "IDCC 9999 : référence de plus de 3 mois"},
    ]},
]

# Faux dossiers JORF/ACCO : on court-circuite la lecture disque en écrivant des
# fichiers temporaires. Plus simple : on teste la fonction via un petit dossier.
import json
import tempfile
tmp = tempfile.mkdtemp()
jorf = os.path.join(tmp, "jorf"); os.makedirs(jorf)
acco = os.path.join(tmp, "acco"); os.makedirs(acco)


def ecrire(dossier, nom, titre):
    json.dump({"titre": titre}, open(os.path.join(dossier, nom), "w", encoding="utf-8"))


# 1580 : un avenant salaires (mars) + un arrêté d'extension (mai) -> alerte,
#        gravité haute, date_texte = date du texte PERTINENT (mars), pas mai.
ecrire(jorf, "a.json", "Avenant du 3 mars 2026 relatif aux salaires (n° 1580)")
ecrire(jorf, "b.json", "Arrêté du 20 mai 2026 portant extension d'un avenant relatif aux classifications (n° 1580)")
# 7027 : UNIQUEMENT un arrêté d'extension -> AUCUNE alerte (pas de minima neufs).
ecrire(jorf, "c.json", "Arrêté du 10 avril 2026 portant extension d'un avenant (n° 7027)")
# 4444 (sous-SMIC) et 9999 (âge) : des textes existent, mais ces CCN ne sont
# pas des grilles en attente -> ne doivent JAMAIS être croisées.
ecrire(jorf, "d.json", "Avenant du 1er juin 2026 relatif aux salaires (n° 4444)")
ecrire(jorf, "e.json", "Avenant du 1er juin 2026 relatif aux salaires (n° 9999)")

res = cd.croiser_en_memoire(sections, jorf, acco)
titres = {a["titre"]: a for a in res["alertes"]}

check("1580 (périmée) remonte", any("IDCC 1580" in t for t in titres))
check("7027 (extension seule) NE remonte PAS", not any("IDCC 7027" in t for t in titres))
check("4444 (sous-SMIC) NE remonte PAS", not any("IDCC 4444" in t for t in titres))
check("9999 (âge) NE remonte PAS", not any("IDCC 9999" in t for t in titres))

a1580 = next((a for t, a in titres.items() if "IDCC 1580" in t), None)
check("1580 gravité haute (texte salaire présent)", a1580 and a1580["gravite"] == "haute")
check("1580 date_texte = 2026-03-03 (le pertinent, PAS l'extension de mai)",
      a1580 and a1580.get("date_texte") == "2026-03-03")
check("1580 détail marque l'extension comme sans minima",
      a1580 and "sans nouveaux minima" in a1580["detail"])


print("4) coupure par date (mode jusqu_au) — le bug corrigé")
# On reconstruit la logique _exception_couvre telle qu'elle vit dans
# construire-donnees.py (fonction locale à main) pour la tester isolément.
def exception_couvre(e, a):
    if e["categorie"] != a.get("categorie"):
        return False
    if e.get("cle") and e["cle"] not in a.get("titre", ""):
        return False
    if e.get("mode") == "jusqu_au":
        dt = a.get("date_texte")
        return bool(dt) and dt <= e.get("date", "")
    return True

coupure = {"categorie": "texte-pour-ccn-en-alerte", "cle": "", "mode": "jusqu_au", "date": "2026-08-10"}
avant = {"categorie": "texte-pour-ccn-en-alerte", "titre": "IDCC X", "date_texte": "2026-03-03"}
apres = {"categorie": "texte-pour-ccn-en-alerte", "titre": "IDCC Y", "date_texte": "2026-08-31"}
sans_date = {"categorie": "texte-pour-ccn-en-alerte", "titre": "IDCC Z"}
check("texte AVANT le 10/08 -> masqué", exception_couvre(coupure, avant) is True)
check("texte APRÈS le 10/08 -> conservé (réapparaît)", exception_couvre(coupure, apres) is False)
check("sans date_texte -> conservé (on préfère montrer) — c'était le bug : avant, "
      "TOUTES les alertes de croisement étaient sans date_texte",
      exception_couvre(coupure, sans_date) is False)

print()
print(f"RÉSULTAT : {ok} OK, {ko} KO")
raise SystemExit(1 if ko else 0)
