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
import io
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


# Relais facultatif (secret/variable VEILLE_RELAIS, ex. un Worker Cloudflare
# « https://…/?url= ») : le test du 02/10/2026 montre que boss.gouv.fr ne répond
# pas aux machines de GitHub (délai dépassé). Sans relais, l'alerte 📡 le dit.
RELAIS = os.environ.get("VEILLE_RELAIS", "").strip()
ENTETES = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def ouvrir_octets(url, delai=40, relais=False):
    if relais and RELAIS:
        url = RELAIS + urllib.parse.quote(url, safe="")
    req = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(req, timeout=delai) as r:
        return r.read(), r.headers.get_content_charset()


def ouvrir(url, delai=40, relais=False):
    octets, cs = ouvrir_octets(url, delai, relais)
    if not cs:
        m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', octets[:2000]) or \
            re.search(rb'encoding=["\']([A-Za-z0-9_-]+)', octets[:200])
        cs = m.group(1).decode() if m else "utf-8"
    try:
        return octets.decode(cs, "replace")
    except LookupError:
        return octets.decode("utf-8", "replace")


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


def _paras_texte(t):
    """Page reçue en texte brut (le Raccourci peut envoyer le texte affiché au
    lieu du HTML) : un paragraphe par ligne."""
    out = []
    for ligne in str(t or "").splitlines():
        ligne = " ".join(ligne.split())
        if len(ligne) >= 25 and (not out or ligne != out[-1]):
            out.append(ligne)
    return out


def _est_html(t):
    return bool(re.search(r"<(html|body|div|p|main|a)\b", str(t or "")[:5000], re.I))


def lire_capture(chemin):
    """boss-capture.json écrit par le Raccourci iPhone : {"_date": …, url: page, …}
    ou {"date": …, "pages": {url: page}}. -> (date, {url: page}, empreinte)."""
    try:
        brut = open(chemin, encoding="utf-8").read()
        d = json.loads(brut)
    except Exception:
        return None, {}, None
    pages = d.get("pages") if isinstance(d.get("pages"), dict) else \
        {k: v for k, v in d.items() if str(k).startswith("http")}
    return str(d.get("_date") or d.get("date") or ""), pages, empreinte(brut)


def ecrire_liste_boss(chemin, decouvertes):
    """boss-pages.txt : la liste que le Raccourci télécharge avant de lire le BOSS.
    Tes lignes sont gardées (tu peux en ajouter à la main) ; les pages trouvées
    dans les liens du BOSS sont ajoutées à la fin."""
    try:
        lignes = open(chemin, encoding="utf-8").read().splitlines()
    except Exception:
        lignes = ["# Pages du BOSS lues chaque semaine par le Raccourci iPhone.",
                  "# Une adresse par ligne ; tu peux en ajouter. Les lignes # sont ignorées."] + BOSS_DEPART[:1]
    deja = {l.strip() for l in lignes if l.strip() and not l.startswith("#")}
    ajout = [u for u in decouvertes if u not in deja][:max(0, BOSS_MAX_PAGES - len(deja))]
    if ajout or not os.path.exists(chemin):
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("\n".join(lignes + ajout) + "\n")
    return len(deja) + len(ajout)


def veille_boss(memoire, alertes, sante, aujourd_hui, diag, capture=None, liste=None):
    """boss.gouv.fr bloque GitHub ET Cloudflare (02/10/2026) : la lecture se fait
    depuis l'iPhone (Raccourci « Veille BOSS ») qui dépose boss-capture.json dans
    ce dépôt. Ici on compare cette capture à la précédente."""
    mem = memoire.setdefault("boss", {})
    pages_mem = mem.setdefault("pages", {})
    if not capture or not os.path.exists(capture):
        print("BOSS : pas encore de capture du Raccourci iPhone (boss-capture.json).")
        if liste:
            ecrire_liste_boss(liste, [])
        return
    date_cap, pages, h_cap = lire_capture(capture)
    if h_cap and h_cap != mem.get("capture_empreinte"):
        mem["capture_empreinte"] = h_cap
        mem["capture_recue"] = aujourd_hui
    recue = mem.get("capture_recue") or aujourd_hui
    age = (datetime.strptime(aujourd_hui, "%Y-%m-%d") - datetime.strptime(recue, "%Y-%m-%d")).days
    if age > 10:
        sante.append({
            "categorie": "source-injoignable",
            "gravite": "moyenne",
            "titre": f"BOSS : le Raccourci iPhone n'a rien envoyé depuis {age} jours",
            "detail": ("La veille du BOSS dépend du Raccourci « Veille BOSS » de ton iPhone (le site bloque les "
                       "serveurs). Sa dernière capture date du " + recue + ". Vérifie l'automatisation dans "
                       "l'app Raccourcis (onglet Automatisation) ou lance-le à la main."),
            "lien": "https://boss.gouv.fr/",
            "date_texte": recue,
        })
    decouvertes = []
    premier = not pages_mem
    n_modif = n_lues = 0
    for u, page in pages.items():
        html_ok = _est_html(page)
        if html_ok:
            decouvertes += [l for l in liens_boss(page, u) if l not in decouvertes]
            paras, titre = paragraphes(page), titre_page(page, u)
        else:
            paras = _paras_texte(page)
            titre = paras[0][:120] if paras else u
        if not paras:
            continue
        n_lues += 1
        h = empreinte("\n".join(paras))
        avant = pages_mem.get(u)
        pages_mem[u] = {"titre": titre, "empreinte": h, "paragraphes": paras, "vu_le": aujourd_hui}
        if diag:
            print(f"  {court(titre, 80)} : {len(paras)} paragraphe(s){'' if html_ok else ' (texte brut)'}")
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
                       f"depuis la capture du {avant.get('vu_le') or '?'}.\n\n" + "\n".join(lignes)),
            "lien": u,
            "date_texte": aujourd_hui,
            "_id": f"boss:{u}:{h}",
        })
    if liste:
        n_liste = ecrire_liste_boss(liste, decouvertes)
        if diag:
            print(f"BOSS : {len(decouvertes)} lien(s) sur nos sujets trouvés ; liste du Raccourci : {n_liste} page(s).")
    mem["dernier"] = aujourd_hui
    print(f"BOSS : capture du {date_cap or recue}, {n_lues} page(s) lue(s), "
          + ("état de départ enregistré sans alerte." if premier else f"{n_modif} modifiée(s)."))


