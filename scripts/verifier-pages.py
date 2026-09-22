#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFIER-PAGES.PY — ouvre VRAIMENT les pages de l'application (P6, 22/09/2026)

POURQUOI
verifier-syntaxe-js.py lit le code sans l'exécuter : il ne voit pas une page
qui plante au chargement (variable inconnue, fichier renommé, script absent).
Et deux pannes passées venaient d'un oubli dans le précache de sw.js
(nouveautes.html, puis taiko.html) : dans l'appli Android, la navigation
retombait en silence sur le menu. Aucun des deux n'aurait été vu ici.

CE QU'IL FAIT
  1. Sert la copie de l'application en HTTP local (pas en file:// : les chemins
     relatifs et le service worker ne s'y comportent pas comme en production).
  2. Ouvre chaque page .html dans Chromium, à neuf (stockage vide, comme un
     nouvel utilisateur), et relève :
       - les erreurs JavaScript levées au chargement ;
       - les fichiers de l'appli qui répondent 404 (script, style, image).
     Le service worker est bloqué pendant ces ouvertures : on teste la page
     elle-même, pas une copie en cache.
  3. Compare les pages et les fichiers locaux qu'elles chargent à la liste
     FILES_TO_CACHE de sw.js : ce qui manque ne s'ouvrira pas hors ligne.

Les ressources externes (polices, CDN) sont ignorées : le runner n'est pas un
téléphone, une panne réseau passagère ne doit pas devenir une alerte.

USAGE
    python3 verifier-pages.py --hs /chemin/vers/hs --json sortie.json
"""
import argparse
import functools
import glob
import http.server
import json
import os
import re
import socketserver
import threading
from urllib.parse import urlparse, unquote

ATTENTE_MS = 1500          # après « load » : laisse tourner les scripts de démarrage
DELAI_PAGE_MS = 20000      # une page qui ne finit pas de charger en 20 s est signalée


class _Silencieux(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serveur(racine):
    gestion = functools.partial(_Silencieux, directory=racine)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), gestion)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def liste_precache(chemin_sw):
    s = open(chemin_sw, encoding="utf-8", errors="replace").read()
    m = re.search(r"FILES_TO_CACHE\s*=\s*\[(.*?)\];", s, re.S)
    if not m:
        return None
    return {x.split("?")[0] for x in re.findall(r"[\"']\./([^\"']*)[\"']", m.group(1))}


def pages_html(racine):
    out = []
    for p in glob.glob(os.path.join(racine, "**", "*.html"), recursive=True):
        rel = os.path.relpath(p, racine).replace(os.sep, "/")
        if rel.startswith((".", "_")) or "/." in rel or "node_modules" in rel:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hs", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()
    racine = os.path.abspath(args.hs)
    resultat = {"module": "pages", "alertes": []}
    A = resultat["alertes"]

    pages = pages_html(racine)

    # --- 3. Précache (sans navigateur) ------------------------------------
    precache = liste_precache(os.path.join(racine, "sw.js"))
    if precache is None:
        A.append({"categorie": "precache-illisible", "gravite": "haute",
                  "titre": "sw.js : liste FILES_TO_CACHE introuvable",
                  "detail": "Impossible de vérifier ce qui s'ouvre hors ligne."})
    else:
        for p in pages:
            if p not in precache:
                A.append({"categorie": "page-hors-precache", "gravite": "haute",
                          "titre": f"{p} : absente du précache de sw.js",
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
                      "titre": f"{r} : chargé par une page mais absent du précache",
                      "detail": f"Chargé par {', '.join(sorted(qui)[:5])}"
                                + (f" (+{len(qui) - 5})" if len(qui) > 5 else "")
                                + ". Il ne sera disponible hors ligne qu'après une première visite en ligne."})

    # --- 1-2. Ouverture réelle ----------------------------------------------
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        resultat["erreur"] = "playwright non installé : pages non ouvertes"
        print(resultat["erreur"])
        pages_ouvertes = 0
    else:
        httpd, port = serveur(racine)
        origine = f"http://127.0.0.1:{port}"
        pages_ouvertes = 0
        with sync_playwright() as pw:
            nav = pw.chromium.launch()
            for p in pages:
                ctx = nav.new_context(service_workers="block", viewport={"width": 390, "height": 844})
                page = ctx.new_page()
                erreurs, absents = [], set()
                page.on("pageerror", lambda e, erreurs=erreurs: erreurs.append(str(e).split("\n")[0][:200]))

                def reponse(r, absents=absents):
                    if r.url.startswith(origine) and r.status == 404:
                        absents.add(unquote(urlparse(r.url).path.lstrip("/")))
                page.on("response", reponse)
                try:
                    page.goto(f"{origine}/{p}", wait_until="load", timeout=DELAI_PAGE_MS)
                    page.wait_for_timeout(ATTENTE_MS)
                    pages_ouvertes += 1
                except Exception as e:
                    A.append({"categorie": "page-ne-charge-pas", "gravite": "haute",
                              "titre": f"{p} : ne finit pas de charger",
                              "detail": str(e).split("\n")[0][:200]})
                if erreurs:
                    uniques = list(dict.fromkeys(erreurs))
                    A.append({"categorie": "page-erreur-js", "gravite": "haute",
                              "titre": f"{p} : erreur JavaScript au chargement",
                              "detail": " · ".join(uniques[:3])
                                        + (f" (+{len(uniques) - 3})" if len(uniques) > 3 else "")})
                absents.discard("favicon.ico")
                # Une image absente est un défaut d'affichage (souvent déjà
                # rattrapé par un onerror, ex. Mascotte.png des outils) ; un
                # script ou un style absent casse la page. Gravités distinctes.
                images = {a for a in absents if re.search(r"\.(png|jpe?g|gif|webp|svg|ico)$", a, re.I)}
                autres = absents - images
                if autres:
                    A.append({"categorie": "page-fichier-404", "gravite": "haute",
                              "titre": f"{p} : fichier introuvable (404)",
                              "detail": ", ".join(sorted(autres)[:6])})
                if images:
                    A.append({"categorie": "page-image-404", "gravite": "basse",
                              "titre": f"{p} : image introuvable (404)",
                              "detail": ", ".join(sorted(images)[:6])})
                ctx.close()
            nav.close()
        httpd.shutdown()

    print(f"{len(pages)} page(s), {pages_ouvertes} ouverte(s), {len(A)} alerte(s).")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
