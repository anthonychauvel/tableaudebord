#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VEILLE-REGLES-OFFICIELLES.PY — une règle de calcul, une formule ou un montant
officiel a-t-il changé ?

Les calculs de l'appli sont justes. Ce qui peut les rendre faux, c'est le
monde qui bouge : un nouveau plafond de la Sécurité sociale, un SMIC
revalorisé, une exonération des heures sup modifiée, un préavis ou une
indemnité de licenciement changés pour une convention. Deux administrations
publient leurs règles de calcul sous une forme lisible par un programme
(publicodes), versionnées sur npm :

  CDTN   @socialgouv/modeles-social : les 8 simulateurs du Code du travail
         numérique (préavis de démission / licenciement / retraite, indemnités
         de licenciement, rupture conventionnelle, départ à la retraite,
         précarité, heures pour rechercher un emploi), avec les règles
         particulières de ~40 conventions collectives.
  URSSAF modele-social (mon-entreprise.urssaf.fr) : SMIC, plafond de la
         Sécurité sociale, cotisations, exonération des heures sup, etc.

Principe : quand une nouvelle version paraît, on télécharge l'ANCIENNE (celle
vue au passage précédent) et la NOUVELLE, et on compare règle par règle. Le
CDTN publie 5 à 9 versions par mois, souvent sans toucher aux règles : seules
les règles réellement modifiées remontent, avec l'avant et l'après. La mémoire
(regles-officielles.json) ne garde que le numéro de version vu et les alertes
des 45 derniers jours. Premier passage : version de départ enregistrée, sans
alerte.

USAGE
    python3 veille-regles-officielles.py --hs /chemin/hs --memoire ../regles-officielles.json --json sortie.json
"""
import argparse
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veille_commun import normaliser, idcc_de_l_appli  # noqa: E402

REGISTRE = "https://registry.npmjs.org/"
RETENTION_JOURS = 45
MAX_LIGNES = 25

# Simulateur CDTN -> outil(s) de l'appli à revoir si ses règles changent.
OUTILS_CDTN = {
    "indemnite-licenciement": ("Indemnité de licenciement", "Fin de contrat, Comparatif ruptures"),
    "rupture-conventionnelle": ("Rupture conventionnelle", "Rupture conventionnelle, Comparatif ruptures"),
    "preavis-demission": ("Préavis de démission", "Préavis"),
    "preavis-licenciement": ("Préavis de licenciement", "Préavis"),
    "preavis-retraite": ("Préavis de départ / mise à la retraite", "Retraite, Préavis"),
    "indemnite-retraite": ("Indemnité de départ / mise à la retraite", "Retraite, Fin de contrat"),
    "indemnite-precarite": ("Prime de précarité (fin de CDD)", "Prime de précarité"),
    "heures-recherche-emploi": ("Heures pour rechercher un emploi", "Préavis"),
}

# URSSAF : seules les règles qui touchent l'appli. Motif -> (thème, outils).
SUJETS_URSSAF = [
    (r"\bsmic\b", "SMIC", "GrillePaye, Convertisseur paie, Net · Brut"),
    (r"plafond securite sociale|\bpss\b", "Plafond de la Sécurité sociale", "Net · Brut · Coût employeur, Bulletin décrypté"),
    (r"heures supplementaires|heures complementaires", "Heures sup / complémentaires", "Modules heures et paye, Net · Brut"),
    (r"titres?-restaurant", "Titres-restaurant", "Titres-restaurant"),
    (r"avantages? en nature", "Avantages en nature", "Avantages en nature"),
    (r"frais professionnels|indemnites? kilometriques?|forfait mobilites", "Frais professionnels", "Carnet de frais pro, Transport & Mobilité, Forfait Mobilités"),
    (r"activite partielle", "Activité partielle", "Activité partielle"),
    (r"apprenti|contrat de professionnalisation", "Alternance", "Alternance"),
    (r"indemnite de licenciement|rupture conventionnelle|indemnite de depart|indemnite de fin de contrat|precarite", "Indemnités de rupture", "Fin de contrat, Rupture conventionnelle"),
    (r"conges? payes?", "Congés payés", "Congés payés"),
    (r"reduction generale|allegement", "Réduction générale des cotisations", "Net · Brut · Coût employeur"),
    (r"taux horaire|salaire brut|remuneration \. brut", "Salaire brut", "Convertisseur paie, Net · Brut"),
]

SOURCES = [
    {"cle": "cdtn", "paquet": "@socialgouv/modeles-social", "nom": "Code du travail numérique"},
    {"cle": "urssaf", "paquet": "modele-social", "nom": "URSSAF (mon-entreprise)"},
]


def http_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "veille"}), timeout=60) as r:
        return json.loads(r.read())


def telecharger(paquet, version):
    """Le paquet npm d'une version donnée, en mémoire (quelques Mo)."""
    meta = http_json(f"{REGISTRE}{paquet}/{version}")
    with urllib.request.urlopen(meta["dist"]["tarball"], timeout=120) as r:
        return tarfile.open(fileobj=io.BytesIO(r.read()), mode="r:gz")


