#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VEILLE-SOURCES-OFFICIELLES.PY — les trois trous de la veille (02/10/2026).

  BOSS      Bulletin officiel de la Sécurité sociale (boss.gouv.fr) : la
            doctrine de l'administration sur l'exonération des heures sup, la
            réduction générale, les avantages en nature, les frais pro… Une
            rubrique qui change = un calcul de paye de l'appli à revoir.
            Méthode : les pages du BOSS sur nos sujets (trouvées depuis
            l'accueil) sont relues à chaque passage ; seuls les paragraphes
            réellement ajoutés ou retirés remontent, avec l'avant / l'après.

  PARLEMENT Ce qui n'est PAS ENCORE au Journal officiel : projets et
            propositions de loi déposés (Sénat, Assemblée), commission des
            affaires sociales. Octobre = budget de la Sécurité sociale (PLFSS),
            là où se jouent chaque année l'exonération des heures sup et les
            cotisations. Méthode : flux RSS officiels, filtrés par tes sujets
            (mots-cles.json) et quelques mots du travail.

  DARES     La liste officielle des conventions (univers des IDCC) vient d'un
            fichier DARES posé à la main dans le dépôt droit. Il vieillit sans
            prévenir : alerte au-delà de 4 mois.

Mémoire : sources-officielles.json (committé). Premier passage de chaque
source = état de départ enregistré SANS alerte. Une source injoignable deux
passages de suite = une alerte (sinon la veille se tairait sans rien dire).

USAGE
    python3 veille-sources-officielles.py --droit /chemin/droit \\
        --mots-cles ../mots-cles.json --memoire ../sources-officielles.json --json sortie.json
    python3 veille-sources-officielles.py ... --diagnostic   (affiche tout ce qui est lu)
"""
import argparse
import difflib
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from veille_commun import charger_mots_cles, themes_trouves, normaliser  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) veille-SimulHeures (+https://github.com/anthonychauvel/tableaudebord)"
RETENTION_JOURS = 45

# ── BOSS ──────────────────────────────────────────────────────────────────
BOSS_DEPART = ["https://boss.gouv.fr/portail/accueil.html", "https://boss.gouv.fr/"]
# Une page du BOSS est suivie si son adresse ou l'intitulé du lien parle d'un de ces sujets.
BOSS_SUJETS = re.compile(
    r"heures?[- ]suppl|heures?[- ]compl|reduction[- ]generale|allegement|exoneration|avantages?[- ]en[- ]nature"
    r"|frais[- ]professionnel|assiette|temps[- ]partiel|apprenti|smic|cotisation|mise[s]?[- ]a[- ]jour"
    r"|historique|actualit|nouveaute", re.I)
BOSS_MAX_PAGES = 30
BOSS_TEXTE_MAX = 25000
# Paragraphe « sensible » : touche directement un calcul de l'appli -> 🔴
SENSIBLE = re.compile(r"heures? suppl|heures? compl|reduction generale|exoneration|smic|plafond"
                      r"|taux|majoration|contingent|avantage en nature|forfait", re.I)

# ── PARLEMENT ─────────────────────────────────────────────────────────────
FLUX = [
    ("Sénat — textes déposés", "https://www.senat.fr/rss/textes.rss"),
    ("Sénat — affaires sociales", "https://www.senat.fr/themes/rss/therss20.rss"),
    ("Assemblée — documents parlementaires",
     "https://www2.assemblee-nationale.fr/feeds/detail/documents-parlementaires"),
    ("Assemblée — commission des affaires sociales",
     "https://www2.assemblee-nationale.fr/feeds/detail/ID_420120/(type)/instance"),
]
PARL_SUJETS = re.compile(
    r"financement de la securite sociale|plfss|code du travail|droit du travail|duree du travail|temps de travail"
    r"|heures? supplementaires?|heures? complementaires?|conges payes|travail de nuit|travail du dimanche"
    r"|salaries?|salaire|smic|cotisations? sociales?|pouvoir d'achat|assurance chomage|apprentissage"
    r"|teletravail|rupture conventionnelle|licenciement|prud'hom|convention collective|dialogue social", re.I)
PARL_FORT = re.compile(r"financement de la securite sociale|plfss|heures? supplementaires?|code du travail"
                       r"|duree du travail|temps de travail|smic", re.I)

# ── DARES ─────────────────────────────────────────────────────────────────
DARES_MAX_JOURS = 120
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}


def ouvrir(url, delai=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def court(t, n=300):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def empreinte(t):
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]


# ── BOSS : lecture des pages ──────────────────────────────────────────────
_BLOC = re.compile(r"</?(p|div|li|h[1-6]|tr|td|th|section|article|br|table|ul|ol|dd|dt)\b[^>]*>", re.I)


def paragraphes(page):
    """Texte utile d'une page HTML, découpé en paragraphes (menus, en-tête et
    pied de page retirés ; le contenu de <main>/<article> s'il existe)."""
    h = re.sub(r"<(script|style|noscript|svg|nav|header|footer|form)\b.*?</\1>", " ", page, flags=re.S | re.I)
    m = re.search(r"<main\b.*?</main>", h, re.S | re.I) or re.search(r"<article\b.*?</article>", h, re.S | re.I)
    if m:
        h = m.group(0)
    h = _BLOC.sub("\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", " ", h))
    out, total = [], 0
    for ligne in h.split("\n"):
        ligne = " ".join(ligne.split())
        if len(ligne) < 25:                 # titres de menu, boutons, numéros
            continue
        if out and ligne == out[-1]:
            continue
        out.append(ligne)
        total += len(ligne)
        if total > BOSS_TEXTE_MAX:
            break
    return out