# ── PARLEMENT ─────────────────────────────────────────────────────────────
PARL_MAX_JOURS = 30
_MOIS_EN = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def date_flux(v):
    """« Fri,02 Oct 2026 », « Thu, 01 Oct 2026 10:00:00 +0200 », « 2026-10-01T… » -> « 2026-10-01 »."""
    v = str(v or "")
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", v)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(20\d\d)", v)
    if m and m.group(2).lower() in _MOIS_EN:
        return f"{m.group(3)}-{_MOIS_EN[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


def items_flux(octets):
    """octets bruts du flux : l'analyseur XML lit lui-même l'encodage déclaré
    (le Sénat publie en ISO-8859-1 : décodé en UTF-8, les accents étaient
    détruits et les mots-clés ne trouvaient plus « salariés »)."""
    xml_txt = None
    """RSS 2.0 ou Atom -> [(titre, lien, date, description)]."""
    out = []
    try:
        racine = ET.fromstring(octets)
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
    m = re.search(rb'encoding=["\']([A-Za-z0-9_-]+)', octets[:200])
    try:
        xml_txt = octets.decode(m.group(1).decode() if m else "utf-8", "replace")
    except LookupError:
        xml_txt = octets.decode("utf-8", "replace")
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
            items = items_flux(ouvrir_octets(url)[0])
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
        titres_vus = set()
        for titre, lien, date, desc in items:
            cle = lien or titre
            if not cle or cle in vus:
                continue
            vus[cle] = aujourd_hui
            # Test du 02/10/2026 : le flux « affaires sociales » du Sénat garde
            # ~200 éléments, dont tout le PLFSS 2026 de l'an dernier. Un élément
            # daté de plus de PARL_MAX_JOURS jours n'est pas une actualité.
            d = date_flux(date)
            if d and d < (datetime.strptime(aujourd_hui, "%Y-%m-%d") - timedelta(days=PARL_MAX_JOURS)).strftime("%Y-%m-%d"):
                continue
            if normaliser(titre) in titres_vus:          # même titre deux fois (tomes, doublons)
                continue
            titres_vus.add(normaliser(titre))
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
    # maj_dares.py (lundi, dépôt droit) note ce que la page officielle propose.
    try:
        src = json.load(open(os.path.join(droit, "ccn", "dares-source.json"), encoding="utf-8"))
    except Exception:
        src = {}
    nv = src.get("nouvelle_version")
    if nv:
        alertes.append({
            "categorie": "dares-perime",
            "gravite": "moyenne",
            "titre": f"Nouvelle liste DARES des conventions : {nv.get('fichier')}",
            "detail": (f"La DARES a publié {nv.get('fichier')} (vu le {nv.get('vue_le')}), mais le site bloque le "
                       f"téléchargement automatique. Le dépôt utilise encore {nom}.\n\nTélécharge-le avec le "
                       f"bouton ci-dessous et pose-le dans droit/ccn/ sous le nom Dares_Suivi_DERNIER.xlsx."),
            "lien": nv.get("url") or "",
            "date_texte": nv.get("vue_le") or aujourd_hui,
        })
        return
    verifie = src.get("verifie_le") or ""
    if src.get("a_jour") and verifie and \
            (datetime.strptime(aujourd_hui, "%Y-%m-%d") - datetime.strptime(verifie[:10], "%Y-%m-%d")).days <= 21:
        print(f"DARES : vérifié le {verifie} — c'est la dernière version publiée.")
        return
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


