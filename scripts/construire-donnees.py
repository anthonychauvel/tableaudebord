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
    (ex. Grilles CCN = fraîcheur + santé, dans le même onglet du tableau)."""
    toutes = []
    for r in resultats:
        toutes.extend(r.get("alertes", []))
    return {"alertes": toutes}


def bumper_service_worker(chemin_sw):
    """Change le numéro de version du cache à CHAQUE run, sans exception.

    Une donnée fraîche dans donnees.json ne suffit pas toujours : la coquille
    de l'app (index.html, manifest.json, sw.js lui-même) reste en cache tant
    que la version ne change pas. C'est exactement le bug "rien ne change"
    qui est revenu plusieurs fois cette session sur l'app principale — la
    même classe de bug, mais ici sur veille-perso elle-même. Le corriger une
    fois pour toutes en l'automatisant plutôt que de compter sur d'y penser
    à chaque fois.
    """
    contenu = open(chemin_sw, encoding="utf-8").read()
    nouvelle_version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    contenu2, n = re.subn(r'const CACHE = "veille-perso-[^"]*"',
                          f'const CACHE = "veille-perso-{nouvelle_version}"', contenu)
    if n == 0:
        print("ATTENTION : la ligne 'const CACHE' n'a pas été trouvée dans sw.js "
              "-- version non changée.", file=sys.stderr)
        return None
    open(chemin_sw, "w", encoding="utf-8").write(contenu2)
    return nouvelle_version


def cle_stable(alerte):
    """Identifiant d'une alerte qui survit aux détails qui changent tout
    seuls d'un jour à l'autre -- "dépassée de 210 jours" devient "211" le
    lendemain sans que le problème lui-même ait bougé. Le titre suit presque
    partout le patron "IDENTIFIANT : description" (IDCC, nom de fichier,
    numéro d'article) -- ce qui est avant le ':' est stable, ce qui suit
    souvent pas. Une comparaison sur le titre entier marquerait ces alertes
    comme nouvelles chaque jour, à tort.
    """
    titre = alerte.get("titre", "")
    identifiant = titre.split(" : ", 1)[0].strip() if " : " in titre else titre.strip()
    return f"{alerte.get('categorie', '')}::{identifiant}"


def marquer_nouveautes(sections, chemin_donnees_precedent):
    """Ajoute nouveau=true/false sur chaque alerte. Sans historique antérieur
    (premier run), rien n'est marqué nouveau -- comparer à du vide rendrait
    TOUT rouge dès le premier lancement, ce qui n'aide personne."""
    cles_avant = set()
    if os.path.isfile(chemin_donnees_precedent):
        try:
            precedent = json.load(open(chemin_donnees_precedent, encoding="utf-8"))
            for s in precedent.get("sections", []):
                for a in s.get("alertes", []):
                    cles_avant.add(cle_stable(a))
        except Exception as e:
            print(f"donnees.json précédent illisible, traité comme premier run : {e}", file=sys.stderr)

    n_nouvelles = 0
    for s in sections:
        for a in s.get("alertes", []):
            a["nouveau"] = bool(cles_avant) and cle_stable(a) not in cles_avant
            if a["nouveau"]:
                n_nouvelles += 1
    return n_nouvelles


def sauver_historique(dossier_veille, sortie):
    """Un instantané complet à chaque run, jamais écrasé -- pour pouvoir
    remonter et comparer n'importe quand, pas seulement au run d'avant."""
    dossier = os.path.join(dossier_veille, "historique")
    os.makedirs(dossier, exist_ok=True)
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    chemin = os.path.join(dossier, f"{horodatage}.json")
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=2)
    return chemin


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--droit", required=True)
    ap.add_argument("--guide", help="Racine du dépôt Guide (optionnel)")
    ap.add_argument("--out", default="../donnees.json")
    args = ap.parse_args()

    sections = []
    sections.append({"id": "grilles", "titre": "Grilles CCN",
        **fusionner(
            lancer("adaptateur-grilles.py", ["--racine", args.hs, "--fonds", args.droit]),
            lancer("adaptateur-sante-grilles.py", ["--racine", args.hs,
                   "--idcc-suivis", os.path.join(args.droit, "idcc_list.txt")]),
        )})
    sections.append({"id": "droit", "titre": "MonLegiTexte",
        **lancer("verifier-droit.py", ["--fonds", args.droit])})
    sections.append({"id": "modules", "titre": "8 modules",
        **fusionner(
            lancer("verifier-modules.py", ["--racine", args.hs]),
            lancer("adaptateur-coherence-ccn.py", ["--racine", args.hs,
                   "--dares", os.path.join(args.droit, "ccn",
                   "Dares_Suivi_Historique_convention_collective_Juin2026.xlsx")]),
            lancer("verifier-liens.py", ["--cible", args.hs, "--nom-module", "liens-app"]),
        )})
    sections.append({"id": "outils", "titre": "105 outils",
        **fusionner(
            lancer("verifier-outils.py", ["--racine", args.hs, "--fonds", args.droit]),
            lancer("verifier-liens.py", ["--cible", os.path.join(args.hs, "outils"),
                   "--nom-module", "liens-outils"]),
        )})
    if args.guide:
        sections.append({"id": "guide", "titre": "Guide SEO",
            **fusionner(
                lancer("verifier-guide.py", ["--guide", args.guide, "--hs", args.hs]),
                lancer("verifier-liens.py", ["--cible", args.guide, "--nom-module", "liens-guide"]),
            )})
    else:
        sections.append({"id": "guide", "titre": "Guide SEO", "alertes": [],
            "non_construit": True})

    # Croisement : citations juridiques du guide + des 8 modules contre le fonds.
    # Distinct de la vérification des outils (verifier-outils.py, incluse dans
    # la section "outils" ci-dessus) : celle-ci connaît le code (travail/sécu) de
    # chaque article grâce à articles-loi.js, alors que le guide et les modules
    # citent en texte brut, sans cette information.
    citations_args = ["--hs", args.hs, "--fonds", args.droit]
    if args.guide:
        citations_args += ["--guide", args.guide]
    sections.append({"id": "citations", "titre": "Citations juridiques (guide + modules)",
        **lancer("verifier-citations-ecosysteme.py", citations_args)})

    # Syntaxe JS : la seule vérification qui détecte "cette page ne charge plus
    # DU TOUT", pas seulement "cette donnée est périmée". Couvre la racine, les
    # 8 modules, GrillePaye et les 105 outils.
    sections.append({"id": "syntaxe", "titre": "Syntaxe JS (page entière cassée)",
        **lancer("verifier-syntaxe-js.py", ["--hs", args.hs])})

    # Structure du guide et des outils : ce qui restait explicitement noté
    # "hors périmètre" dans les tout premiers lots de ce tableau de bord.
    structure_alertes = fusionner(
        lancer("verifier-outils-orphelins.py", ["--hs", args.hs]),
    )
    if args.guide:
        structure_alertes = fusionner(
            {"alertes": structure_alertes["alertes"]},
            lancer("verifier-jsonld.py", ["--guide", args.guide]),
        )
    sections.append({"id": "structure", "titre": "Structure (JSON-LD, outils orphelins)",
        **structure_alertes})

    # MonLegiTexte en direct : le seul contrôle de tout ce tableau de bord qui
    # fait un vrai appel réseau vers le site déployé, plutôt que de lire un
    # fichier. Volontairement isolé dans sa propre section : une panne réseau
    # ponctuelle ne doit pas se confondre avec les autres catégories.
    sections.append({"id": "noindex", "titre": "MonLegiTexte — noindex en direct",
        **lancer("verifier-noindex-live.py", [])})

    # Contenu des articles : le trou signalé -- un article peut rester "en
    # vigueur" tout en changeant de texte (seuils, montants, formulation).
    # Empreinte persistante dans son propre fichier, PAS dans donnees.json
    # (qui, lui, est entièrement régénéré à chaque run -- l'empreinte doit
    # survivre d'un run à l'autre, donc vivre ailleurs).
    contenu_args = ["--hs", args.hs, "--fonds", args.droit,
                    "--empreintes", os.path.join(os.path.dirname(args.out), "empreintes-articles.json")]
    if args.guide:
        contenu_args += ["--guide", args.guide]
    sections.append({"id": "contenu", "titre": "Contenu des articles cités",
        **lancer("verifier-contenu-articles.py", contenu_args)})

    # Changements de fichiers : constat neutre, pas un jugement -- signale
    # tout ce qui a changé depuis le dernier run, app + guide + MonLegiTexte
    # confondus, que ce soit voulu ou non. Empreinte dans son propre fichier.
    changements_args = ["--hs", args.hs,
                         "--empreintes", os.path.join(os.path.dirname(args.out), "empreintes-fichiers.json")]
    if args.guide:
        changements_args += ["--guide", args.guide]
    sections.append({"id": "changements", "titre": "Fichiers modifiés (app, guide, MonLegiTexte)",
        **lancer("verifier-changements-fichiers.py", changements_args)})

    # Exceptions manuelles : un fichier que TOI seul édites (directement sur
    # GitHub, pas par ce script) pour dire "celle-ci, je l'ai déjà vérifiée,
    # arrête de me la remontrer". Sans lui, chaque run réaffiche indéfiniment
    # tout ce qui reste bloqué, même ce que tu as déjà consciemment tranché.
    exceptions = []
    chemin_exceptions = os.path.join(os.path.dirname(args.out), "exceptions.json")
    if os.path.isfile(chemin_exceptions):
        try:
            exceptions = [e for e in json.load(open(chemin_exceptions, encoding="utf-8"))
                          if "categorie" in e and "cle" in e]
        except Exception as e:
            print(f"exceptions.json illisible, ignoré : {e}", file=sys.stderr)

    n_ignorees = 0
    for s in sections:
        gardees = []
        for a in s.get("alertes", []):
            matché = next((e for e in exceptions
                           if e["categorie"] == a.get("categorie") and e["cle"] in a.get("titre", "")),
                          None)
            if matché:
                n_ignorees += 1
            else:
                gardees.append(a)
        s["alertes"] = gardees

    n_nouvelles = marquer_nouveautes(sections, args.out)

    sortie = {
        "genere": datetime.now(timezone.utc).isoformat(),
        "exceptions_appliquees": n_ignorees,
        "nouvelles_alertes": n_nouvelles,
        "sections": sections,
    }
    sauver_historique(os.path.dirname(args.out), sortie)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=2)
    total = sum(len(s.get("alertes", [])) for s in sections)
    print(f"\n{total} alerte(s) au total ({n_ignorees} ignorée(s) via exceptions.json, "
          f"{n_nouvelles} nouvelle(s) depuis le dernier run), écrit dans {args.out}")

    chemin_sw = os.path.join(os.path.dirname(args.out), "sw.js")
    if os.path.isfile(chemin_sw):
        nouvelle = bumper_service_worker(chemin_sw)
        if nouvelle:
            print(f"sw.js : cache renouvelé -> veille-perso-{nouvelle}")

if __name__ == "__main__":
    main()
