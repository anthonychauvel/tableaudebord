#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONSTRUIRE-DONNEES.PY — orchestrateur : lance les 4 vérificateurs et
fusionne leurs sorties JSON en un seul fichier consommé par le tableau de bord.

USAGE
    python3 construire-donnees.py --hs /chemin/vers/hs --droit /chemin/vers/droit --out ../donnees.json
"""
import argparse, json, os, re, subprocess, sys
from datetime import datetime, timezone

ICI = os.path.dirname(os.path.abspath(__file__))

_compteur_appels = [0]

def lancer(script, args_liste):
    # Un compteur, pas seulement le nom du script : verifier-liens.py est
    # appelé 3 fois (app, outils, guide) dans ce même run. Un nom de fichier
    # dérivé uniquement du script aurait fait que chaque appel écrase le
    # précédent — fonctionnellement correct tant que tout s'exécute en
    # séquence et qu'on relit juste après chaque appel, mais fragile au
    # moindre changement d'ordre. Un compteur élimine le risque proprement.
    _compteur_appels[0] += 1
    tmp = f"/tmp/_veille_{_compteur_appels[0]:02d}_" + script.replace(".py", "") + ".json"
    cmd = [sys.executable, os.path.join(ICI, script)] + args_liste + ["--json", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"--- {script} ---")
    print(r.stdout.strip())
    if r.returncode != 0:
        print(f"  ERREUR : {r.stderr[-500:]}", file=sys.stderr)
        return {"module": script, "alertes": [], "erreur": r.stderr[-300:]}
    if not os.path.isfile(tmp):
        return {"module": script, "alertes": []}
    return json.load(open(tmp, encoding="utf-8"))

def fusionner(*resultats):
    """Combine les alertes de plusieurs vérificateurs dans une même section
    (ex. Grilles CCN = fraîcheur + santé, dans le même onglet du tableau).

    Dédoublonne par IDCC : si deux vérifications différentes signalent le
    MÊME IDCC (ex. "sous le SMIC" ET "grille de plus de 12 mois"), on ne
    montre qu'UNE alerte, pas deux lignes qui se suivent pour la même
    convention. C'est ce qui noyait le tableau -- 5 CCN en double sur la
    seule section Grilles. La gravité retenue est la plus forte des deux,
    et les détails sont combinés pour ne rien perdre.
    """
    ordre_gravite = {"haute": 3, "moyenne": 2, "basse": 1}
    toutes = []
    for r in resultats:
        toutes.extend(r.get("alertes", []))

    par_idcc = {}   # idcc -> alerte fusionnée
    autres = []     # alertes sans IDCC identifiable, gardées telles quelles
    for a in toutes:
        m = re.search(r"\bIDCC\s+(\d{1,5})\b", a.get("titre", ""))
        if not m:
            autres.append(a)
            continue
        idcc = m.group(1)
        if idcc not in par_idcc:
            par_idcc[idcc] = dict(a)
            continue
        # Déjà une alerte pour cet IDCC : on combine.
        existante = par_idcc[idcc]
        if ordre_gravite.get(a.
