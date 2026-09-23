#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-PAGES.PY — ouvre VRAIMENT chaque page, de l'appli ET du guide (P6)

POURQUOI
verifier-syntaxe-js.py lit le code sans l'exécuter : il ne voit pas une page
qui plante au chargement (variable inconnue, fichier renommé, script absent).
Et deux pannes passées venaient d'un oubli dans le précache de sw.js
(nouveautes.html, puis taiko.html) : dans l'appli Android, la navigation
retombait en silence sur le menu. Aucun des deux n'aurait été vu ici.

CE QU'IL FAIT
  1. Sert l'appli (et le guide) en HTTP local — pas en file:// : les chemins
     relatifs et le service worker ne s'y comportent pas comme en production.
  2. Ouvre chaque page .html dans Chromium, à neuf (stockage vide, comme un
     nouvel utilisateur), et relève :
       - les erreurs JavaScript levées au chargement ;
       - les fichiers de l'appli qui répondent 404 (script, style, image) ;
       - les pages qui ne finissent pas de charger.
     Le service worker est bloqué : on teste la page elle-même, pas un cache.
  3. Compare les pages et leurs fichiers locaux à FILES_TO_CACHE de sw.js
     (appli seulement : le guide n'a pas de service worker).
  4. Relève les articles de loi VISIBLES dans la page une fois le JavaScript
     exécuté (ex. « L3121-36 »), et les écrit dans --articles : c'est ce que
     lit vraiment l'utilisateur, y compris ce qui est injecté par script et
     qu'une lecture du code source ne voit pas. Sert au croisement avec le
     fonds juridique (dépôt droit).

VITESSE
  Plusieurs pages en parallèle (--parallele, 4 par défaut) : ~1 100 pages
  (appli + guide) en 8 à 10 minutes sur un runner GitHub, contre une demi-heure
  une par une.

Les ressources externes (polices, CDN) sont ignorées : le runner n'est pas un
téléphone, une panne réseau passagère ne doit pas devenir une alerte.

USAGE
    python3 verifier-pages.py --hs ../_hs [--guide ../_guide] \
        [--parallele 4] [--json sortie.json] [--articles pages-articles.json]
"""
import argparse
import asyncio
import fnmatch
import functools
import glob
import http.server
import json
import os
import re
import socketserver
import threading
from urllib.parse import urlparse, unquote

ATTENTE_MS = 1200          # après « load » : laisse tourner les scripts de démarrage
DELAI_PAGE_MS = 20000      # une page qui ne finit pas de charger en 20 s est signalée
ART = re.compile(r"\b((?:L|R|D)\.?\s?\d{3,4}-\d{1,3}(?:-\d{1,2})?)\b")


class _Silencieux(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            # Page fermée avant la fin d'un téléchargement : sans intérêt ici.
            self.close_connection = True


def serveur(racine):
    gestion = functools.partial(_Silencieux, directory=racine)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), gestion)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def liste_precache(chemin_sw):
    if not os.path.isfile(chemin_sw):
        return None
    s = open(chemin_sw, encoding="utf-8", errors="replace").read()
    m = re.search(r"FILES_TO_CACHE\s*=\s*\[(.*?)\];", s, re.S)
    if not m:
        return None
    return {x.split("?")[0] for x in re.findall(r"[\"']\./([^\"']*)[\"']", m.group(1))}


def pages_html(racine, ignorer=()):
    out = []
    for p in glob.glob(os.path.join(racine, "**", "*.html"), recursive=True):
        rel = os.path.relpath(p, racine).replace(os.sep, "/")
        if rel.startswith((".", "_")) or "/." in rel or "node_modules" in rel:
            continue
        # Les pages d'aperçu du guide recopient la structure de l'appli pour
        # donner envie de la télécharger : leurs boutons pointent vers des
        # fichiers de l'appli, absents du guide, et ne sont pas censés
        # fonctionner ici. Même exclusion que verifier-liens.py.
        if any(fnmatch.fnmatch(os.path.basename(rel), m) for m in ignorer):
            continue
        out.append(rel)
    return sorted(out)


_REF = re.compile(r"""<(?:script|link|img)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"'#]+)["']""", re.I)


def ressources_locales(racine, page):
    """Fichiers locaux chargés par une page (scripts, styles, images) — pas les liens <a>."""
    s = open(os.path.join(racine, page), encoding="utf-8", errors="replace").read()
    base = os.path.dirname(page)
    out = set()
    for url in _REF.findall(s):
        if re.match(r"^(?:[a-z]+:|//|data:)", url, re.I):
            continue
        chemin = os.path.normpath(os.path.join(base, url.split("?")[0])).replace(os.sep, "/")
        if chemin.startswith(".."):
            continue
        out.add(chemin)
    return out


def alertes_precache(racine, pages, prefixe):
    """Contrôle du hors-ligne — appli seulement (le guide n'a pas de sw.js)."""
    A = []
    precache = liste_precache(os.path.join(racine, "sw.js"))
    if precache is None:
        A.append({"categorie": "precache-illisible", "gravite": "haute",
                  "titre": "sw.js : liste FILES_TO_CACHE introuvable",
                  "detail": "Impossible de vérifier ce qui s'ouvre hors ligne."})
        return A
    for p in pages:
        if p not in precache:
            A.append({"categorie": "page-hors-precache", "gravite": "haute",
                      "titre": f"{prefixe}{p} : absente du précache de sw.js",
                      "detail": "Hors ligne, et dans l'appli Android, cette page ne s'ouvrira pas : "
                                "la navigation retombe sur le menu. Ajouter "
                                f"\"./{p}\" à FILES_TO_CACHE et incrémenter CACHE_NAME."})
    manquantes = {}
    for p in pages:
        if p not in precache:
            continue          # déjà signalée
        for r in ressources_locales(racine, p):
            if r not in precache and os.path.isfile(os.path.join(racine, r)):
                manquantes.setdefault(r, []).append(p)
    for r, qui in sorted(manquantes.items()):
        A.append({"categorie": "ressource-hors-precache", "gravite": "moyenne",
                  "titre": f"{prefixe}{r} : chargé par une page mais absent du précache",
                  "detail": f"Chargé par {', '.join(sorted(qui)[:5])}"
                            + (f" (+{len(qui) - 5})" if len(qui) > 5 else "")
                            + ". Il ne sera disponible hors ligne qu'après une première visite en ligne."})
    return A


async def _ouvrir(nav, origine, page_rel, prefixe, articles, est_appli=True):
    """Ouvre une page dans un contexte neuf et renvoie ses alertes."""
    A = []
    ctx = await nav.new_context(service_workers="block", viewport={"width": 390, "height": 844})
    page = await ctx.new_page()
    erreurs, absents = [], set()
    page.on("pageerror", lambda e: erreurs.append(str(e).split("\n")[0][:200]))

    def reponse(r):
        if r.url.startswith(origine) and r.status == 404:
            absents.add(unquote(urlparse(r.url).path.lstrip("/")))
    page.on("response", reponse)
    try:
        await page.goto(f"{origine}/{page_rel}", wait_until="load", timeout=DELAI_PAGE_MS)
        await page.wait_for_timeout(ATTENTE_MS)
        try:
            texte = await page.evaluate("document.body ? document.body.innerText : ''")
        except Exception:
            texte = ""
        vus = sorted({re.sub(r"[.\s]", "", a) for a in ART.findall(texte or "")})
        if vus:
            articles[prefixe + page_rel] = vus
    except Exception as e:
        A.append({"categorie": "page-ne-charge-pas", "gravite": "haute",
                  "titre": f"{prefixe}{page_rel} : ne finit pas de charger",
                  "detail": str(e).split("\n")[0][:200]})
    if erreurs:
        uniques = list(dict.fromkeys(erreurs))
        A.append({"categorie": "page-erreur-js", "gravite": "haute",
                  "titre": f"{prefixe}{page_rel} : erreur JavaScript au chargement",
                  "detail": " · ".join(uniques[:3]) + (f" (+{len(uniques) - 3})" if len(uniques) > 3 else "")})
    absents.discard("favicon.ico")
    # Une image absente est un défaut d'affichage (souvent déjà rattrapé par un
    # onerror, ex. Mascotte.png des outils) ; un script ou un style absent casse
    # la page. Gravités distinctes.
    images = {a for a in absents if re.search(r"\.(png|jpe?g|gif|webp|svg|ico)$", a, re.I)}
    autres = absents - images
    if autres:
        A.append({"categorie": "page-fichier-404", "gravite": "haute" if est_appli else "moyenne",
                  "titre": f"{prefixe}{page_rel} : fichier introuvable (404)",
                  "detail": ", ".join(sorted(autres)[:6])})
    if images:
        A.append({"categorie": "page-image-404", "gravite": "basse",
                  "titre": f"{prefixe}{page_rel} : image introuvable (404)",
                  "detail": ", ".join(sorted(images)[:6])})
    await ctx.close()
    return A


async def ouvrir_site(racine, pages, prefixe, parallele, articles, est_appli=True):
    from playwright.async_api import async_playwright
    httpd, port = serveur(racine)
    origine = f"http://127.0.0.1:{port}"
    A, faites = [], 0
    file = asyncio.Queue()
    for p in pages:
        file.put_nowait(p)
    async with async_playwright() as pw:
        nav = await pw.chromium.launch()

        async def ouvrier():
            nonlocal faites
            while True:
                try:
                    p = file.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    A.extend(await _ouvrir(nav, origine, p, prefixe, articles, est_appli))
                except Exception as e:
                    A.append({"categorie": "page-ne-charge-pas", "gravite": "haute",
                              "titre": f"{prefixe}{p} : ne finit pas de charger",
                              "detail": str(e).split("\n")[0][:200]})
                faites += 1
                if faites % 100 == 0:
                    print(f"  … {faites}/{len(pages)} pages ouvertes", flush=True)

        await asyncio.gather(*[ouvrier() for _ in range(max(1, parallele))])
        await nav.close()
    httpd.shutdown()
    return A, faites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--guide", help="Racine du dépôt Guide (optionnel)")
    ap.add_argument("--parallele", type=int, default=4)
    ap.add_argument("--ignorer-guide", default="apercu*.html",
                    help="Motifs de pages du guide à ne pas ouvrir, séparés par des virgules")
    ap.add_argument("--json")
    ap.add_argument("--articles", help="Écrire les articles de loi visibles par page (pour le croisement avec le fonds)")
    args = ap.parse_args()

    resultat = {"module": "pages", "alertes": []}
    A = resultat["alertes"]
    articles = {}

    ignorer = [m.strip() for m in (args.ignorer_guide or "").split(",") if m.strip()]
    sites = [(os.path.abspath(args.hs), "", True, ())]
    if args.guide:
        sites.append((os.path.abspath(args.guide), "guide:", False, tuple(ignorer)))

    total_pages = 0
    for racine, prefixe, est_appli, ign in sites:
        pages = pages_html(racine, ign)
        total_pages += len(pages)
        if est_appli:
            A.extend(alertes_precache(racine, pages, prefixe))
        try:
            import playwright  # noqa: F401
        except ImportError:
            resultat["erreur"] = "playwright non installé : pages non ouvertes"
            print(resultat["erreur"])
            break
        print(f"{len(pages)} page(s) à ouvrir dans {racine}", flush=True)
        alertes, faites = asyncio.run(ouvrir_site(racine, pages, prefixe, args.parallele, articles, est_appli))
        A.extend(alertes)
        print(f"  {faites} page(s) ouverte(s).", flush=True)

    if args.articles:
        with open(args.articles, "w", encoding="utf-8") as f:
            json.dump({"pages": articles,
                       "articles": sorted({a for v in articles.values() for a in v})}, f,
                      ensure_ascii=False, indent=2)
        print(f"{sum(len(v) for v in articles.values())} citation(s) visible(s) relevée(s) dans {args.articles}")

    print(f"{total_pages} page(s) au total, {len(A)} alerte(s).")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
