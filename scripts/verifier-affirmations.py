#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-AFFIRMATIONS.PY — une phrase FAUSSE connue est-elle encore écrite quelque part ?

Le trou comblé (13/10/2026) : les autres vérifications partent d'un ARTICLE cité
(est-il abrogé ? son texte a-t-il changé ?). Une phrase comme « la faute lourde
prive des congés payés » ne cite aucun article : aucun contrôle ne pouvait la
voir, et elle est restée dans le guide plusieurs années après sa suppression
par la loi. Ici, on tient une liste de phrases fausses (affirmations-fausses.json)
et on cherche chacune dans tout le guide, l'appli, les modules et les outils.

Chaque règle : motifs (expressions régulières sur le texte sans accents),
'sauf' (si présent autour de la phrase, elle est déjà corrigée), correction, source.
Le script ne corrige rien : il signale la page, la phrase et ce qui est vrai.

USAGE
    python3 verifier-affirmations.py --guide /chemin/Guide --hs /chemin/hs \
        --regles affirmations-fausses.json --json sortie.json
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from veille_commun import normaliser
except Exception:                                         # noqa: BLE001
    import unicodedata

    def normaliser(t):
        t = unicodedata.normalize("NFD", t or "")
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", t.lower().replace("’", "'"))

TAG = re.compile(r"<[^>]+>")
ENTITES = {"&nbsp;": " ", "&amp;": "&", "&#39;": "'", "&apos;": "'", "&quot;": '"', "&rsquo;": "'", "&lt;": "<", "&gt;": ">"}
DOSSIERS_IGNORES = {"node_modules", "fonts", "images", "icons", "assets", "releves", "historique", ".git", "Gg", "Dd", "Fg", "Ff"}
EXTENSIONS = (".html", ".js")
TAILLE_MAX = 3_000_000


def fichiers(racine, recursif):
    if not racine or not os.path.isdir(racine):
        return
    if not recursif:
        for c in sorted(glob.glob(os.path.join(racine, "*.html"))):
            yield c
        return
    for dossier, sous, noms in os.walk(racine):
        sous[:] = [d for d in sous if d not in DOSSIERS_IGNORES]
        for n in sorted(noms):
            if n.endswith(EXTENSIONS):
                yield os.path.join(dossier, n)


def texte_lisible(chemin):
    try:
        if os.path.getsize(chemin) > TAILLE_MAX:
            return ""
        brut = open(chemin, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""
    if chemin.endswith(".html"):
        brut = TAG.sub(" ", brut)
    for k, v in ENTITES.items():
        brut = brut.replace(k, v)
    return normaliser(brut)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--guide")
    ap.add_argument("--hs")
    ap.add_argument("--regles", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    try:
        regles = [r for r in json.load(open(args.regles, encoding="utf-8")) if r.get("id") and r.get("motifs")]
    except Exception as e:                                # noqa: BLE001
        print(f"Règles illisibles : {e}", file=sys.stderr)
        regles = []
    compilees = []
    for r in regles:
        try:
            compilees.append((r, [re.compile(normaliser(m), re.S) for m in r["motifs"]],
                              re.compile(normaliser(r["sauf"])) if r.get("sauf") else None))
        except re.error as e:
            print(f"Règle « {r['id']} » ignorée : expression invalide ({e})", file=sys.stderr)

    cibles = [(args.guide, False, "guide"), (args.hs, True, "appli")]
    resultat = {"module": "affirmations-fausses", "alertes": []}
    n_fichiers = 0
    for racine, recursif, zone in cibles:
        for chemin in fichiers(racine, recursif):
            n_fichiers += 1
            txt = texte_lisible(chemin)
            if not txt:
                continue
            rel = os.path.relpath(chemin, racine)
            for regle, motifs, sauf in compilees:
                for rx in motifs:
                    trouve = None
                    for m in rx.finditer(txt):
                        if sauf and sauf.search(txt[max(0, m.start() - 100):m.end() + 250]):
                            continue
                        trouve = m
                        break
                    if trouve:
                        extrait = txt[max(0, trouve.start() - 60):trouve.end() + 80]
                        resultat["alertes"].append({
                            "categorie": "affirmation-fausse",
                            "gravite": "haute",
                            "titre": f"{rel} : {regle.get('titre') or regle['id']}",
                            "detail": (f"Fichier ({zone}) : {rel}\n"
                                       f"Phrase trouvée : « …{extrait}… »\n\n"
                                       f"Ce qui est vrai : {regle.get('correction', '?')}\n"
                                       f"Source : {regle.get('source', '?')}\n"
                                       f"Règle : {regle['id']} (affirmations-fausses.json)"),
                            "regle": regle["id"],
                        })
                        break          # une alerte par règle et par fichier
    print(f"{n_fichiers} fichier(s) lus, {len(compilees)} règle(s), {len(resultat['alertes'])} alerte(s).")
    for a in resultat["alertes"][:15]:
        print(f"  [{a['gravite']}] {a['titre']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