def regles_cdtn(tgz):
    """{« simulateur :: règle » : définition} pour les 8 simulateurs."""
    out = {}
    for m in tgz.getmembers():
        nom = os.path.basename(m.name)
        g = re.fullmatch(r"modeles-([\w-]+)\.json", nom)
        if not g or "/lib/modeles/" not in m.name:
            continue
        d = json.load(tgz.extractfile(m))
        sim = g.group(1)
        for k, v in d.items():
            # {idcc: {règle: déf}} ou {"base": {règle: déf}} : un bloc de règles
            if isinstance(v, dict) and (k.isdigit() or all(" . " in x or x == "contrat salarié" for x in v)):
                for r, dv in v.items():
                    out[f"{sim} :: {r}"] = dv
            else:
                out[f"{sim} :: {k}"] = v
    return out


def regles_urssaf(tgz):
    for m in tgz.getmembers():
        if m.name.endswith("dist/index.js"):
            s = tgz.extractfile(m).read().decode("utf-8")
            g = re.search(r'export const json = (?:/\*@__PURE__\*/ )?("(?:[^"\\]|\\.)*")', s, re.S)
            if g:
                return json.loads(json.loads(g.group(1)))
    return {}


def compact(v, n=350):
    t = json.dumps(v, ensure_ascii=False, sort_keys=True)
    return t if len(t) <= n else t[:n] + "…"


def idcc_des_conventions(regles):
    """« transports routiers » -> "16", depuis les règles racines des conventions."""
    out = {}
    for k, v in regles.items():
        _, _, r = k.partition(" :: ")
        g = re.fullmatch(r"contrat salarié \. convention collective \. ([^.]+?)", r)
        if g and isinstance(v, dict):
            idcc = (v.get("cdtn") or {}).get("idcc")
            if idcc:
                out[g.group(1).strip()] = str(idcc)
    return out


# Champs d'AFFICHAGE : les reformuler ne change aucun calcul. Les ignorer évite
# de signaler chaque retouche de question ou de description.
IGNORES = {"question", "description", "titre", "titre global", "note", "notes", "références",
           "cdtn", "suggestions", "icônes", "résumé", "acronyme", "aide", "experimental",
           "avertissement", "type", "par défaut"}


def feuilles(v, chemin=""):
    """{chemin: valeur} de toutes les valeurs d'une règle, sans les champs d'affichage."""
    out = {}
    if isinstance(v, dict):
        for k, x in v.items():
            if k in IGNORES:
                continue
            out.update(feuilles(x, f"{chemin}.{k}" if chemin else k))
    elif isinstance(v, list):
        # Repérer chaque élément par son CONTENU, pas par sa position : quand
        # l'URSSAF ajoute le SMIC de juin en tête de liste, tous les éléments se
        # décalent d'un cran -- repérés par position, ils paraîtraient tous changés.
        for i, x in enumerate(v):
            if isinstance(x, dict) and ("si" in x or "sinon" in x):
                cle = f"si {x['si']}" if "si" in x else "sinon"
                out.update(feuilles({k: y for k, y in x.items() if k != "si"}, f"{chemin}[{cle}]"))
            elif isinstance(x, (str, int, float, bool)) or x is None:
                out[f"{chemin}[{x}]"] = "présent"
            else:
                out.update(feuilles(x, f"{chemin}[{i}]"))
    else:
        out[chemin or "valeur"] = v
    return out


def comparer(avant, apres):
    """[(règle, [(chemin, avant, après)])] : seulement les VALEURS qui ont changé
    (montants, taux, durées, formules, conditions)."""
    diff = []
    for k in sorted(set(avant) | set(apres)):
        fa, fb = feuilles(avant.get(k)) if k in avant else {}, feuilles(apres.get(k)) if k in apres else {}
        ch = [(c, fa.get(c), fb.get(c)) for c in sorted(set(fa) | set(fb)) if fa.get(c) != fb.get(c)]
        if ch:
            diff.append((k, ch))
    return diff