# ── FONDS DILA : circulaires, Conseil constitutionnel, Conseil d'État ─────
# Aspirés par dila-fonds.yml (dépôt droit) dans output/{circulaires,constit,jade}/ :
# une fiche par texte qui touche l'écosystème (le tri grossier est fait là-bas).
FONDS_DILA = {
    "circulaires": ("Circulaire / instruction", "📨", "nouvelle-circulaire"),
    "constit": ("Conseil constitutionnel", "🏛️", "decision-haute-juridiction"),
    "jade": ("Conseil d'État", "🏛️", "decision-haute-juridiction"),
}
CENSURE = re.compile(r"non[- ]conformite|contraire a la constitution|annul|abrog|censur|illegal", re.I)
FORT_DILA = re.compile(r"code du travail|heures? supplementaires?|duree du travail|conges? payes?|smic"
                       r"|cotisations?|reduction generale|convention collective|arrete d.extension", re.I)


def articles_cites_ecosysteme(chemin):
    try:
        return {k.partition(":")[2] for k in json.load(open(chemin, encoding="utf-8"))}
    except Exception:
        return set()


def veille_fonds_dila(droit, memoire, alertes, themes, cites, aujourd_hui, diag):
    if not droit:
        return
    mem = memoire.setdefault("fonds_dila", {})
    for dossier, (nom, emoji, categorie) in FONDS_DILA.items():
        racine = os.path.join(droit, "output", dossier)
        if not os.path.isdir(racine):
            if diag:
                print(f"{nom} : pas encore de fonds ({racine}).")
            continue
        fichiers = sorted(n for n in os.listdir(racine) if n.endswith(".json") and not n.startswith("_"))
        premier = dossier not in mem
        vus = set(mem.get(dossier) or [])
        nouveaux = [n for n in fichiers if n not in vus]
        mem[dossier] = sorted(vus | set(fichiers))[-20000:]
        if premier:
            print(f"{nom} : {len(fichiers)} texte(s) au fonds, état de départ sans alerte.")
            continue
        if len(nouveaux) > 150:
            alertes.append({"categorie": "rattrapage-fonds", "gravite": "basse",
                            "titre": f"{nom} ({aujourd_hui}) : {len(nouveaux)} textes arrivés d'un coup, enregistrés sans alerte",
                            "detail": "Rattrapage de l'aspirateur : textes anciens récupérés en masse.",
                            "_id": f"rattrapage:{dossier}:{aujourd_hui}"})
            continue
        retenus = 0
        for n in nouveaux:
            try:
                f = json.load(open(os.path.join(racine, n), encoding="utf-8"))
            except Exception:
                continue
            texte = f"{f.get('titre', '')} {f.get('solution', '')} {f.get('extrait', '')}"
            norm = normaliser(texte)
            trouves = themes_trouves(texte, themes)
            arts = [a for a in (f.get("articles") or []) if a in cites]
            if not trouves and not arts and not FORT_DILA.search(norm):
                continue
            retenus += 1
            censure = dossier != "circulaires" and bool(CENSURE.search(normaliser(f.get("solution", "") + " " + f.get("titre", ""))))
            haute = bool(arts) or (censure and bool(FORT_DILA.search(norm)))
            detail = (f"{nom}" + (f" — {f['juridiction']}" if f.get("juridiction") else "")
                      + (f" — n° {f['numero']}" if f.get("numero") else "")
                      + (f" — {f['date']}" if f.get("date") else "") + "."
                      + f"\n\n{court(f.get('titre'), 400)}"
                      + (f"\n\nSolution : {court(f.get('solution'), 300)}" if f.get("solution") else "")
                      + (f"\n\n⚠️ Articles que l'écosystème cite : {', '.join(arts)}" if arts else "")
                      + (f"\n\nExtrait : {court(f.get('extrait'), 500)}" if f.get("extrait") else ""))
            if trouves:
                detail += "\n\n" + "\n".join(f"{e} {t} — « {x} »" for t, e, x, _ in trouves)
            ident = str(f.get("id") or n[:-5])
            lien = (f"https://www.legifrance.gouv.fr/cons/id/{ident}" if ident.startswith("CONSTEXT") else
                    f"https://www.legifrance.gouv.fr/ceta/id/{ident}" if ident.startswith("CETATEXT") else
                    f"https://www.legifrance.gouv.fr/circulaire/id/{ident}" if dossier == "circulaires" else "")
            alertes.append({
                "categorie": categorie,
                "gravite": "haute" if haute else "moyenne",
                "titre": f"{emoji} {nom} — {court(f.get('titre'), 120)}" + (" : CENSURE / ANNULATION" if censure else ""),
                "detail": detail,
                "lien": lien,
                "date_texte": f.get("date") or aujourd_hui,
                "_id": f"dila:{dossier}:{ident}",
            })
        print(f"{nom} : {len(nouveaux)} texte(s) nouveau(x), {retenus} retenu(s).")


