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
        if ordre_gravite.get(a.get("gravite"), 0) > ordre_gravite.get(existante.get("gravite"), 0):
            existante["gravite"] = a["gravite"]
            existante["titre"] = a["titre"]  # garder le titre de l'alerte la plus grave
        d1 = existante.get("detail", "")
        d2 = a.get("detail", "")
        if d2 and d2 not in d1:
            existante["detail"] = (d1 + "\n\n" + d2).strip()
        # Un lien éventuel (ex. lien MonLegiTexte) ne doit pas être perdu.
        if a.get("lien") and not existante.get("lien"):
            existante["lien"] = a["lien"]

    return {"alertes": autres + list(par_idcc.values())}


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
    remonter et comparer n'importe quand, pas seulement au run d'avant.

    Un hébergement statique (Cloudflare Pages, GitHub Pages) ne permet pas de
    lister le contenu d'un dossier depuis le navigateur -- sans un index
    explicite, le tableau de bord n'aurait aucun moyen de savoir quels
    instantanés existent pour proposer de les consulter.
    """
    dossier = os.path.join(dossier_veille, "historique")
    os.makedirs(dossier, exist_ok=True)
    horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    nom_fichier = f"{horodatage}.json"
    chemin = os.path.join(dossier, nom_fichier)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=2)

    chemin_index = os.path.join(dossier, "index.json")
    index = []
    if os.path.isfile(chemin_index):
        try:
            index = json.load(open(chemin_index, encoding="utf-8"))
        except Exception:
            index = []
    total = sum(len(s.get("alertes", [])) for s in sortie.get("sections", []))
    par_gravite = {"haute": 0, "moyenne": 0, "basse": 0}
    for s in sortie.get("sections", []):
        for a in s.get("alertes", []):
            if a.get("gravite") in par_gravite:
                par_gravite[a["gravite"]] += 1
    index.append({
        "fichier": nom_fichier,
        "genere": sortie.get("genere"),
        "total": total,
        "par_gravite": par_gravite,
        "nouvelles_alertes": sortie.get("nouvelles_alertes", 0),
    })
    with open(chemin_index, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return chemin


# --- Pertinence des textes JORF/ACCO pour la veille des grilles -------------
# Un texte qui parle de salaires/minima est probablement l'avenant qui lève
# une alerte de grille. Un arrêté qui se contente d'ÉTENDRE ou d'AGRÉER un
# avenant, sans nouveaux minima, est du bruit pour la veille des grilles : on
# le compte mais on n'en fait pas une alerte prioritaire. C'est ce qui
# remontait ~200 « textes parus » en gravité haute sans aucun minimum neuf.
_MOTS_SALAIRE = ("salaire", "salariale", "salarial", "rémunération", "remuneration",
                 "minima", "minimum", "minimaux", "barème", "bareme", "grille de salaire",
                 "grille salariale", "valeur du point", "valeur de point",
                 "pouvoir d'achat", "augmentation", "traitement", "rmh", "rag", "rmg")
_MOTS_EXTENSION = ("extension", "élargissement", "elargissement",
                   "agrément", "agrement", "agréé", "agree")
_MOIS_FR = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
            "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
            "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}


def classer_texte(titre):
    """salaire / extension / autre. Le mot de salaire l'emporte : un « arrêté
    portant extension d'un avenant relatif aux salaires » reste pertinent."""
    t = titre.lower()
    if any(mot in t for mot in _MOTS_SALAIRE):
        return "salaire"
    if any(mot in t for mot in _MOTS_EXTENSION):
        return "extension"
    return "autre"


def date_iso_du_titre(titre):
    """Lit « du J MOIS AAAA » dans un titre -> AAAA-MM-JJ, sinon None.
    Accepte l'ordinal « 1er / 2ème » (fréquent : « à compter du 1er juin »)."""
    m = re.search(r"\bdu\s+(\d{1,2})(?:er|ère|ème|e|nd)?\s+([a-zûéèà]+)\s+(20\d\d)", titre.lower())
    if m and m.group(2) in _MOIS_FR:
        return f"{int(m.group(3)):04d}-{_MOIS_FR[m.group(2)]:02d}-{int(m.group(1)):02d}"
    return None


