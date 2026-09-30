# -*- coding: utf-8 -*-
"""
VEILLE_COMMUN.PY — petites fonctions partagées par la veille des nouveaux
textes (veille-textes.py), le filtre MonLegiTexte (verifier-droit.py) et la
veille des articles cités (verifier-contenu-articles.py).

Rien ici n'écrit de fichier : lecture de mots-cles.json, recherche
d'expressions, extraction de texte d'une fiche du fonds, liens Légifrance.
"""
import json
import os
import re
import unicodedata

MONLEGITEXTE = "https://monlegitexte.heuressupfrance.workers.dev/"


def normaliser(t):
    """Minuscules, sans accents, apostrophes unifiées, espaces simples : la
    recherche d'une expression ne doit pas dépendre de « é » contre « e » ni
    de l'apostrophe typographique."""
    t = unicodedata.normalize("NFD", str(t or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("’", "'").replace(" ", " ").lower()
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def charger_mots_cles(chemin):
    """-> (themes, exclusions). themes = [{nom, emoji, motifs:[(expr, regex)]}].
    Fichier absent ou illisible : veille par mots-clés désactivée (listes vides),
    jamais un plantage de tout le passage."""
    try:
        d = json.load(open(chemin, encoding="utf-8"))
    except Exception:
        return [], []
    themes = []
    for t in d.get("themes", []):
        motifs = []
        for e in t.get("expressions", []):
            n = normaliser(e)
            if n:
                # Bornes de mot : « astreinte » ne doit pas matcher « astreintes »
                # d'un autre mot, et « forfait jours » pas « forfait journalier ».
                motifs.append((e, re.compile(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])")))
        if motifs:
            themes.append({"nom": t.get("nom", "?"), "emoji": t.get("emoji", "🔎"), "motifs": motifs})
    exclusions = [normaliser(x) for x in d.get("exclusions", []) if normaliser(x)]
    return themes, exclusions


def exclu(titre, exclusions):
    n = normaliser(titre)
    return any(x in n for x in exclusions)


def themes_trouves(texte, themes, largeur=160):
    """-> [(nom_theme, emoji, expression, extrait)] : un résultat par thème
    (la première expression trouvée), avec l'extrait autour du mot."""
    n = normaliser(texte)
    out = []
    for t in themes:
        for expr, rx in t["motifs"]:
            m = rx.search(n)
            if m:
                deb = max(0, m.start() - largeur)
                fin = min(len(n), m.end() + largeur)
                extrait = ("…" if deb else "") + n[deb:fin].strip() + ("…" if fin < len(n) else "")
                out.append((t["nom"], t["emoji"], expr, extrait))
                break
    return out


_CLES_TEXTE = ("texte", "content", "text", "titre", "title", "kw")


def texte_de(obj, limite=400000):
    """Tout le texte lisible d'une fiche du fonds, quelle que soit sa forme
    (article de code, texte JORF, accord, convention) : on descend dans la
    structure et on garde les champs qui portent du texte."""
    morceaux = []
    total = [0]

    def descendre(o):
        if total[0] > limite:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k in _CLES_TEXTE:
                    morceaux.append(v)
                    total[0] += len(v)
                elif isinstance(v, (dict, list)):
                    descendre(v)
        elif isinstance(o, list):
            for v in o:
                descendre(v)

    descendre(obj)
    return " ".join(morceaux)


# « article L. 3121-36 », « L3121-36 », « R. 3121-1 », « D. 241-21 »
_REF = re.compile(r"\b([LRD])\.?\s?(\d{3,4}(?:-\d+){1,3})\b")


def refs_articles(texte):
    """Numéros d'articles de code cités dans un texte, au format du fonds (L3121-36)."""
    return {m.group(1) + m.group(2) for m in _REF.finditer(str(texte or ""))}


def lien_legifrance(identifiant):
    i = str(identifiant or "")
    if i.startswith("JORFTEXT"):
        return f"https://www.legifrance.gouv.fr/jorf/id/{i}"
    if i.startswith("KALITEXT") or i.startswith("KALICONT"):
        return f"https://www.legifrance.gouv.fr/conv_coll/id/{i}"
    if i.startswith("ACCOTEXT"):
        return f"https://www.legifrance.gouv.fr/acco/id/{i}"
    if i.startswith("LEGIARTI"):
        return f"https://www.legifrance.gouv.fr/codes/article_lc/{i}"
    return ""


def lien_monlegitexte(num, code="CT"):
    return MONLEGITEXTE + f"?art={num}" + ("&code=secu" if code == "CSS" else "")


def idcc_de_l_appli(racine_hs):
    """IDCC pour lesquels l'appli a une grille (GrillePaye/ccn-data.json)."""
    try:
        d = json.load(open(os.path.join(racine_hs, "GrillePaye", "ccn-data.json"), encoding="utf-8"))
        return {str(k) for k in (d.get("grilles") or {})}
    except Exception:
        return set()