def lisible(chemin):
    """« variations[si date >= 06/2026].alors » -> « à partir du 06/2026 ». Le
    chemin technique d'une valeur dans la règle, dit en français."""
    morceaux = []
    for seg in re.findall(r"\[[^\]]*\]|[^.\[\]]+", chemin):
        seg = seg.strip()
        if seg.startswith("["):
            c = seg[1:-1]
            m = re.fullmatch(r"si date >= (\d\d/\d{4})", c)
            if m:
                morceaux.append(f"à partir du {m.group(1)}")
            elif c == "sinon":
                morceaux.append("autres cas")
            elif c.startswith("si "):
                morceaux.append("si " + c[3:].split(" . ")[-1])
            elif c != "présent":
                morceaux.append(c)
        elif seg not in ("variations", "alors", "sinon", "valeur", "avec", ""):
            morceaux.append(seg)
    return " · ".join(morceaux) or "valeur"


def ligne(k, changements):
    lignes = [f"• {k}"]
    for c, a, b in changements[:6]:
        c = lisible(c)
        val = lambda v: "" if v == "présent" else " : " + compact(v, 160).strip('"')
        if a is None:
            lignes.append(f"  ＋ {c}{val(b)}")
        elif b is None:
            lignes.append(f"  － {c}{val(a)}")
        else:
            lignes.append(f"  {c} : {compact(a, 160).strip(chr(34))} → {compact(b, 160).strip(chr(34))}")
    if len(changements) > 6:
        lignes.append(f"  … et {len(changements) - 6} autre(s) valeur(s)")
    return "\n".join(lignes)


_MONTANT = re.compile(r"\d[\d .,]*\s*(?:€|%|mois|an|ans|jours?|semaines?|heures?)", re.I)


def touche_un_montant(changements):
    """Un montant, un taux, une durée ou un coefficient a bougé (et pas seulement
    une condition ou un libellé)."""
    for c, a, b in changements:
        for v in (a, b):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return True
            if v is not None and _MONTANT.search(str(v) + " " + c):
                return True
    return False


def alertes_cdtn(diff, v_av, v_ap, idcc_appli, jour, conv):
    """Une alerte par simulateur. conv : nom de convention -> IDCC, pour savoir
    si une convention touchée est dans l'appli."""
    alertes = []
    par_sim = {}
    for k, ch in diff:
        sim, _, regle = k.partition(" :: ")
        par_sim.setdefault(sim, []).append((regle, ch))
    for sim, liste in sorted(par_sim.items()):
        liste.sort(key=lambda x: not touche_un_montant(x[1]))     # montants d'abord
        nom, outils = OUTILS_CDTN.get(sim, (sim, "?"))
        conv_touchees, general = set(), False
        for regle, _ch in liste:
            g = re.match(r"contrat salarié \. convention collective \. ([^.]+?)(?: \.|$)", regle)
            if g:
                conv_touchees.add(g.group(1).strip())
            else:
                general = True
        idcc = {conv[c] for c in conv_touchees if c in conv}
        dans_appli = sorted(i for i in idcc if i in idcc_appli)
        montant = any(touche_un_montant(ch) for _, ch in liste)
        gravite = "haute" if montant and (general or dans_appli) else "moyenne"
        qui = ("règle générale (Code du travail)" if general else "") + \
              ((" + " if general else "") + "conventions : " + ", ".join(
                  f"{c} (IDCC {conv[c]})" if c in conv else c for c in sorted(conv_touchees))[:300]
               if conv_touchees else "")
        detail = (f"Le Code du travail numérique a publié la version {v_ap} de ses règles (vue au "
                  f"passage précédent : {v_av}). {len(liste)} règle(s) du simulateur « {nom} » ont "
                  f"changé — {qui}.\n\nOutil(s) de l'appli à revoir : {outils}."
                  + (f"\nConventions de l'appli concernées : IDCC {', '.join(dans_appli)}." if dans_appli else "")
                  + "\n\n" + "\n\n".join(ligne(r, ch) for r, ch in liste[:MAX_LIGNES])
                  + (f"\n\n… et {len(liste) - MAX_LIGNES} autre(s)." if len(liste) > MAX_LIGNES else ""))
        alertes.append({
            "categorie": "regle-officielle-modifiee",
            "gravite": gravite,
            "titre": f"CDTN — {nom} ({v_ap}) : {len(liste)} règle(s) modifiée(s)",
            "detail": detail,
            "lien": "https://code.travail.gouv.fr/outils",
            "fonds": "Règles",
            "theme": nom,
            "date_texte": jour,
            "_id": f"cdtn:{sim}:{v_ap}",
        })
    return alertes