def croiser_en_memoire(sections, dossier_jorf, dossier_acco):
    """Relie les CCN qui ATTENDENT réellement un texte (grille périmée ou à
    créer) aux avenants SALAIRES fraîchement aspirés. Ne lit plus la section
    « âge » (une référence qui vieillit sans successeur au fonds n'attend rien)
    et ne remonte plus les arrêtés d'extension seuls (aucun minimum nouveau)."""
    import glob as _glob

    # 1) IDCC en alerte ACTIONNABLE : uniquement les grilles périmées ou à
    #    créer. Une grille « ancienne / sous SMIC / sans date » ou une simple
    #    alerte d'âge n'est pas quelque chose qu'un avenant vient lever -> on
    #    ne la croise pas (c'était la 1re source de faux positifs, ~200 IDCC
    #    de la section âge injectés ici).
    ACTIONNABLES = ("grille-perimee", "grille-a-creer")
    en_alerte = {}
    for section in sections:
        if section.get("id") != "grilles":
            continue
        for a in section.get("alertes", []):
            if a.get("categorie") not in ACTIONNABLES:
                continue
            m = re.search(r"\bIDCC\s+(\d{1,5})\b", a.get("titre", ""))
            if m:
                en_alerte.setdefault(m.group(1), a.get("titre", ""))
    if not en_alerte:
        return {"alertes": []}

    # 2) Titres des textes JORF/ACCO récupérés.
    textes = []
    for dossier, source in ((dossier_jorf, "Journal Officiel"), (dossier_acco, "accord d'entreprise")):
        if not dossier or not os.path.isdir(dossier):
            continue
        for chemin in _glob.glob(os.path.join(dossier, "*.json")):
            base = os.path.basename(chemin)
            if base.startswith("_"):
                continue
            try:
                d = json.load(open(chemin, encoding="utf-8"))
            except Exception:
                continue
            titre = d.get("titre") or ""
            if titre:
                textes.append((os.path.splitext(base)[0], titre, source))

    # 3) Croisement : IDCC cherché dans les titres (nombre entier), puis TRI
    #    par pertinence salaire. On n'émet une alerte que s'il reste un texte
    #    qui n'est pas un pur arrêté d'extension.
    alertes = []
    for idcc, titre_alerte in sorted(en_alerte.items(), key=lambda kv: int(kv[0])):
        corr = [(titre, source) for tid, titre, source in textes
                if re.search(r"(?<!\d)" + re.escape(idcc) + r"(?!\d)", titre)]
        if not corr:
            continue
        pertinents, autres, extensions = [], [], []
        for titre, source in corr:
            cls = classer_texte(titre)
            (pertinents if cls == "salaire"
             else autres if cls == "autre" else extensions).append((titre, source))
        if not pertinents and not autres:
            # Rien que des extensions/agréments -> pas de minima nouveaux,
            # on ne crée pas d'alerte (le bruit qu'on veut éliminer).
            continue
        a_montrer = pertinents + autres
        lignes = [f"• 💶 [{s}] {t[:90]}" for t, s in pertinents[:5]]
        lignes += [f"• [{s}] {t[:90]}" for t, s in autres[:5]]
        if extensions:
            lignes.append(f"• (+ {len(extensions)} arrêté(s) d'extension/agrément, sans nouveaux minima)")
        # Date du texte pertinent le plus récent (extensions exclues) -> permet
        # la coupure par date d'exceptions.json (mode « jusqu_au »). SANS cette
        # date, le mode jus_qu_au ne matchait jamais et la coupure au 10/08
        # était inopérante sur cette section (bug corrigé).
        dates = [d for d in (date_iso_du_titre(t) for t, _ in a_montrer) if d]
        alerte = {
            "categorie": "texte-pour-ccn-en-alerte",
            "gravite": "haute" if pertinents else "moyenne",
            "titre": (f"IDCC {idcc} : {'avenant salaires' if pertinents else 'texte'} "
                      f"paru pour cette CCN en attente"),
            "detail": (f"Cette convention attend une grille (« {titre_alerte} »), et un "
                       f"texte vient de paraître qui la mentionne — probablement de quoi "
                       f"lever l'alerte :\n" + "\n".join(lignes)),
        }
        if dates:
            alerte["date_texte"] = max(dates)
        alertes.append(alerte)
    return {"alertes": alertes}


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

    # Âge de la référence : reproduit le bandeau "Plus de 12 mois" que l'app
    # montre elle-même aux utilisateurs -- indépendant de verifier-fraicheur.py
    # (qui compare au fonds, pas à un seuil absolu), pour ne jamais perdre de
    # vue ce qu'un utilisateur resté sur l'onglet Référence voit vraiment,
    # même quand une région est à jour par ailleurs.
    sections.append({"id": "age", "titre": "Âge de la référence (3 mois et 12 mois)",
        **lancer("verifier-age-reference.py", ["--hs", args.hs, "--fonds", os.path.join(args.droit, "output", "ccn")])})

    # Croisement CCN en alerte ↔ textes JORF/ACCO fraîchement aspirés.
    # C'est LA fonctionnalité clé : si une convention est déjà en alerte et
    # qu'un texte vient de paraître qui la mentionne, on le remonte en tête,
    # en gravité haute -- probablement l'avenant qui lève l'alerte.
    # Se calcule sur les sections DÉJÀ construites (grilles + âge), pas sur un
    # fichier -- donnees.json n'existe pas encore à ce stade. On insère le
    # résultat EN TÊTE pour qu'il soit la première chose vue.
    croisement = croiser_en_memoire(
        sections,
        os.path.join(args.droit, "output", "jorf"),
        os.path.join(args.droit, "output", "acco"),
    )
    if croisement["alertes"]:
        sections.insert(0, {"id": "croisement",
                            "titre": "🔔 Textes parus pour une CCN en attente",
                            **croisement})

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

    def _exception_couvre(e, a):
        # Catégorie : toujours exacte.
        if e["categorie"] != a.get("categorie"):
            return False
        # Clé : sous-chaîne du titre. Une clé vide vaut « toute la catégorie »
        # (utile pour une règle de coupure globale par date).
        if e.get("cle") and e["cle"] not in a.get("titre", ""):
            return False
        # Mode « jusqu_au » : ne masque que si le texte de référence de
        # l'alerte est ANTÉRIEUR ou ÉGAL à la date d'acquittement. Un texte
        # paru APRÈS cette date réapparaît tout seul — c'est ce qui permet de
        # solder le backlog à une date donnée sans masquer les nouveautés.
        # Sans date_texte sur l'alerte, une exception « jusqu_au » ne matche
        # pas (on préfère montrer que masquer à l'aveugle).
        if e.get("mode") == "jusqu_au":
            dt = a.get("date_texte")
            return bool(dt) and dt <= e.get("date", "")
        # Sinon : exception simple, masquage permanent (comportement d'origine).
        return True

    for s in sections:
        gardees = []
        for a in s.get("alertes", []):
            matché = next((e for e in exceptions if _exception_couvre(e, a)), None)
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

    # Données de consultation (majoration, contingent, source) -- pas des
    # alertes, un fichier séparé. Node, pas Python : besoin de charger le
    # VRAI fichier de règles de l'app pour que ça ne puisse jamais diverger
    # de son vrai comportement.
    chemin_regles = os.path.join(os.path.dirname(args.out), "ccn-regles.json")
    r = subprocess.run(
        ["node", os.path.join(ICI, "extraire-regles-ccn.js"), "--hs", args.hs, "--out", chemin_regles],
        capture_output=True, text=True)
    print(f"--- extraire-regles-ccn.js ---\n{r.stdout.strip()}")
    if r.returncode != 0:
        print(f"ÉCHEC extraire-regles-ccn.js : {r.stderr.strip()}", file=sys.stderr)

if __name__ == "__main__":
    main()