def titre_page(page, url):
    m = re.search(r"<h1\b[^>]*>(.*?)</h1>", page, re.S | re.I) or re.search(r"<title>(.*?)</title>", page, re.S | re.I)
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split()) if m else ""
    return t or url.rstrip("/").rsplit("/", 1)[-1]


def liens_boss(page, base):
    out = []
    for href, texte in re.findall(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        u = urllib.parse.urljoin(base, html.unescape(href))
        if urllib.parse.urlparse(u).netloc not in ("boss.gouv.fr", "www.boss.gouv.fr"):
            continue
        if re.search(r"\.(pdf|jpg|png|zip|xlsx?)$", u, re.I):
            continue
        cle = normaliser(u + " " + re.sub(r"<[^>]+>", " ", texte))
        if BOSS_SUJETS.search(cle) and u not in out:
            out.append(u)
    return out


def veille_boss(memoire, alertes, sante, aujourd_hui, diag):
    mem = memoire.setdefault("boss", {})
    pages_mem = mem.setdefault("pages", {})
    accueil, base = None, None
    for u in BOSS_DEPART:
        try:
            accueil, base = ouvrir(u), u
            break
        except Exception as e:                       # noqa: BLE001
            if diag:
                print(f"  BOSS {u} : {e}")
    if accueil is None:
        _injoignable(mem, sante, "BOSS (boss.gouv.fr)", BOSS_DEPART[0], aujourd_hui)
        print("BOSS : accueil injoignable.")
        return
    mem["echecs"] = 0
    cibles = liens_boss(accueil, base)
    # Les pages déjà suivies restent suivies même si l'accueil ne les montre plus.
    for u in pages_mem:
        if u not in cibles:
            cibles.append(u)
    cibles = cibles[:BOSS_MAX_PAGES]
    if diag:
        print(f"BOSS : {len(cibles)} page(s) sur nos sujets :")
        for u in cibles:
            print(f"   {u}")
    premier = not pages_mem
    n_modif = 0
    for u in cibles:
        try:
            page = ouvrir(u)
        except Exception as e:                       # noqa: BLE001
            if diag:
                print(f"  {u} : {e}")
            continue
        paras = paragraphes(page)
        if not paras:
            continue
        titre = titre_page(page, u)
        h = empreinte("\n".join(paras))
        avant = pages_mem.get(u)
        pages_mem[u] = {"titre": titre, "empreinte": h, "paragraphes": paras, "vu_le": aujourd_hui}
        if diag:
            print(f"  {court(titre, 80)} : {len(paras)} paragraphe(s)")
        if premier or avant is None or avant.get("empreinte") == h:
            continue
        anciens, nouveaux = avant.get("paragraphes") or [], paras
        retires = [p for p in anciens if p not in set(nouveaux)]
        ajoutes = [p for p in nouveaux if p not in set(anciens)]
        # Une date de mise à jour seule qui change n'est pas une modification de fond.
        fond = [p for p in retires + ajoutes if not re.fullmatch(r".{0,60}\d{1,2}[/ ]\w+[/ ]\d{4}.{0,20}", p)]
        if not fond:
            continue
        n_modif += 1
        sensible = any(SENSIBLE.search(normaliser(p)) for p in fond)
        lignes = [f"－ {court(p)}" for p in retires[:5]] + [f"＋ {court(p)}" for p in ajoutes[:5]]
        if len(retires) > 5 or len(ajoutes) > 5:
            lignes.append(f"(… {len(retires)} paragraphe(s) retiré(s), {len(ajoutes)} ajouté(s) au total)")
        alertes.append({
            "categorie": "boss-modifie",
            "gravite": "haute" if sensible else "moyenne",
            "titre": f"BOSS — {court(titre, 110)} : {len(retires) + len(ajoutes)} paragraphe(s) modifié(s)",
            "detail": ("Une page du Bulletin officiel de la Sécurité sociale sur tes sujets a changé "
                       f"depuis le passage du {avant.get('vu_le') or '?'}.\n\n" + "\n".join(lignes)),
            "lien": u,
            "date_texte": aujourd_hui,
            "_id": f"boss:{u}:{h}",
        })
    mem["dernier"] = aujourd_hui
    print(f"BOSS : {len(cibles)} page(s) suivie(s), "
          + ("état de départ enregistré sans alerte." if premier else f"{n_modif} modifiée(s)."))


# ── PARLEMENT ─────────────────────────────────────────────────────────────
def items_flux(xml_txt):
    """RSS 2.0 ou Atom -> [(titre, lien, date, description)]."""
    out = []
    try:
        racine = ET.fromstring(xml_txt.encode("utf-8"))
    except ET.ParseError:
        racine = None
    if racine is not None:
        for it in racine.iter():
            tag = it.tag.rsplit("}", 1)[-1].lower()
            if tag not in ("item", "entry"):
                continue
            d = {}
            for c in it:
                t = c.tag.rsplit("}", 1)[-1].lower()
                if t == "link":
                    d["link"] = (c.text or c.get("href") or "").strip()
                elif c.text:
                    d.setdefault(t, c.text.strip())
            out.append((d.get("title", ""), d.get("link", ""),
                        d.get("pubdate") or d.get("updated") or d.get("date") or d.get("published") or "",
                        html.unescape(re.sub(r"<[^>]+>", " ", d.get("description") or d.get("summary") or ""))))
        return out
    for bloc in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", xml_txt, re.S | re.I):
        def champ(n):
            m = re.search(rf"<{n}\b[^>]*>(.*?)</{n}>", bloc, re.S | re.I)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", " ", m.group(1))).strip() if m else ""
        lien = champ("link") or (re.search(r'<link[^>]*href="([^"]+)"', bloc) or [None, ""])[1]
        out.append((champ("title"), lien, champ("pubDate") or champ("updated"), champ("description")))
    return out


def veille_parlement(memoire, alertes, sante, themes, aujourd_hui, diag):
    mem = memoire.setdefault("parlement", {})
    vus = mem.setdefault("vus", {})
    total = 0
    for nom, url in FLUX:
        etat = mem.setdefault("flux", {}).setdefault(url, {})
        try:
            items = items_flux(ouvrir(url))
        except Exception as e:                       # noqa: BLE001
            if diag:
                print(f"  {nom} : {e}")
            _injoignable(etat, sante, nom, url, aujourd_hui)
            continue
        etat["echecs"] = 0
        premier = not etat.get("lu")
        etat["lu"] = aujourd_hui
        if diag:
            print(f"{nom} : {len(items)} élément(s)")
            for t, l, d, _ in items[:8]:
                print(f"   - {court(t, 110)} ({d[:16]})")
        for titre, lien, date, desc in items:
            cle = lien or titre
            if not cle or cle in vus:
                continue
            vus[cle] = aujourd_hui
            texte = normaliser(titre + " " + desc)
            # Premier passage : départ sans alerte… sauf les textes majeurs déjà
            # dans le flux (le PLFSS se dépose début octobre : ne pas le rater).
            if premier and not PARL_FORT.search(texte):
                continue
            trouves = themes_trouves(titre + " " + desc, themes)
            if not trouves and not PARL_SUJETS.search(texte):
                continue
            total += 1
            fort = bool(PARL_FORT.search(texte))
            detail = (f"{nom} — {date or 'date ?'}.\n\n{court(titre, 400)}"
                      + (f"\n\n{court(desc, 600)}" if desc.strip() else "")
                      + "\n\nCe texte n'est PAS encore une loi : il peut être modifié ou rejeté. "
                        "À suivre pour anticiper ce que l'appli devra changer s'il est adopté.")
            if trouves:
                detail += "\n\n" + "\n".join(f"{e} {n} — « {x} »" for n, e, x, _ in trouves)
            alertes.append({
                "categorie": "texte-parlement",
                "gravite": "haute" if fort else "moyenne",
                "titre": f"🏛️ {court(titre, 140)}",
                "detail": detail,
                "lien": lien,
                "date_texte": aujourd_hui,
                "_id": f"parl:{cle}",
            })
    # Mémoire bornée : on garde les 4 000 liens les plus récents.
    if len(vus) > 4000:
        for k in sorted(vus, key=vus.get)[:len(vus) - 4000]:
            del vus[k]
    print(f"Parlement : {total} texte(s) retenu(s) ce passage.")


# ── DARES ─────────────────────────────────────────────────────────────────
def date_dares(droit):
    """-> (date ISO, nom du fichier, d'où vient la date)."""
    src = os.path.join(droit, "ccn", "dares-source.json")
    if os.path.isfile(src):
        try:
            d = json.load(open(src, encoding="utf-8"))
            if d.get("date_publication") or d.get("telecharge_le"):
                return (d.get("date_publication") or d["telecharge_le"])[:10], d.get("fichier", "?"), "dares-source.json"
        except Exception:
            pass
    meilleur = None
    dossier = os.path.join(droit, "ccn")
    for n in os.listdir(dossier) if os.path.isdir(dossier) else []:
        if not n.lower().endswith(".xlsx"):
            continue
        m = re.search(r"([A-Za-zéûÉÛ]+)[_ -]?(20\d\d)", n)
        if m and normaliser(m.group(1)) in MOIS:
            d = f"{m.group(2)}-{MOIS[normaliser(m.group(1))]:02d}-01"
            if not meilleur or d > meilleur[0]:
                meilleur = (d, n, "nom du fichier")
    return meilleur or (None, None, None)


def veille_dares(droit, alertes, aujourd_hui):
    """alertes : ici la liste des états (pas de rétention 45 jours)."""
    if not droit:
        return
    d, nom, source = date_dares(droit)
    if not d:
        print("DARES : aucun fichier de suivi des conventions trouvé dans droit/ccn.")
        return
    age = (datetime.strptime(aujourd_hui, "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days
    print(f"DARES : {nom} ({d}, {age} jours).")
    if age <= DARES_MAX_JOURS:
        return
    alertes.append({
        "categorie": "dares-perime",
        "gravite": "moyenne",
        "titre": f"Liste officielle des conventions (DARES) : {age} jours",
        "detail": (f"Le fichier qui sert d'univers des IDCC ({nom}, daté du {d} d'après {source}) a plus de "
                   f"{DARES_MAX_JOURS} jours. Les conventions créées ou fusionnées depuis ne sont pas vues par "
                   f"l'aspirateur.\n\nLe téléchargement automatique (maj_dares.py, dépôt droit) n'a pas trouvé "
                   f"de version plus récente, ou le site l'a bloqué. Récupère le fichier « Suivi historique des "
                   f"conventions collectives » sur le site de la DARES / du ministère du Travail et pose-le dans "
                   f"droit/ccn/ sous le nom Dares_Suivi_DERNIER.xlsx."),
        "lien": "https://travail-emploi.gouv.fr/conventions-collectives-nomenclatures",
        "date_texte": d,
    })


# ── commun ────────────────────────────────────────────────────────────────
def _injoignable(etat, sante, nom, url, aujourd_hui):
    etat["echecs"] = etat.get("echecs", 0) + 1
    if etat["echecs"] >= 2:
        sante.append({
            "categorie": "source-injoignable",
            "gravite": "moyenne",
            "titre": f"{nom} : injoignable depuis {etat['echecs']} passages",
            "detail": (f"La veille n'arrive plus à lire {url}. Tant que ça dure, rien de nouveau ne peut "
                       f"remonter de cette source. Le site a peut-être changé d'adresse ou bloque les robots : "
                       f"lance « Régénérer » à la main et regarde le journal de veille-sources-officielles.py."),
            "lien": url,
            "date_texte": aujourd_hui,
        })


def retenir(memoire, nouvelles, aujourd_hui):
    limite = (datetime.strptime(aujourd_hui, "%Y-%m-%d") - timedelta(days=RETENTION_JOURS)).strftime("%Y-%m-%d")
    deja = {a.get("_id"): a for a in memoire.get("detectes", [])}
    for a in nouvelles:
        if a.get("_id") not in deja:
            a["vu_le"] = aujourd_hui
            deja[a["_id"]] = a
    gardees = sorted((a for a in deja.values() if a.get("vu_le", aujourd_hui) >= limite),
                     key=lambda a: a.get("vu_le", ""), reverse=True)[:300]
    memoire["detectes"] = gardees
    return gardees


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--droit", default="")
    ap.add_argument("--mots-cles", required=True)
    ap.add_argument("--memoire", required=True)
    ap.add_argument("--json")
    ap.add_argument("--diagnostic", action="store_true")
    ap.add_argument("--sans", default="", help="sources à sauter : boss,parlement,dares")
    args = ap.parse_args()

    aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    themes, _ = charger_mots_cles(args.mots_cles)
    try:
        memoire = json.load(open(args.memoire, encoding="utf-8"))
    except Exception:
        memoire = {}
    sans = {s.strip() for s in args.sans.split(",") if s.strip()}
    alertes, sante = [], []
    if "boss" not in sans:
        try:
            veille_boss(memoire, alertes, sante, aujourd_hui, args.diagnostic)
        except Exception as e:                       # noqa: BLE001
            print(f"BOSS : erreur {e}")
    if "parlement" not in sans:
        try:
            veille_parlement(memoire, alertes, sante, themes, aujourd_hui, args.diagnostic)
        except Exception as e:                       # noqa: BLE001
            print(f"Parlement : erreur {e}")
    if "dares" not in sans:
        veille_dares(args.droit, sante, aujourd_hui)      # un état, pas un événement : pas de rétention

    toutes = retenir(memoire, alertes, aujourd_hui)
    memoire["dernier_passage"] = aujourd_hui
    with open(args.memoire, "w", encoding="utf-8") as f:
        json.dump(memoire, f, ensure_ascii=False, indent=1)

    def propre(a):
        return {k: v for k, v in a.items() if not k.startswith("_")}
    res = {"module": "veille-sources-officielles",
           "alertes": [propre(a) for a in toutes] + sante}
    print(f"{len(alertes)} alerte(s) nouvelle(s), {len(toutes)} gardée(s) sur {RETENTION_JOURS} jours, "
          f"{len(sante)} source(s) injoignable(s).")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