def sujet_urssaf(regle, definition):
    titre = definition.get("titre") if isinstance(definition, dict) else None
    n = normaliser(f"{regle} {titre or ''}")
    for motif, theme, outils in SUJETS_URSSAF:
        if re.search(motif, n):
            return theme, outils
    return None


def alertes_urssaf(diff, v_av, v_ap, jour):
    par_theme = {}
    for k, ch in diff:
        s = sujet_urssaf(k, None)
        if s:
            par_theme.setdefault(s, []).append((k, ch))
    alertes = []
    for (theme, outils), liste in sorted(par_theme.items()):
        liste.sort(key=lambda x: not touche_un_montant(x[1]))     # montants d'abord
        montant = any(touche_un_montant(ch) for _, ch in liste)
        alertes.append({
            "categorie": "regle-officielle-modifiee",
            "gravite": "haute" if montant else "moyenne",
            "titre": f"URSSAF — {theme} ({v_ap}) : {len(liste)} règle(s) modifiée(s)",
            "detail": (f"L'URSSAF a publié la version {v_ap} de ses règles de calcul (vue au passage "
                       f"précédent : {v_av}). Règles « {theme} » modifiées — un montant, un taux ou une "
                       f"condition a peut-être changé.\n\nOutil(s) de l'appli à revoir : {outils}.\n\n"
                       + "\n\n".join(ligne(r, ch) for r, ch in liste[:MAX_LIGNES])
                       + (f"\n\n… et {len(liste) - MAX_LIGNES} autre(s)." if len(liste) > MAX_LIGNES else "")),
            "lien": "https://mon-entreprise.urssaf.fr/",
            "fonds": "Règles",
            "theme": theme,
            "date_texte": jour,
            "_id": f"urssaf:{theme}:{v_ap}",
        })
    return alertes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--memoire", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        memoire = json.load(open(args.memoire, encoding="utf-8"))
    except Exception:
        memoire = {}
    idcc_appli = idcc_de_l_appli(args.hs)
    nouvelles, erreurs = [], []

    for src in SOURCES:
        vu = memoire.setdefault(src["cle"], {})
        try:
            dernier = http_json(f"{REGISTRE}{src['paquet']}/latest")["version"]
        except Exception as e:
            erreurs.append(f"{src['nom']} : registre npm injoignable ({e})")
            continue
        avant = vu.get("version")
        if avant is None:
            vu.update({"version": dernier, "depuis": jour})
            print(f"{src['nom']} : version de départ {dernier} enregistrée, pas d'alerte.")
            continue
        if avant == dernier:
            print(f"{src['nom']} : toujours en {dernier}, rien à comparer.")
            continue
        try:
            lire = regles_cdtn if src["cle"] == "cdtn" else regles_urssaf
            r_av, r_ap = lire(telecharger(src["paquet"], avant)), lire(telecharger(src["paquet"], dernier))
        except Exception as e:
            erreurs.append(f"{src['nom']} : comparaison {avant} → {dernier} impossible ({e})")
            continue
        diff = comparer(r_av, r_ap)
        print(f"{src['nom']} : {avant} → {dernier}, {len(diff)} règle(s) modifiée(s) sur {len(r_ap)}.")
        if src["cle"] == "cdtn":
            conv = {**idcc_des_conventions(r_av), **idcc_des_conventions(r_ap)}
            nouvelles += alertes_cdtn(diff, avant, dernier, idcc_appli, jour, conv)
        else:
            nouvelles += alertes_urssaf(diff, avant, dernier, jour)
        vu.update({"version": dernier, "depuis": jour})

    # Rétention : une alerte reste 45 jours (NOUVEAU au premier passage seulement).
    limite = (datetime.strptime(jour, "%Y-%m-%d") - timedelta(days=RETENTION_JOURS)).strftime("%Y-%m-%d")
    garde = {a["_id"]: a for a in memoire.get("detectes", [])}
    for a in nouvelles:
        a.setdefault("vu_le", jour)
        garde.setdefault(a["_id"], a)
    memoire["detectes"] = sorted((a for a in garde.values() if a.get("vu_le", jour) >= limite),
                                 key=lambda a: a.get("vu_le", ""), reverse=True)
    with open(args.memoire, "w", encoding="utf-8") as f:
        json.dump(memoire, f, ensure_ascii=False, indent=1)

    alertes = [{k: v for k, v in a.items() if not k.startswith("_")} for a in memoire["detectes"]]
    for e in erreurs:
        print("ATTENTION", e)
    resultat = {"module": "regles-officielles", "alertes": alertes}
    if erreurs:
        resultat["erreur"] = " ; ".join(erreurs)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