# ── PARAMÈTRES SOCIAUX HORS DROIT DU TRAVAIL (OpenFisca-France) ────────────
# Chômage, prestations familiales, minima sociaux, retraite complémentaire,
# cotisations, impôt… : les barèmes que certains des 105 outils utilisent.
# OpenFisca-France (le modèle socio-fiscal ouvert de l'État) les tient à jour
# avec leur date d'effet ; à chaque nouvelle version publiée sur PyPI, on
# compare les fichiers de paramètres ligne à ligne (pas besoin de PyYAML).
PYPI = "https://pypi.org/pypi/OpenFisca-France/json"
DOMAINES_OF = [
    ("chomage/", "Assurance chômage", ["chomage", "demission-are", "fincontrat", "activite-partielle"]),
    ("prestations_sociales/prestations_familiales/", "Prestations familiales",
     ["allocations-familiales", "famille", "parentalite", "naissance", "proche-aidant"]),
    ("prestations_sociales/solidarite_insertion/", "Minima sociaux (RSA, prime d'activité, ASS…)", ["budget", "chomage"]),
    ("prestations_sociales/prestations_etat_de_sante/", "Indemnités maladie, invalidité, AT-MP",
     ["arret", "invalidite", "atmp", "inaptitude"]),
    ("prestations_sociales/aides_logement/", "Aides au logement", ["logement", "loyer"]),
    ("prelevements_sociaux/regimes_complementaires_retraite_secteur_prive/", "Retraite complémentaire (Agirc-Arrco)",
     ["retraite", "cumul-retraite", "bulletin"]),
    ("prelevements_sociaux/cotisations_securite_sociale_regime_general/", "Cotisations de sécurité sociale",
     ["bulletin", "salaire-cout-employeur"]),
    ("prelevements_sociaux/reductions_cotisations_sociales/", "Réductions de cotisations (dont heures sup)",
     ["bulletin", "salaire-cout-employeur"]),
    ("prelevements_sociaux/pss/", "Plafond de la Sécurité sociale", ["bulletin", "salaire-cout-employeur", "retraite"]),
    ("prelevements_sociaux/contributions_sociales/", "CSG / CRDS", ["bulletin", "salaire-cout-employeur"]),
    ("marche_travail/salaire_minimum/", "SMIC et minimum garanti", ["bulletin", "salaire-cout-employeur", "alternance"]),
    ("marche_travail/indemnite_fin_contrat/", "Indemnité de fin de contrat", ["precarite", "fincontrat"]),
    ("impot_revenu/bareme_ir_depuis_1945/", "Barème de l'impôt sur le revenu", ["impot-revenu"]),
    ("impot_revenu/calcul_revenus_imposables/", "Revenus imposables (dont exonération heures sup)", ["impot-revenu"]),
    ("taxation_capital/epargne/", "Épargne réglementée", ["livrets-epargne", "epargne"]),
]


