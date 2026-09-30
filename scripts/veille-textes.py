#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VEILLE-TEXTES.PY — tout texte NOUVEAU du fonds qui touche un sujet suivi,
même s'il n'est encore cité nulle part dans l'écosystème.

Jusqu'ici, le tableau de bord ne regardait que ce qu'il connaissait déjà :
les numéros d'articles cités, et pour les CCN les clauses salaires. Un décret
sur les heures supplémentaires, un avenant « temps partiel » d'une convention
de l'appli ou un nouvel article inséré à côté de L3121-36 passaient donc
inaperçus. Ce script regarde les quatre fonds :

  CODE  (d) les SECTIONS du Code qui contiennent nos articles cités : un
        numéro qui y apparaît = « Nouvel article sur un sujet suivi ».
  CCN   un texte (avenant, accord) nouveau dans une convention : haute si la
        convention est dans l'appli (GrillePaye), sinon seulement s'il parle
        d'un de nos sujets (mots-clés).
  JORF  loi, décret, arrêté nouveau : haute s'il modifie un article du Code
        que l'on suit, moyenne s'il contient un mot-clé ou étend un avenant
        d'une convention de l'appli (le JO arrive des semaines AVANT que
        l'aspirateur ne relise la convention).
  ACCO  accord d'entreprise nouveau avec un mot-clé : rubrique à part,
        regroupée par thème, gravité basse — pour ne pas noyer le reste.

(e) Les sujets : mots-cles.json, éditable sur GitHub (même principe
qu'exceptions.json).

(f) Mémoire d'un passage à l'autre : textes-vus.json. Premier passage (ou
premier passage d'un fonds, d'une convention, d'une section) = état de départ
enregistré SANS alerte. Un afflux anormal d'un coup (rattrapage de
l'aspirateur, ex. 6 000 accords anciens) est enregistré sans alerte lui aussi.

Les identifiants Légifrance (JORFTEXT…, KALITEXT…, ACCOTEXT…) sont attribués
dans l'ordre de publication : « nouveau » = numéro plus grand que le plus
grand déjà vu. Un rattrapage de textes ANCIENS (numéros plus petits) ne
déclenche donc rien, et la mémoire tient en quelques Ko.

Une alerte reste affichée RETENTION_JOURS jours (elle n'est « NOUVEAU »
qu'au premier passage) : un texte repéré un lundi ne doit pas disparaître le
mercredi parce qu'il n'est plus « nouveau ».

USAGE
    python3 veille-textes.py --hs /chemin/hs --fonds /chemin/droit \\
        --mots-cles ../mots-cles.json --memoire ../textes-vus.json \\
        --empreintes-articles ../empreintes-articles.json --json sortie.json
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veille_commun import (charger_mots_cles, exclu, themes_trouves, texte_de,  # noqa: E402
                           refs_articles, normaliser, lien_legifrance,
                           lien_monlegitexte, idcc_de_l_appli)

RETENTION_JOURS = 45
# Au-delà, c'est un rattrapage de l'aspirateur, pas l'actualité d'un passage.
SEUIL_RATTRAPAGE = {"jorf": 300, "acco": 500, "ccn": 40, "code": 60}
MAX_DETECTES = 400

CODES = {"CT": "code-travail", "CSS": "code-secu"}
NOM_CODE = {"CT": "Code du travail", "CSS": "Code de la sécurité sociale"}

# Formules par lesquelles un texte modifie un code.
_MODIFIE = re.compile(r"est (ainsi )?(modifie|remplace|abroge|redige|insere|complete|retabli)"
                      r"|sont (ainsi )?(modifies|remplaces|abroges|rediges|inseres|completes)"
                      r"|il est (insere|cree|ajoute|retabli)")
# « … convention collective nationale de l'édition (n° 2121) » / « IDCC 2121 »
_IDCC_TITRE = re.compile(r"\(\s*n[°o]\s*(\d{1,4})\s*\)|\bidcc\s*(?:n[°o]\s*)?(\d{1,4})\b", re.I)


def num_id(identifiant):
    m = re.search(r"(\d+)$", str(identifiant or ""))
    return int(m.group(1)) if m else 0


def court(t, n=150):
    t = " ".join(str(t or "").replace("<mark>", "").replace("</mark>", "").split())
    t = t.replace(" : ", " – ")        # « : » sépare l'identifiant du reste du titre
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def date_ms(v):
    try:
        v = int(v)
        if 0 < v < 32000000000000:
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def lignes_themes(trouves):
    return "\n".join(f"{e} {nom} — « {expr} » : {extrait}" for nom, e, expr, extrait in trouves)


# ── CODE : veille par sections (d) ─────────────────────────────────────────
def articles_cites(chemin_empreintes):
    """{code: {num}} : les articles cités, tels que verifier-contenu-articles.py
    les a relevés dans CE passage (il tourne juste avant)."""
    out = {"CT": set(), "CSS": set()}
    try:
        for cle in json.load(open(chemin_empreintes, encoding="utf-8")):
            code, _, num = cle.partition(":")
            if code in out and num:
                out[code].add(num)
    except Exception:
        pass
    return out


_RX_SECT = re.compile(r'"sectionParentCid":\s*"(LEGISCTA\d+)"')


def veille_sections(fonds, cites, memoire, alertes, themes, aujourd_hui):
    """Retourne {code: {num}} : TOUS les articles des sections suivies (sert
    aussi au JORF, pour savoir si un décret touche « notre » partie du Code)."""
    suivis_tous = {}
    mem = memoire.setdefault("sections", {})
    for code, sous in CODES.items():
        dossier = os.path.join(fonds, "output", sous)
        suivis_tous[code] = set()
        if not os.path.isdir(dossier):
            continue
        # 1) Les sections de nos articles cités.
        sections = {}
        for num in cites.get(code, ()):
            try:
                a = json.load(open(os.path.join(dossier, num + ".json"), encoding="utf-8")).get("article")
            except Exception:
                a = None
            if a and a.get("sectionParentCid"):
                sections[a["sectionParentCid"]] = a.get("fullSectionsTitre") or a.get("sectionParentTitre") or ""
        if not sections:
            continue
        # 2) Tous les articles en vigueur de ces sections (pré-filtre texte :
        #    on lit ~20 000 fiches, on n'en décode que quelques centaines).
        contenu = {s: {} for s in sections}
        for e in os.scandir(dossier):
            if not e.name.endswith(".json") or e.name.startswith("_"):
                continue
            try:
                brut = open(e.path, encoding="utf-8").read()
            except Exception:
                continue
            m = _RX_SECT.search(brut)
            if not m or m.group(1) not in sections:
                continue
            try:
                a = json.loads(brut).get("article")
            except Exception:
                continue
            if a and a.get("etat") == "VIGUEUR" and a.get("num"):
                contenu[m.group(1)][a["num"]] = a
        mem_code = mem.setdefault(code, {})
        nouveaux = []
        for s, arts in contenu.items():
            suivis_tous[code].update(arts)
            if s not in mem_code:          # section vue pour la 1re fois : départ
                mem_code[s] = sorted(arts)
                continue
            deja = set(mem_code[s])
            for num, a in arts.items():
                if num not in deja:
                    nouveaux.append((s, num, a))
            mem_code[s] = sorted(deja | set(arts))
        if len(nouveaux) > SEUIL_RATTRAPAGE["code"]:
            alertes.append(_rattrapage("code", NOM_CODE[code], len(nouveaux), aujourd_hui))
            continue
        for s, num, a in nouveaux:
            texte = " ".join((a.get("texte") or "").split())
            cree = next((l.get("textTitle") for l in (a.get("lienModifications") or [])
                         if l.get("linkType") in ("CREE", "DEPLACE", "TRANSFERE")), "")
            trouves = themes_trouves(texte, themes)
            detail = (f"Nouvel article dans une section du {NOM_CODE[code]} qui contient des "
                      f"articles que tu cites.\nSection : {court(sections[s].replace('&gt;', '>'), 300)}"
                      + (f"\nCréé par : {cree}" if cree else "")
                      + f"\n\nTEXTE — {court(texte, 700)}")
            if trouves:
                detail += "\n\n" + lignes_themes(trouves)
            alertes.append({
                "categorie": "nouvel-article-section",
                "gravite": "haute",
                "titre": f"{num} ({code}) : nouvel article sur un sujet suivi",
                "detail": detail,
                "lien": lien_monlegitexte(num, code),
                "fonds": "Code",
                "theme": trouves[0][0] if trouves else "Section suivie",
                "date_texte": aujourd_hui,
                "_id": f"{code}:{num}",
            })
    return suivis_tous


# ── JORF ───────────────────────────────────────────────────────────────────
def veille_jorf(fonds, memoire, alertes, themes, exclusions, suivis, idcc_appli, aujourd_hui):
    dossier = os.path.join(fonds, "output", "jorf")
    if not os.path.isdir(dossier):
        return
    fichiers = [(num_id(n[:-5]), n) for n in os.listdir(dossier)
                if n.startswith("JORFTEXT") and n.endswith(".json")]
    if not fichiers:
        return
    maxi = max(i for i, _ in fichiers)
    avant = memoire.get("jorf_max")
    memoire["jorf_max"] = max(maxi, avant or 0)
    if avant is None:
        print(f"JORF : état de départ enregistré ({len(fichiers)} textes), pas d'alerte.")
        return
    nouveaux = sorted(n for i, n in fichiers if i > avant)
    print(f"JORF : {len(nouveaux)} texte(s) nouveau(x) depuis le dernier passage.")
    if len(nouveaux) > SEUIL_RATTRAPAGE["jorf"]:
        alertes.append(_rattrapage("jorf", "Journal officiel", len(nouveaux), aujourd_hui))
        return
    tous_suivis = {n for s in suivis.values() for n in s}
    for nom in nouveaux:
        try:
            d = json.load(open(os.path.join(dossier, nom), encoding="utf-8"))
        except Exception:
            continue
        titre = d.get("titre") or ""
        if not titre or exclu(titre, exclusions):
            continue
        corps = d.get("text") if isinstance(d.get("text"), dict) else {}
        texte = texte_de(corps)
        date = date_ms(corps.get("dateParution")) or aujourd_hui
        trouves = themes_trouves(titre + " " + texte, themes)
        n_texte = normaliser(texte)
        refs = refs_articles(texte)
        touche = sorted(refs & tous_suivis) if _MODIFIE.search(n_texte) and (
            "code du travail" in n_texte or "code de la securite sociale" in n_texte) else []
        # « Avis relatif à l'extension… » n'est qu'une annonce : l'arrêté
        # d'extension suit quelques semaines après et sera, lui, signalé. Les
        # garder doublait presque le volume (1 texte JORF sur 3) pour rien.
        if normaliser(titre).startswith("avis relatif a l'extension"):
            continue
        idcc = {g for m in _IDCC_TITRE.finditer(titre) for g in m.groups() if g}
        idcc_app = sorted(idcc & idcc_appli, key=int)
        est_avis = normaliser(titre).startswith("avis ")
        sujets = ", ".join(t[0] for t in trouves)

        if touche:
            gravite, pourquoi = "haute", (f"modifie des articles du Code que tu suis : "
                                          f"{', '.join(touche[:12])}")
        elif idcc_app and not est_avis:
            gravite = "haute" if trouves else "moyenne"
            pourquoi = (f"concerne une convention de l'appli (IDCC {', '.join(idcc_app)})"
                        + (f" — {sujets}" if sujets else ""))
        elif trouves:
            gravite, pourquoi = "moyenne", f"parle de : {sujets}"
        else:
            continue
        detail = (f"Paru au JO le {date}. Ce texte {pourquoi}.\n\n"
                  f"{court(titre, 400)}")
        if trouves:
            detail += "\n\n" + lignes_themes(trouves)
        if refs:
            detail += f"\n\nArticles de code cités dans le texte : {', '.join(sorted(refs)[:20])}"
        alertes.append({
            "categorie": "nouveau-texte-jorf",
            "gravite": gravite,
            "titre": f"{court(titre, 140)} : {pourquoi}",
            "detail": detail,
            "lien": lien_legifrance(nom[:-5]),
            "fonds": "JORF",
            "theme": trouves[0][0] if trouves else ("Convention de l'appli" if idcc_app else "Code suivi"),
            "date_texte": date,
            "_id": nom[:-5],
        })


# ── CCN ────────────────────────────────────────────────────────────────────
def _textes_ccn(o, acc):
    """{KALITEXT: noeud} dans une convention (texte de base, attachés, salaires)."""
    if isinstance(o, dict):
        i = str(o.get("id", ""))
        if i.startswith("KALITEXT"):
            acc.setdefault(i, o)
        for v in o.values():
            if isinstance(v, (dict, list)):
                _textes_ccn(v, acc)
    elif isinstance(o, list):
        for v in o:
            _textes_ccn(v, acc)


def veille_ccn(fonds, memoire, alertes, themes, exclusions, idcc_appli, aujourd_hui):
    dossier = os.path.join(fonds, "output", "ccn")
    if not os.path.isdir(dossier):
        return
    mem = memoire.setdefault("ccn_max", {})
    total = 0
    for n in sorted(os.listdir(dossier)):
        if not re.fullmatch(r"\d+\.json", n):
            continue
        idcc = n[:-5]
        try:
            d = json.load(open(os.path.join(dossier, n), encoding="utf-8"))
        except Exception:
            continue
        textes = {}
        _textes_ccn(d.get("sections") or [], textes)
        if not textes:
            continue
        maxi = max(num_id(i) for i in textes)
        avant = mem.get(idcc)
        mem[idcc] = max(maxi, avant or 0)
        if avant is None:
            continue                         # convention vue pour la 1re fois : départ
        nouveaux = [(i, t) for i, t in textes.items() if num_id(i) > avant]
        if not nouveaux:
            continue
        if len(nouveaux) > SEUIL_RATTRAPAGE["ccn"]:
            alertes.append(_rattrapage("ccn", f"IDCC {idcc}", len(nouveaux), aujourd_hui))
            continue
        nom_ccn = court(d.get("titre") or "", 90)
        for i, t in sorted(nouveaux):
            titre = t.get("title") or t.get("titre") or ""
            if exclu(titre, exclusions):
                continue
            texte = texte_de({"x": t.get("sections"), "y": t.get("articles")})
            trouves = themes_trouves(titre + " " + texte, themes)
            dans_appli = idcc in idcc_appli
            if not dans_appli and not trouves:
                continue
            total += 1
            detail = (f"Nouveau texte dans la convention IDCC {idcc} ({nom_ccn})"
                      + (" — convention présente dans l'appli." if dans_appli else ".")
                      + f"\nDate : {t.get('dateModif') or '?'} · État : {t.get('etat') or '?'}"
                      + f"\n\n{court(titre, 400)}")
            if trouves:
                detail += "\n\n" + lignes_themes(trouves)
            elif not texte.strip():
                detail += ("\n\n(Corps du texte pas encore récupéré par l'aspirateur : "
                           "seul le titre a pu être lu.)")
            alertes.append({
                "categorie": "nouvel-avenant-ccn",
                "gravite": "haute" if dans_appli else "moyenne",
                "titre": f"IDCC {idcc} — {court(titre, 120)} : nouveau texte"
                         + (f" ({trouves[0][0]})" if trouves else ""),
                "detail": detail,
                "lien": lien_legifrance(i),
                "fonds": "CCN",
                "theme": trouves[0][0] if trouves else "Convention de l'appli",
                "date_texte": t.get("dateModif") or aujourd_hui,
                "_id": i,
            })
    print(f"CCN : {total} texte(s) nouveau(x) retenu(s).")


# ── ACCO ───────────────────────────────────────────────────────────────────
def infos_accord(meta, idcc_appli):
    """« 12/09/2026 · ACME (SIRET 123…) · IDCC 1516 — convention de l'appli »,
    à partir des métadonnées gardées par l'aspirateur depuis le 30/09/2026
    (les accords plus anciens n'en ont pas : chaîne vide)."""
    if not meta:
        return ""
    brut = json.dumps(meta, ensure_ascii=False)
    morceaux = []
    for k, v in meta.items():
        if "date" in k.lower() and isinstance(v, (int, str)):
            d = date_ms(v) if isinstance(v, int) else str(v)[:10]
            if d:
                morceaux.append(d)
                break
    for k in ("raisonSociale", "raison_sociale", "entreprise", "denomination"):
        if meta.get(k):
            morceaux.append(str(meta[k])[:60])
            break
    idcc = sorted({m for m in re.findall(r'"(?:idcc|codeIdcc|IDCC|num)":\s*"?(\d{1,4})\b', brut)}, key=int)
    if idcc:
        dans = [i for i in idcc if i in idcc_appli]
        morceaux.append("IDCC " + ", ".join(idcc[:3]) + (" — convention de l'appli" if dans else ""))
    return " · ".join(morceaux)


def veille_acco(fonds, memoire, alertes_acco, themes, exclusions, aujourd_hui, idcc_appli=frozenset()):
    dossier = os.path.join(fonds, "output", "acco")
    if not os.path.isdir(dossier):
        return
    fichiers = []
    for e in os.scandir(dossier):
        if e.name.startswith("ACCOTEXT") and e.name.endswith(".json"):
            fichiers.append((num_id(e.name[:-5]), e.name))
    if not fichiers:
        return
    maxi = max(i for i, _ in fichiers)
    avant = memoire.get("acco_max")
    memoire["acco_max"] = max(maxi, avant or 0)
    if avant is None:
        print(f"ACCO : état de départ enregistré ({len(fichiers)} accords), pas d'alerte.")
        return
    nouveaux = sorted(n for i, n in fichiers if i > avant)
    print(f"ACCO : {len(nouveaux)} accord(s) nouveau(x).")
    if len(nouveaux) > SEUIL_RATTRAPAGE["acco"]:
        alertes_acco.append(_rattrapage("acco", "Accords d'entreprise", len(nouveaux), aujourd_hui))
        return
    par_theme = {}
    for nom in nouveaux:
        try:
            d = json.load(open(os.path.join(dossier, nom), encoding="utf-8"))
        except Exception:
            continue
        titre = d.get("titre") or ""
        if exclu(titre, exclusions):
            continue
        trouves = themes_trouves(titre + " " + texte_de(d.get("text") or {}), themes, largeur=110)
        info = infos_accord(d.get("meta") or {}, idcc_appli)
        for nom_t, emo, expr, extrait in trouves:
            par_theme.setdefault((nom_t, emo), []).append((nom[:-5], titre, expr, extrait, info))
    for (nom_t, emo), liste in sorted(par_theme.items(), key=lambda kv: -len(kv[1])):
        # Les accords d'une convention de l'appli d'abord.
        liste.sort(key=lambda x: 0 if "convention de l'appli" in x[4] else 1)
        lignes = [f"• {court(t, 110)}" + (f"\n  {info}" if info else "")
                  + f"\n  « {expr} » : {court(ex, 240)}\n  {lien_legifrance(i)}"
                  for i, t, expr, ex, info in liste[:12]]
        if len(liste) > 12:
            lignes.append(f"… et {len(liste) - 12} autre(s).")
        alertes_acco.append({
            "categorie": "accords-entreprise",
            "gravite": "basse",
            "titre": f"{emo} {nom_t} ({aujourd_hui}) : {len(liste)} accord(s) d'entreprise nouveau(x)",
            "detail": "Accords d'entreprise publiés depuis le dernier passage qui parlent de ce "
                      "sujet — pour t'inspirer ou repérer une pratique, rien d'obligatoire.\n\n"
                      + "\n\n".join(lignes),
            "lien": lien_legifrance(liste[0][0]),
            "fonds": "ACCO",
            "theme": nom_t,
            "compteur": len(liste),
            "date_texte": aujourd_hui,
            "_id": f"acco:{nom_t}:{aujourd_hui}",
        })


def _rattrapage(fonds, quoi, n, aujourd_hui):
    return {
        "categorie": "rattrapage-fonds",
        "gravite": "basse",
        "titre": f"{quoi} ({aujourd_hui}) : {n} textes arrivés d'un coup, enregistrés sans alerte",
        "detail": (f"L'aspirateur a ajouté {n} textes en un seul passage : c'est un rattrapage "
                   f"(textes anciens récupérés en masse), pas l'actualité. Ils sont mémorisés "
                   f"comme « déjà vus » pour ne pas te noyer ; seuls les textes suivants seront "
                   f"signalés."),
        "fonds": fonds.upper(),
        "_id": f"rattrapage:{fonds}:{quoi}:{aujourd_hui}",
    }


def fusionner_retention(memoire, nouvelles, aujourd_hui):
    """Ajoute les alertes de ce passage à la mémoire et renvoie toutes celles
    encore dans la fenêtre de RETENTION_JOURS jours."""
    limite = (datetime.strptime(aujourd_hui, "%Y-%m-%d") - timedelta(days=RETENTION_JOURS)).strftime("%Y-%m-%d")
    deja = {a.get("_id"): a for a in memoire.get("detectes", [])}
    for a in nouvelles:
        if a.get("_id") not in deja:
            a["vu_le"] = aujourd_hui
            deja[a["_id"]] = a
    gardees = [a for a in deja.values() if a.get("vu_le", aujourd_hui) >= limite]
    gardees.sort(key=lambda a: a.get("vu_le", ""), reverse=True)
    memoire["detectes"] = gardees[:MAX_DETECTES]
    return memoire["detectes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--fonds", required=True)
    ap.add_argument("--mots-cles", required=True)
    ap.add_argument("--memoire", required=True)
    ap.add_argument("--empreintes-articles", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    themes, exclusions = charger_mots_cles(args.mots_cles)
    print(f"{len(themes)} thème(s), {sum(len(t['motifs']) for t in themes)} expression(s), "
          f"{len(exclusions)} exclusion(s).")
    try:
        memoire = json.load(open(args.memoire, encoding="utf-8"))
    except Exception:
        memoire = {}
    memoire["version"] = 1

    idcc_appli = idcc_de_l_appli(args.hs)
    cites = articles_cites(args.empreintes_articles)
    alertes, alertes_acco = [], []

    suivis = veille_sections(args.fonds, cites, memoire, alertes, themes, aujourd_hui)
    print(f"Code : {sum(len(v) for v in suivis.values())} article(s) dans les sections suivies.")
    veille_jorf(args.fonds, memoire, alertes, themes, exclusions, suivis, idcc_appli, aujourd_hui)
    veille_ccn(args.fonds, memoire, alertes, themes, exclusions, idcc_appli, aujourd_hui)
    veille_acco(args.fonds, memoire, alertes_acco, themes, exclusions, aujourd_hui, idcc_appli)

    toutes = fusionner_retention(memoire, alertes + alertes_acco, aujourd_hui)
    memoire["dernier_passage"] = aujourd_hui
    with open(args.memoire, "w", encoding="utf-8") as f:
        json.dump(memoire, f, ensure_ascii=False, indent=1)

    def propre(a):
        return {k: v for k, v in a.items() if not k.startswith("_")}
    resultat = {
        "module": "veille-textes",
        "alertes": [propre(a) for a in toutes if a.get("categorie") != "accords-entreprise"
                    and a.get("fonds") != "ACCO"],
        "alertes_accords": [propre(a) for a in toutes if a.get("categorie") == "accords-entreprise"
                            or a.get("fonds") == "ACCO"],
    }
    print(f"{len(alertes)} alerte(s) nouvelle(s) ce passage (+ {len(alertes_acco)} pour les accords), "
          f"{len(toutes)} gardée(s) sur {RETENTION_JOURS} jours.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
