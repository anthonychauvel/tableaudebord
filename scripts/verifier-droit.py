#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-DROIT.PY — lit les audits déjà produits par le fonds (5 sources)

Ce script ne refait AUCUN diff lui-même : chaque workflow du fonds "droit"
compare déjà le commit courant au précédent et écrit le résultat dans SON
PROPRE fichier d'audit. Reproduire ce diff ici demanderait un historique git
complet (le clone superficiel utilisé pour les autres contrôles n'en a pas)
pour, au final, refaire un travail déjà fait et déjà fiable.

Ce script se contente donc de lire le dernier run de CHAQUE source et d'en
tirer ce qui mérite une alerte :
  - un run a-t-il eu lieu récemment (chaque source a son propre rythme) ?
  - le dernier run a-t-il trouvé un VRAI changement (pas du simple
    rattrapage/routine) ? C'est la seule distinction qui compte.

SOURCES (18/08/2026 — le fonds a grandi au-delà du seul aspirateur France) :
  - index.json                       : aspirateur principal (lundi/jeudi)
  - index-oit.json                   : OIT, texte JORF (vendredi)
  - index-cedh.json                  : CEDH, texte HUDOC (mercredi)
  - index-cgfp-civil-penal.json      : CGFP + Code civil/pénal (vendredi)
  - index-combler-manques.json       : fiches minimales, tous corpus (samedi)

Chaque nouvelle source écrit son entrée via ecrire_audit.py (dans le fonds
droit) -- champ "changements_droit", alors que l'aspirateur principal utilise
"total_changements". Les deux noms sont vérifiés ici (comme le fait déjà
index.html côté appli) plutôt que d'imposer un seul nom.

USAGE
    python3 verifier-droit.py --fonds /chemin/vers/droit --json sortie.json
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veille_commun import charger_mots_cles, themes_trouves, texte_de, idcc_de_l_appli  # noqa: E402

# (nom_fichier, label humain, cadence normale en jours, marge avant alerte)
SOURCES = [
    ("index.json",                  "Aspirateur principal (France)",        3,  5),
    ("index-oit.json",              "OIT",                                  7,  12),
    ("index-cedh.json",             "CEDH",                                 7,  12),
    ("index-cgfp-civil-penal.json", "CGFP + Code civil/pénal",              7,  12),
    ("index-combler-manques.json",  "Comblement des manques",               7,  12),
]


def nombre_changements(entree):
    """Vérifie les deux noms de champ possibles selon la source qui a écrit
    l'entrée -- l'aspirateur principal utilise total_changements,
    ecrire_audit.py (utilisé par les 4 nouvelles sources) utilise
    changements_droit. Même logique défensive que _majSansChangement() côté
    appli (index.html), pour ne pas imposer un seul nom aux deux générateurs."""
    if isinstance(entree.get("changements_droit"), (int, float)):
        return int(entree["changements_droit"])
    return int(entree.get("total_changements", 0) or 0)


def verifier_source(dossier_audits, nom_fichier, label, cadence_jours, marge_jours, alertes):
    chemin = os.path.join(dossier_audits, nom_fichier)
    if not os.path.isfile(chemin):
        print(f"[{label}] {nom_fichier} absent -- ce workflow n'a peut-être "
              f"jamais tourné, ou pas encore poussé son 1er audit.")
        return

    try:
        runs = json.load(open(chemin, encoding="utf-8"))
    except Exception as e:
        alertes.append({
            "categorie": "audit-illisible",
            "gravite": "moyenne",
            "titre": f"[{label}] Fichier d'audit illisible",
            "detail": f"« {chemin} » n'a pas pu être lu comme JSON valide ({e}).",
        })
        return

    if not runs:
        print(f"[{label}] {nom_fichier} vide -- aucun run enregistré.")
        return

    dernier = runs[0]
    print(f"[{label}] Dernier run : {dernier.get('date','?')} {dernier.get('heure','')}")
    print(f"  {dernier.get('resume','')}")

    try:
        d = datetime.strptime(dernier["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age_jours = (datetime.now(timezone.utc) - d).days
    except Exception:
        age_jours = None

    if age_jours is not None and age_jours > marge_jours:
        alertes.append({
            "categorie": "run-en-retard",
            "gravite": "moyenne",
            "titre": f"[{label}] Dernier run vieux de {age_jours} jours",
            "detail": f"Cadence normale : environ tous les {cadence_jours} jours. "
                      f"{age_jours} jours sans run suggère un cycle manqué ou le "
                      f"workflow en échec silencieux.",
        })

    total = nombre_changements(dernier)
    if total > 0:
        filtre = CONTEXTE.get("filtre")
        if filtre is None:
            # Sans filtre (appel à l'ancienne) : comportement d'origine.
            alertes.append(alerte_brute(label, dernier, total))
        else:
            filtre.traiter_run(dossier_audits, label, dernier, total, alertes)
    else:
        print(f"  Aucun changement réel signalé.")


def alerte_brute(label, dernier, total):
    return {
        "categorie": "changement-reel",
        "gravite": "haute",
        "titre": f"[{label}] {total} changement(s) réel(s) détecté(s)",
        "detail": f"Run du {dernier.get('date','?')} {dernier.get('heure','')} — voir "
                  f"audits/{dernier.get('fichier','?')} pour le détail. Ceci n'est pas "
                  f"du rattrapage : quelque chose a effectivement changé, à distinguer "
                  f"d'un simple complément de collecte.",
    }


# ── Filtre « est-ce que ça me concerne ? » (30/09/2026) ─────────────────────
# L'alerte « [CGFP + Code civil/pénal] 21 changement(s) réel(s) » tombait en
# gravité haute à chaque passage, alors que :
#   1. « 21 fichiers mis à jour » veut souvent dire « 21 fichiers re-téléchargés »
#      (un champ technique de Légifrance change à chaque téléchargement, pas le
#      texte) ;
#   2. même un vrai changement (harcèlement, Code pénal) ne concerne pas
#      forcément les sujets de l'appli — et MonLegiTexte se met à jour tout seul
#      pour ses utilisateurs.
# On ouvre donc chaque fichier cité par l'audit et on ne garde que ceux dont le
# TEXTE a vraiment changé (empreinte gardée dans empreintes-droit.json) ET qui
# touchent un sujet suivi : article cité par l'écosystème, convention de
# l'appli, ou mot-clé de mots-cles.json. Le reste est compté, jamais affiché.
_RX_CHEMIN = re.compile(r"(output/[\w./-]+\.json)")
GARDER_JOURS = 14


class FiltrePertinence:
    def __init__(self, fonds, themes, cites, idcc_appli, memoire):
        self.fonds, self.themes, self.cites = fonds, themes, cites
        self.idcc_appli, self.memoire = idcc_appli, memoire
        self.aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.ignores = 0

    def _sujet(self, chemin, texte):
        parties = chemin.split("/")
        nom = os.path.splitext(parties[-1])[0]
        if len(parties) >= 3 and parties[1] in ("code-travail", "code-travail-complet") and nom in self.cites.get("CT", ()):
            return "article cité par l'écosystème"
        if len(parties) >= 3 and parties[1] in ("code-secu", "code-secu-complet") and nom in self.cites.get("CSS", ()):
            return "article cité par l'écosystème"
        if len(parties) >= 3 and parties[1] == "ccn" and nom in self.idcc_appli:
            return f"convention de l'appli (IDCC {nom})"
        trouves = themes_trouves(texte, self.themes, largeur=120)
        if trouves:
            return "; ".join(f"{e} {n} (« {x} »)" for n, e, x, _ in trouves)
        return None

    def traiter_run(self, dossier_audits, label, dernier, total, alertes):
        try:
            md = open(os.path.join(dossier_audits, dernier.get("fichier", "")), encoding="utf-8").read()
        except Exception:
            md = ""
        chemins = sorted(set(_RX_CHEMIN.findall(md)))
        mem = self.memoire.setdefault("fichiers", {})
        retenus = []
        for chemin in chemins:
            complet = os.path.join(self.fonds, chemin)
            try:
                d = json.load(open(complet, encoding="utf-8"))
            except Exception:
                continue
            texte = " ".join(texte_de(d).split())
            h = hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]
            m = mem.get(chemin)
            if m is None:
                mem[chemin] = {"hash": h, "texte": texte[:1500]}      # départ, pas d'alerte
                continue
            if m.get("hash") != h:
                mem[chemin] = {"hash": h, "texte": texte[:1500], "change_le": self.aujourd_hui,
                               "avant": m.get("texte", "")}
        # Les changements récents (fenêtre de GARDER_JOURS) de CETTE source,
        # qu'ils aient été vus à ce passage ou à un précédent.
        limite = (datetime.now(timezone.utc) - timedelta(days=GARDER_JOURS)).strftime("%Y-%m-%d")
        for chemin in chemins:
            m = mem.get(chemin) or {}
            if not m.get("change_le") or m["change_le"] < limite:
                continue
            sujet = self._sujet(chemin, m.get("texte", ""))
            if sujet:
                retenus.append((chemin, m, sujet))
            else:
                self.ignores += 1
        print(f"  {len(chemins)} fichier(s) listé(s) par l'audit, {len(retenus)} vrai(s) "
              f"changement(s) sur tes sujets.")
        if not retenus:
            return
        lignes = []
        for chemin, m, sujet in retenus[:15]:
            lignes.append(f"• {chemin} — {sujet} (changé le {m['change_le']})"
                          + (f"\n  AVANT — {m['avant'][:250]}…" if m.get("avant") else "")
                          + f"\n  APRÈS — {m.get('texte', '')[:250]}…")
        if len(retenus) > 15:
            lignes.append(f"… et {len(retenus) - 15} autre(s).")
        alertes.append({
            "categorie": "changement-reel",
            "gravite": "haute",
            "titre": f"[{label}] {len(retenus)} changement(s) sur tes sujets",
            "detail": (f"Run du {dernier.get('date','?')} {dernier.get('heure','')} "
                       f"(audits/{dernier.get('fichier','?')}). Seuls les textes qui ont "
                       f"VRAIMENT changé et qui touchent tes sujets sont listés :\n\n"
                       + "\n\n".join(lignes)),
            "date_texte": max(m["change_le"] for _, m, _ in retenus),
        })


CONTEXTE = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonds", required=True, help="Racine du dépôt droit (le fonds)")
    ap.add_argument("--json", help="Écrire le résultat en JSON à ce chemin")
    ap.add_argument("--mots-cles", help="mots-cles.json : active le filtre « mes sujets »")
    ap.add_argument("--empreintes-articles", help="empreintes-articles.json (articles cités)")
    ap.add_argument("--hs", help="Racine de l'appli (conventions de l'appli)")
    ap.add_argument("--memoire", help="empreintes-droit.json : texte des fichiers d'un passage à l'autre")
    args = ap.parse_args()

    filtre = None
    if args.mots_cles and args.memoire:
        themes, _ = charger_mots_cles(args.mots_cles)
        cites = {"CT": set(), "CSS": set()}
        try:
            for cle in json.load(open(args.empreintes_articles, encoding="utf-8")):
                code, _, num = cle.partition(":")
                cites.setdefault(code, set()).add(num)
        except Exception:
            pass
        try:
            memoire = json.load(open(args.memoire, encoding="utf-8"))
        except Exception:
            memoire = {}
        filtre = FiltrePertinence(args.fonds, themes, cites,
                                  idcc_de_l_appli(args.hs) if args.hs else set(), memoire)
    CONTEXTE["filtre"] = filtre

    resultat = {"module": "monlegitexte-droit", "alertes": []}
    dossier_audits = os.path.join(args.fonds, "audits")

    if not os.path.isdir(dossier_audits):
        resultat["alertes"].append({
            "categorie": "audit-introuvable",
            "gravite": "haute",
            "titre": "Aucun dossier d'audits trouvé",
            "detail": f"« {dossier_audits} » est absent. Le workflow aspirateur "
                      f"a-t-il déjà tourné au moins une fois sur ce dépôt ?",
        })
        print("dossier audits/ introuvable.")
        if args.json:
            json.dump(resultat, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 0

    for nom_fichier, label, cadence, marge in SOURCES:
        verifier_source(dossier_audits, nom_fichier, label, cadence, marge, resultat["alertes"])
        print()

    if filtre:
        with open(args.memoire, "w", encoding="utf-8") as f:
            json.dump(filtre.memoire, f, ensure_ascii=False, indent=1)
        resultat["hors_sujet_ignores"] = filtre.ignores
        print(f"{filtre.ignores} changement(s) réel(s) hors de tes sujets, non affiché(s).")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"Écrit dans {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