_VAL = re.compile(r"(\d{4}-\d{2}-\d{2})\s*:\s*\n\s*value\s*:\s*([^\n#]+)")


def _valeurs(yaml_txt):
    """Paires (date d'effet, valeur) d'un fichier de paramètres OpenFisca — les
    titres, liens et « last_value_still_valid_on » ne comptent pas (test du
    02/10/2026 : ils changeaient sans qu'aucune valeur ne bouge)."""
    return sorted((d, v.strip().strip("'\"")) for d, v in _VAL.findall(yaml_txt))


def _http_json(url):
    return json.loads(ouvrir_octets(url, delai=60)[0].decode("utf-8"))


def _params_wheel(info, version):
    for f in info.get("releases", {}).get(version, []):
        if f.get("packagetype") == "bdist_wheel":
            import zipfile
            octets = ouvrir_octets(f["url"], delai=300)[0]
            z = zipfile.ZipFile(io.BytesIO(octets))
            out = {}
            for n in z.namelist():
                if "/parameters/" in n and n.endswith(".yaml"):
                    out[n.split("/parameters/", 1)[1]] = z.read(n).decode("utf-8", "replace")
            return out
    return None


def outils_de(hs, mots):
    d = os.path.join(hs or "", "outils")
    if not os.path.isdir(d):
        return mots
    noms = [n[7:-5] for n in os.listdir(d) if n.startswith("module-") and n.endswith(".html")]
    return sorted({n for n in noms for m in mots if m in n})


def veille_openfisca(memoire, alertes, sante, hs, aujourd_hui, diag):
    mem = memoire.setdefault("openfisca", {})
    try:
        info = _http_json(PYPI)
        derniere = info["info"]["version"]
    except Exception as e:                           # noqa: BLE001
        _injoignable(mem, sante, "OpenFisca-France (PyPI)", PYPI, aujourd_hui)
        print(f"OpenFisca : PyPI illisible ({e}).")
        return
    mem["echecs"] = 0
    avant = mem.get("version")
    if not avant:
        mem["version"] = derniere
        print(f"OpenFisca : version de départ {derniere} enregistrée, pas d'alerte.")
        return
    if avant == derniere:
        print(f"OpenFisca : toujours en {derniere}.")
        return
    try:
        p_av, p_ap = _params_wheel(info, avant), _params_wheel(info, derniere)
    except Exception as e:                           # noqa: BLE001
        print(f"OpenFisca : téléchargement impossible ({e}), on réessaiera.")
        return
    if p_av is None or p_ap is None:
        mem["version"] = derniere
        print(f"OpenFisca : {avant} -> {derniere}, une des versions n'a pas de wheel ; départ recalé.")
        return
    n_alertes = 0
    for prefixe, nom, mots in DOMAINES_OF:
        lignes, fichiers, nouvelle_date = [], 0, False
        for chemin in sorted(set(p_av) | set(p_ap)):
            if not chemin.startswith(prefixe):
                continue
            a, b = _valeurs(p_av.get(chemin) or ""), _valeurs(p_ap.get(chemin) or "")
            if a == b:
                continue                      # seules les sources / descriptions ont bougé
            # Valeurs historiques ajoutées d'un coup (ex. ARE depuis 2008) = rattrapage
            # de la base, pas une actualité : on ne regarde que les 2 dernières années.
            recent = (datetime.strptime(aujourd_hui, "%Y-%m-%d") - timedelta(days=730)).strftime("%Y-%m-%d")
            ajoutees = [x for x in b if x not in a and x[0] >= recent]
            retirees = [x for x in a if x not in b and x[0] >= recent]
            if not ajoutees and not retirees:
                continue
            fichiers += 1
            nouvelle_date |= bool(ajoutees)
            lignes.append(f"• {chemin[len(prefixe):-5]}")
            lignes += [f"－ {d} : {court(val, 60)}" for d, val in retirees[:3]]
            lignes += [f"＋ à partir du {d} : {court(val, 60)}" for d, val in ajoutees[:4]]
        if not fichiers:
            continue
        n_alertes += 1
        outils = outils_de(hs, mots)
        alertes.append({
            "categorie": "parametre-social-modifie",
            "gravite": "haute" if nouvelle_date else "moyenne",
            "titre": f"Barème modifié — {nom} ({fichiers} paramètre(s))",
            "detail": (f"OpenFisca-France {avant} → {derniere} : des paramètres officiels de « {nom} » ont changé"
                       + (" (nouvelle valeur avec une date d'effet)" if nouvelle_date else "") + ".\n\n"
                       + "\n".join(lignes[:60])
                       + (f"\n\nOutils de l'appli à revoir : {', '.join(outils)}" if outils else "")
                       + "\n\nOpenFisca reprend les textes officiels (décrets, circulaires, délibérations) : "
                         "vérifie la valeur à la source avant de modifier l'outil."),
            "lien": f"https://github.com/openfisca/openfisca-france/tree/master/openfisca_france/parameters/{prefixe}",
            "date_texte": aujourd_hui,
            "_id": f"openfisca:{derniere}:{prefixe}",
        })
    mem["version"] = derniere
    print(f"OpenFisca : {avant} → {derniere}, {n_alertes} domaine(s) modifié(s).")


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
    ap.add_argument("--sans", default="", help="sources à sauter : boss,parlement,dares,fonds,openfisca")
    ap.add_argument("--boss-capture", default="", help="boss-capture.json déposé par le Raccourci iPhone")
    ap.add_argument("--boss-liste", default="", help="boss-pages.txt : pages que le Raccourci doit lire")
    ap.add_argument("--hs", default="", help="dépôt de l'appli (pour nommer les outils à revoir)")
    ap.add_argument("--empreintes-articles", default="", help="articles cités par l'écosystème")
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
            veille_boss(memoire, alertes, sante, aujourd_hui, args.diagnostic,
                        capture=args.boss_capture, liste=args.boss_liste)
        except Exception as e:                       # noqa: BLE001
            print(f"BOSS : erreur {e}")
    if "parlement" not in sans:
        try:
            veille_parlement(memoire, alertes, sante, themes, aujourd_hui, args.diagnostic)
        except Exception as e:                       # noqa: BLE001
            print(f"Parlement : erreur {e}")
    if "fonds" not in sans:
        try:
            veille_fonds_dila(args.droit, memoire, alertes, themes,
                              articles_cites_ecosysteme(args.empreintes_articles), aujourd_hui, args.diagnostic)
        except Exception as e:                       # noqa: BLE001
            print(f"Fonds DILA : erreur {e}")
    if "openfisca" not in sans:
        try:
            veille_openfisca(memoire, alertes, sante, args.hs, aujourd_hui, args.diagnostic)
        except Exception as e:                       # noqa: BLE001
            print(f"OpenFisca : erreur {e}")
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
