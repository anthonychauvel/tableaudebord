#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROUTAGE.PY — dit, pour chaque alerte, OÙ elle se traite dans l'écosystème
(03/10/2026).

Avant : une alerte disait « ce qui se passe », jamais « qui doit bouger ».
Maintenant chaque alerte reçoit :

  "cibles": [ {"zone": "app"|"outils"|"grilles"|"guide"|"mlt"|"veille",
               "cible": "Mizuki — temps partiel",          (libellé lisible)
               "fichiers": ["module5/index.html"],          (chemins dans le dépôt)
               "plus": 0,                                   (fichiers non listés)
               "action": "Vérifier le calcul …",
               "auto": false,                               (true = se met à jour seul)
               "raison": "thème : temps partiel"} , … ]
  "zones":  ["app", "guide"]   (dans l'ordre d'importance, sans doublon)

Une alerte peut viser plusieurs endroits (un décret sur les heures sup touche
le compteur annuel, la paye, Fox, l'outil Temps & Repos ET les pages du guide
qui citent les mêmes articles).

Comment la destination est trouvée, du plus sûr au plus large :
  1. la CATÉGORIE de l'alerte (une grille → GrillePaye ; une étape de
     l'aspirateur → la chaîne de veille ; un noindex → MonLegiTexte) ;
  2. les FICHIERS nommés dans le titre ou le détail (« outils/module-cet.html »,
     « guide:conge-paye-calcul.html », « grillepaye:ccn-data.json ») ;
  3. les ARTICLES de loi cités (L3121-28…) : tous les fichiers de l'appli et
     du guide qui les citent (index construit sur les dépôts, comme
     verifier-citations-ecosysteme.py) ;
  4. les IDCC : GrillePaye, les règles conventionnelles de l'appli
     (ccn/conventions-collectives.js) et les pages du guide qui en parlent ;
  5. le THÈME (mots du titre) : heures sup → compteur, paye, Fox ; temps
     partiel → Mizuki ; forfait jours → Zenji ; chômage → outils Chômage et
     Démission légitime ; etc.

Rien n'est inventé : sans dépôt (--hs / --guide absents), les étapes 3 et 4
ne listent que ce qui est écrit dans l'alerte.
"""
import glob
import importlib.util
import json
import os
import re
import sys
import unicodedata

ZONES = {
    "app":     {"nom": "Application", "emoji": "📱", "depot": "hs"},
    "outils":  {"nom": "105 outils", "emoji": "🧰", "depot": "hs"},
    "grilles": {"nom": "GrillePaye · Lumina", "emoji": "💶", "depot": "hs"},
    "guide":   {"nom": "Guide", "emoji": "📘", "depot": "guide"},
    "mlt":     {"nom": "MonLegiTexte", "emoji": "⚖️", "depot": "droit"},
    "veille":  {"nom": "Chaîne de veille", "emoji": "🩺", "depot": "tableaudebord"},
}
ORDRE_ZONES = ["app", "outils", "grilles", "guide", "mlt", "veille"]

# Dossiers de l'appli -> (clé, libellé). Clé = sous-cible stable pour l'interface.
MODULES = {
    "heures":  "M1 · Compteur annuel des heures sup",
    "paye":    "M2 · Heures mensualisées (paye)",
    "fox":     "M3 · Fox, moteur juridique",
    "module4": "M4 · DTE, prédiction santé et repos",
    "module5": "M5 · Mizuki, temps partiel",
    "module6": "M6 · Zenji, cadres et forfaits",
    "module7": "M7 · Mimizuku, nuit, astreintes, primes",
    "taiko":   "Taiko, plannings",
    "ccn":     "Règles des conventions (HS, temps partiel, forfaits)",
    "coquille": "Coquille de l'appli (menu, cache hors ligne, manifest)",
    "commun":  "Fichiers communs (références de loi, glossaire, scripts)",
}
FICHIER_MODULE = {
    "heures": "heures/index.html", "paye": "paye/index.html", "fox": "fox/index.html",
    "module4": "module4/index.html", "module5": "module5/index.html",
    "module6": "module6/index.html", "module7": "module7/index.html",
    "taiko": "taiko.html", "ccn": "ccn/conventions-collectives.js", "coquille": "menu.html",
}
RACINE_COQUILLE = {"menu.html", "sw.js", "manifest.json", "index.html", "nouveautes.html",
                   "outils.html", "sommaire.html", "etat-appli.html", "_headers", "_redirects",
                   "mentions-legales.html", "privacy.html"}

# Thèmes : motif (texte normalisé sans accents) -> destinations.
# Destination = ("app", module) | ("outils", nom d'outil sans « module- ») |
#               ("grilles", None) ; guide = mots de nom de fichier du guide.
THEMES = [
    ("heures supplementaires", r"heures? sup(?:plementaires?)?\b|\bhs\b|majorations? de salaire|contingent annuel|exoneration (?:des |d.impot sur les )?heures",
     [("app", "heures"), ("app", "paye"), ("app", "fox"), ("outils", "temps")],
     ["heures-supplementaires-guide", "calcul-exoneration-hs", "declaration-impots-heures", "hs-salaires-nets", "depassement-contingent", "heures-non-payees"]),
    ("durée du travail", r"duree (?:du|de) travail|temps de travail|durees? maximales? (?:de |du )?travail|amenagement du temps|annualisation|modulation|equivalences? horaires?",
     [("app", "heures"), ("app", "fox"), ("app", "taiko"), ("outils", "temps"), ("outils", "modulation")],
     ["durees-maximales-travail", "horaires-individualises", "equivalences-horaires", "badgeage"]),
    ("temps partiel", r"temps partiel|heures? complementaires?",
     [("app", "module5")], ["temps-partiel", "clause-exclusivite-temps-partiel"]),
    ("forfaits cadres", r"forfaits? (?:en |annuels? en )?jours|forfait (?:annuel )?en heures|cadres? (?:dirigeants?|autonomes?)",
     [("app", "module6")], ["forfait-jours", "forfait-annuel-heures", "forfait-heures-cadre", "cadre-dirigeant", "convention-forfait-jours"]),
    ("congés payés", r"conges? payes?|repos et conges|jours? feries?|journee de solidarite",
     [("app", "heures"), ("app", "paye"), ("outils", "conges"), ("outils", "feries")],
     ["conge-paye-calcul", "conges-payes-maladie", "demande-conges-payes", "hs-pendant-conge-paye", "dimanche-jours-feries"]),
    ("repos, nuit, dimanche", r"repos (?:quotidien|hebdomadaire|compensateur|dominical)|travail de nuit|travailleurs? de nuit|travail (?:du|le) dimanche|dimanche",
     [("app", "module4"), ("app", "module7"), ("app", "fox"), ("app", "taiko"), ("outils", "temps")],
     ["travail-de-nuit", "travail-nuit", "dimanche", "repos-"]),
    ("astreintes", r"astreintes?", [("app", "module7"), ("outils", "astreintes")], ["astreinte"]),
    ("salaires minima", r"salaires? minima|salaires? minimum|remunerations? minimales?|grilles? (?:de )?salaires?|classifications?|\bsmic\b|valeur du point|revalorisation des salaires",
     [("grilles", None), ("outils", "salaire-cout-employeur"), ("outils", "convertisseur")],
     ["grille-salaire-convention", "smic"]),
    ("cotisations", r"cotisations?|reduction generale|allegements?|exonerations?|\bcsg\b|\bcrds\b|urssaf|plafond (?:annuel |mensuel )?de la securite sociale|financement de la securite sociale|assiette|\bplfss\b|\blfss\b",
     [("app", "paye"), ("outils", "bulletin"), ("outils", "salaire-cout-employeur"), ("outils", "lexique")],
     ["bulletin-paie-comprendre", "csg-crds", "controle-redressement-urssaf", "hs-salaires-nets-bruts"]),
    ("avantages et frais", r"avantages? en nature|frais professionnels|indemnites? kilometriques?",
     [("outils", "avantages-nature"), ("outils", "bulletin")], ["avantage-nature", "avantages-nature", "frais-professionnels", "indemnite-kilometrique"]),
    ("titres-restaurant", r"titres?.restaurant", [("outils", "tr")], ["titre-restaurant", "titres-restaurant"]),
    ("licenciement", r"licenciement|bareme macron|indemnite de depart",
     [("outils", "fincontrat"), ("outils", "preavis-comp"), ("outils", "preavis")],
     ["indemnite-licenciement", "bareme-macron", "licenciement"]),
    ("rupture conventionnelle", r"rupture conventionnelle", [("outils", "rupture"), ("outils", "preavis-comp")],
     ["rupture-conventionnelle"]),
    ("préavis", r"preavis", [("outils", "preavis"), ("outils", "preavis-comp")], ["demission-droits-preavis", "preavis"]),
    ("fin de CDD", r"precarite|fin de contrat|contrats? a duree determinee|\bcdd\b",
     [("outils", "precarite"), ("outils", "contrats"), ("outils", "fincontrat")], ["ifc-indemnite-fin-cdd", "cdd-motifs", "checklist-fin-contrat"]),
    ("solde de tout compte", r"solde de tout compte", [("outils", "fincontrat2")], ["solde-tout-compte"]),
    ("assurance chômage", r"assurance chomage|allocation d.aide au retour|\bare\b|france travail|unedic|privation (?:involontaire )?d.emploi",
     [("outils", "chomage"), ("outils", "demission-are")], ["chomage-are", "demission-legitime-are", "attestation-france-travail"]),
    ("retraite", r"retraites?|agirc|arrco|\bcnav\b|cumul emploi|pension de vieillesse",
     [("outils", "retraite"), ("outils", "cumul-retraite")], ["retraite"]),
    ("maladie, accident", r"arrets? (?:de travail|maladie)|indemnites? journalieres?|accidents? du travail|maladies? professionnelles?|inaptitude|invalidite|\bijss\b",
     [("outils", "arret"), ("outils", "atmp"), ("outils", "inaptitude"), ("outils", "invalidite")],
     ["arret-maladie", "accident-travail", "inaptitude", "invalidite"]),
    ("famille", r"prestations? familiales?|allocations? familiales|\bcaf\b|\bbmaf\b|conge (?:de )?(?:maternite|paternite|naissance)|conge parental|proche aidant|presence parentale",
     [("outils", "allocations-familiales"), ("outils", "famille"), ("outils", "parentalite"), ("outils", "proche-aidant")],
     ["conge-naissance", "conge-paternite", "conges-maternite", "conge-parental", "conge-proche-aidant", "conges-evenements-familiaux"]),
    ("formation, alternance", r"formation professionnelle|\bcpf\b|apprenti(?:ssage|s)?|alternance|contrat de professionnalisation",
     [("outils", "formation"), ("outils", "alternance")], ["formation-cpf", "contrat-apprentissage", "contrat-professionnalisation", "apprenti"]),
    ("télétravail", r"teletravail", [("outils", "teletravail")], ["teletravail"]),
    ("activité partielle", r"activite partielle|chomage partiel", [("outils", "activite-partielle")], ["activite-partielle", "chomage-partiel"]),
    ("grève", r"\bgreve\b", [("outils", "greve")], ["greve"]),
    ("représentation du personnel", r"\bcse\b|comite social|representants? du personnel|heures de delegation|delegue syndical",
     [("outils", "cse"), ("outils", "delegation")], ["cse-", "heures-delegation", "delegation-syndicale"]),
    ("égalité professionnelle", r"egalite professionnelle|index (?:de l.)?egalite|ecarts? de remuneration|transparence salariale",
     [("outils", "egalite")], ["egalite-"]),
    ("épargne salariale, CET", r"compte epargne.temps|\bcet\b|interessement|participation aux resultats|epargne salariale|\bpee\b|\bpercol?\b",
     [("outils", "cet"), ("outils", "epargne")], ["compte-epargne-temps", "epargne-salariale", "interessement"]),
    ("saisie sur salaire", r"saisies? (?:sur salaire|des remunerations)", [("outils", "saisie")], ["saisie"]),
    ("santé, prévoyance", r"complementaire sante|mutuelle|prevoyance", [("outils", "mutuelle")], ["mutuelle", "prevoyance"]),
    ("transport", r"mobilites? durables?|frais de transport|prise en charge des transports|indemnite transport",
     [("outils", "mobilites"), ("outils", "transport")], ["forfait-mobilites", "indemnite-transport"]),
    ("pénibilité", r"penibilite|\bc2p\b", [("outils", "c2p")], ["c2p-penibilite"]),
    ("période d'essai", r"periode d.essai", [("outils", "essai")], ["periode-essai"]),
    ("ancienneté", r"anciennete", [("outils", "anciennete")], ["anciennete"]),
    ("non-concurrence", r"non.concurrence", [("outils", "nonconcurrence")], ["clause-non-concurrence"]),
    ("impôt sur le revenu", r"impot sur le revenu|bareme de l.impot|prelevement a la source",
     [("outils", "impot-revenu")], ["declaration-fiscale-hs", "heures-supplementaires-foyer-fiscal"]),
    ("épargne réglementée", r"livret a\b|livrets? reglementes?|\bldds\b|\blep\b", [("outils", "livrets-epargne")], []),
    ("seuils d'effectif", r"seuils? d.effectifs?", [("outils", "effectifs")], []),
    ("entretien professionnel", r"entretien professionnel", [("outils", "entretien")], ["entretien-professionnel"]),
]


# Noms courts employés par les autres scripts de veille -> nom de fichier.
ALIAS_OUTILS = {"convertisseur paie": "convertisseur", "carnet de frais pro": "avantages-nature",
                "bulletin decrypte": "bulletin", "net · brut": "salaire-cout-employeur"}


# ───────────────────────────── utilitaires ─────────────────────────────

def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn")
    return t.lower().replace("’", "'")


_ART = re.compile(r"\b([LRD])\.?\s?(\d{3,4}(?:-\d+){1,3})\b")
_IDCC = re.compile(r"IDCC\s*(?:n°\s*)?(\d{1,4})\b|\(n°\s*(\d{1,4})\)", re.I)


def articles_de(texte):
    return sorted({m.group(1) + m.group(2) for m in _ART.finditer(texte or "")})


_IDCC_STRICT = re.compile(r"IDCC\s*(?:n°\s*)?(\d{1,4})\b()", re.I)


def idcc_de(texte, strict=False):
    out = []
    for m in (_IDCC_STRICT if strict else _IDCC).finditer(texte or ""):
        n = (m.group(1) or m.group(2)).lstrip("0") or "0"
        if n not in out:
            out.append(n)
    return out


# ───────────────────────────── index des dépôts ─────────────────────────────

class Index:
    """Ce qu'il faut savoir des dépôts pour router : qui cite quel article,
    quelles pages du guide parlent de quelle convention, le nom des outils."""

    def __init__(self, hs=None, guide=None, pages_articles=None):
        self.hs = hs if hs and os.path.isdir(hs) else None
        self.guide = guide if guide and os.path.isdir(guide) else None
        self.citations = {}          # article -> [(zone_brute, chemin)]
        self.idcc_guide = {}         # idcc -> [page]
        self.idcc_regles = set()     # IDCC présents dans ccn/conventions-collectives.js
        self.idcc_grilles = {}       # idcc -> nom (GrillePaye/ccn-data.json)
        self.outils = {}             # nom court -> titre
        self.noms_idcc = {}          # idcc -> nom de la convention
        self.pages_guide = []
        self._charger_citations(pages_articles)
        self._charger_hs()
        self._charger_guide()

    def _charger_citations(self, pages_articles):
        ici = os.path.dirname(os.path.abspath(__file__))
        chemin = os.path.join(ici, "verifier-citations-ecosysteme.py")
        if self.hs and os.path.isfile(chemin):
            try:
                spec = importlib.util.spec_from_file_location("vce", chemin)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self.citations, n = mod.citations_ecosysteme(self.hs, self.guide)
                print(f"routage : {len(self.citations)} article(s) cités dans {n} fichier(s).")
                return
            except Exception as e:                   # noqa: BLE001
                print(f"routage : index des citations indisponible ({e}).", file=sys.stderr)
        # Repli : les articles VISIBLES relevés à l'ouverture des pages.
        if pages_articles and os.path.isfile(pages_articles):
            try:
                pa = json.load(open(pages_articles, encoding="utf-8")).get("pages", {})
                for page, arts in pa.items():
                    zone = "guide" if page.startswith("guide:") else "app"
                    for a in arts:
                        self.citations.setdefault(a, []).append((zone, page.replace("guide:", "")))
            except Exception:
                pass

    def _charger_hs(self):
        if not self.hs:
            return
        for f in sorted(glob.glob(os.path.join(self.hs, "outils", "module-*.html"))):
            nom = os.path.basename(f)[7:-5]
            try:
                tete = open(f, encoding="utf-8", errors="replace").read(4000)
                m = re.search(r"<title>([^<]+)", tete)
                titre = (m.group(1) if m else nom).replace(" · SimulHeures", "").split(" — ")[0].strip()
            except Exception:
                titre = nom
            self.outils[nom] = titre
        # ccn/conventions-collectives.js : {i:7018, …, n:"Entreprises du paysage", …, g:"DC"}.
        # g = groupe de règles HS ; « DC » = droit commun (pas de règle propre).
        try:
            s = open(os.path.join(self.hs, "ccn", "conventions-collectives.js"), encoding="utf-8", errors="replace").read()
            for m in re.finditer(r"\{i:(\d{1,5}),[^{}]*?n:\"([^\"]*)\"[^{}]*?g:\"([^\"]*)\"", s):
                code = m.group(1)
                if len(code) > 4:
                    continue                          # alias internes (5730, 16110…)
                self.noms_idcc.setdefault(code, m.group(2))
                if m.group(3) != "DC":
                    self.idcc_regles.add(code)
        except Exception:
            pass
        try:
            d = json.load(open(os.path.join(self.hs, "GrillePaye", "ccn-data.json"), encoding="utf-8"))
            for k, v in (d.get("grilles") or {}).items():
                self.idcc_grilles[str(k).lstrip("0")] = (v or {}).get("st", "")
        except Exception:
            pass

    def _charger_guide(self):
        if not self.guide:
            return
        for f in sorted(glob.glob(os.path.join(self.guide, "*.html"))):
            nom = os.path.basename(f)
            if nom.startswith(("apercu", "404")) or nom in ("index.html", "sommaire.html"):
                continue
            self.pages_guide.append(nom)
            try:
                s = open(f, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for n in set(idcc_de(s, strict=True)):
                self.idcc_guide.setdefault(n, []).append(nom)

    def nom_outil(self, court):
        return self.outils.get(court) or court.replace("-", " ").capitalize()

    def guide_par_mots(self, mots):
        if not mots or not self.pages_guide:
            return []
        trouve = [p for p in self.pages_guide if any(m in p for m in mots)]
        return sorted(trouve, key=len)


# ───────────────────────────── constructions de cibles ─────────────────────────────

class Routeur:
    def __init__(self, index):
        self.ix = index
        self._titre = ""

    # Une cible par (zone, cible) ; les fichiers s'additionnent.
    def _ajouter(self, cibles, zone, cible, fichiers=(), action="", raison="", auto=False):
        for c in cibles:
            if c["zone"] == zone and c["cible"] == cible:
                for f in fichiers:
                    if f not in c["fichiers"]:
                        c["fichiers"].append(f)
                if raison and raison not in c["raison"]:
                    c["raison"] = (c["raison"] + " · " + raison).strip(" ·")
                if action and not c["action"]:
                    c["action"] = action
                c["auto"] = c["auto"] and auto
                return
        cibles.append({"zone": zone, "cible": cible, "fichiers": list(dict.fromkeys(fichiers)),
                       "action": action, "raison": raison, "auto": auto})

    def _par_chemin(self, cibles, chemin, action, raison=""):
        """Chemin d'un fichier de l'appli ou du guide -> bonne zone."""
        c = chemin.strip().strip(".,;:)»«\"'")
        if not c:
            return
        if any(c in x["fichiers"] or ("guide:" + x["fichiers"][0] == c if x["zone"] == "guide" and x["fichiers"] else False)
               for x in cibles if x["zone"] != "guide") and not c.startswith("guide:"):
            return
        if c.startswith("guide:"):
            self._ajouter(cibles, "guide", "Pages du guide", [c[6:]], action, raison)
            return
        tete = c.split("/")[0]
        if tete == "outils":
            base = os.path.basename(c)
            if base.startswith("module-") and base.endswith(".html"):
                court = base[7:-5]
                self._ajouter(cibles, "outils", self.ix.nom_outil(court), [c], action, raison)
            else:
                self._ajouter(cibles, "outils", "Fichiers communs des outils (articles-loi.js, page loi, catalogue)", [c], action, raison)
        elif tete == "GrillePaye":
            self._ajouter(cibles, "grilles", "GrillePaye (données et page)", [c], action, raison)
        elif tete in MODULES and "/" in c:
            self._ajouter(cibles, "app", MODULES[tete], [c], action, raison)
        elif c == "taiko.html":
            self._ajouter(cibles, "app", MODULES["taiko"], [c], action, raison)
        elif c in RACINE_COQUILLE:
            self._ajouter(cibles, "app", MODULES["coquille"], [c], action, raison)
        elif c.endswith((".html", ".js", ".json")):
            self._ajouter(cibles, "app", MODULES["commun"], [c], action, raison)

    _CHEMINS = [
        (re.compile(r"\bguide:([\w.-]+\.html)"), lambda m: "guide:" + m.group(1)),
        (re.compile(r"\b(?:app:)?outil:(?:outils/)?([\w.-]+\.(?:html|js))"), lambda m: "outils/" + m.group(1)),
        (re.compile(r"\b(?:app:)?grillepaye:([\w.-]+)"), lambda m: "GrillePaye/" + m.group(1)),
        (re.compile(r"\b(?:app:)?module:([\w-]+)(?![\w/.-])"), lambda m: FICHIER_MODULE.get(m.group(1), m.group(1) + "/index.html")),
        (re.compile(r"\b(?:module|fox|racine):((?:[\w-]+/)*[\w.-]+\.(?:html|js|json))"), lambda m: m.group(1)),
        (re.compile(r"(?<![\w/:-])((?:outils|heures|paye|fox|module\d|GrillePaye|ccn|js|widgets)/[\w./-]+\.(?:html|js|json|png|jpg|webp|svg))"), lambda m: m.group(1)),
        (re.compile(r"(?<![\w/:.-])(menu\.html|sw\.js|manifest\.json|taiko\.html|nouveautes\.html|outils\.html|legi-ref\.js|glossaire\.js|articles-loi\.js|etat-appli\.html)\b"), lambda m: ("outils/" if m.group(1) == "articles-loi.js" else "") + m.group(1)),
    ]

    def chemins_de(self, texte):
        vus = []
        for rx, f in self._CHEMINS:
            for m in rx.finditer(texte or ""):
                c = f(m)
                if c.endswith((".png", ".jpg", ".webp", ".svg")):
                    continue                    # l'image manquante n'est pas le fichier à corriger
                if c not in vus:
                    vus.append(c)
        return vus

    def _articles(self, cibles, arts, action, raison_pref="cite"):
        for art in arts:
            for zone, chemin in self.ix.citations.get(art, []):
                if zone == "guide" and chemin.startswith(("apercu", "404")):
                    continue
                if zone == "guide":
                    self._ajouter(cibles, "guide", "Pages du guide", [chemin], action, f"{raison_pref} {art}")
                else:
                    self._par_chemin(cibles, chemin, action, f"{raison_pref} {art}")

    def _idcc(self, cibles, codes, action_grille, avec_guide=True, avec_regles=True):
        for n in codes[:4]:
            nom = self.ix.noms_idcc.get(n, "")
            if not nom:
                m = re.search(rf"IDCC {n}\s*[—-]\s*([^:\n]+)", self._titre)
                nom = m.group(1).strip() if m else ""
            libelle = f"IDCC {n}" + (f" — {nom[:48]}" if nom else "")
            etat = self.ix.idcc_grilles.get(n)
            raison = f"convention IDCC {n}" + ("" if etat is None or not self.ix.idcc_grilles
                                               else f", grille « {etat} » dans l'appli" if etat
                                               else "") + (", pas encore de grille" if self.ix.idcc_grilles and etat is None else "")
            self._ajouter(cibles, "grilles", libelle, ["GrillePaye/ccn-data.json"], action_grille, raison)
            if avec_regles and n in self.ix.idcc_regles:
                self._ajouter(cibles, "app", MODULES["ccn"], ["ccn/conventions-collectives.js"],
                              f"Vérifier si le texte change les règles HS / temps partiel / forfait de l'IDCC {n}",
                              f"IDCC {n} a des règles dans l'appli")
            if avec_guide:
                pages = self.ix.idcc_guide.get(n, [])
                if pages:
                    self._ajouter(cibles, "guide", "Pages du guide", pages,
                                  f"Relire les montants et règles cités pour l'IDCC {n}", f"parlent de l'IDCC {n}")

    def _outils_designes(self, cibles, detail):
        """« Outil(s) de l'appli à revoir : Préavis, Fin de contrat » : la source
        désigne elle-même les outils. Renvoie True si au moins un est reconnu."""
        m = re.search(r"Outils?(?:\(s\))? de l.appli à revoir\s*:\s*([^\n]+)", detail or "")
        if not m:
            return False
        ok = False
        liste = m.group(1)
        if re.search(r"modules? heures et paye", norm(liste)):
            for mod in ("heures", "paye"):
                self._ajouter(cibles, "app", MODULES[mod], [FICHIER_MODULE[mod]],
                              "Mettre à jour la valeur ou la règle", "désigné par la source")
            ok = True
            liste = re.sub(r"(?i)modules? heures et paye", "", liste)
        for jeton in liste.split(","):
            j = norm(jeton).strip(" .")
            j = ALIAS_OUTILS.get(j, j)
            if not j:
                continue
            if "grillepaye" in j:
                self._ajouter(cibles, "grilles", "Grilles de salaires (toutes conventions)", ["GrillePaye/ccn-data.json"],
                              "Mettre à jour la valeur concernée", "désigné par la source")
                ok = True
                continue
            if re.search(r"modules? heures|heures et paye", j):
                for mod in ("heures", "paye"):
                    self._ajouter(cibles, "app", MODULES[mod], [FICHIER_MODULE[mod]],
                                  "Mettre à jour la valeur ou la règle", "désigné par la source")
                ok = True
                continue
            o = self.ix.outils
            cands = ([c for c, t in o.items() if norm(t) == j] or
                     [c for c in o if c == j or c == j.replace(" ", "-")] or
                     [c for c, t in o.items() if norm(t).startswith(j)] or
                     [c for c, t in o.items() if j in norm(t)] or
                     [c for c, t in o.items() if norm(t).split()[0] == j.split()[0] and len(j.split()[0]) > 3])
            if len(cands) >= 1:
                court = sorted(cands, key=lambda c: len(o[c]))[0]
                self._ajouter(cibles, "outils", o[court], [f"outils/module-{court}.html"],
                              "Mettre à jour la valeur ou la règle", "désigné par la source")
                ok = True
        return ok

    def _themes(self, cibles, texte, action=None, guide=True, info=False, sans_outils=False):
        n = norm(texte)
        trouves = []
        for nom, motif, dests, mots_guide in THEMES:
            if not re.search(motif, n):
                continue
            trouves.append(nom)
            for zone, quoi in dests:
                if zone == "app":
                    self._ajouter(cibles, "app", MODULES[quoi], [FICHIER_MODULE[quoi]],
                                  action or "Vérifier que le calcul et les textes du module suivent la règle", f"thème : {nom}")
                elif zone == "outils":
                    if sans_outils or (self.ix.outils and quoi not in self.ix.outils):
                        continue
                    self._ajouter(cibles, "outils", self.ix.nom_outil(quoi), [f"outils/module-{quoi}.html"],
                                  action or "Vérifier montants, règles et textes de l'outil", f"thème : {nom}")
                elif zone == "grilles":
                    self._ajouter(cibles, "grilles", "Grilles de salaires (toutes conventions)", ["GrillePaye/ccn-data.json"],
                                  action or "Vérifier les grilles concernées", f"thème : {nom}")
            if guide:
                pages = self.ix.guide_par_mots(mots_guide)[:8]
                if pages:
                    self._ajouter(cibles, "guide", "Pages du guide", pages,
                                  action or "Relire les pages de fond sur ce thème", f"thème : {nom}")
        return trouves

    # ─────────────────────────── règles par catégorie ───────────────────────────

    def router(self, a, section_id=""):
        cat = a.get("categorie", "")
        self._titre = a.get("titre", "")
        titre, detail = a.get("titre", ""), a.get("detail", "")
        # « … : parle de : Durée du travail » = étiquette ajoutée par la veille,
        # pas le sujet du texte.
        # (Pour la jurisprudence, au contraire, l'étiquette est le seul indice.)
        if cat in ("nouveau-texte-jorf", "nouvel-avenant-ccn"):
            titre = re.sub(r"\s*:\s*parle de\s*:.*$", "", titre)
        tout = titre + "\n" + detail
        C = []
        add = self._ajouter

        # Santé de la chaîne de veille.
        if cat in ("etape-aspirateur-en-echec", "run-aspirateur-en-echec", "run-en-retard", "fonds-fige",
                   "rattrapage-fonds", "source-injoignable", "audit-introuvable", "audit-illisible",
                   "precache-illisible") or cat.startswith("run-"):
            depot = "Aspirateur (dépôt droit, Actions)" if cat != "source-injoignable" else "Sources officielles (tableaudebord)"
            if cat == "precache-illisible":
                self._par_chemin(C, "sw.js", "Réparer la liste FILES_TO_CACHE")
            else:
                add(C, "veille", depot, [], "Ouvrir le dernier passage dans GitHub Actions et relancer / corriger",
                    "santé de la veille")
                if cat.startswith("audit"):
                    add(C, "mlt", "Audits MonLegiTexte", [], "Vérifier le dossier d'audits du dépôt droit", "audit")
        elif cat == "dares-perime":
            add(C, "veille", "Liste DARES (maj_dares.py, dépôt droit)", ["ccn/Dares_Suivi_Historique_convention_collective_*.xlsx"],
                "Télécharger la dernière liste DARES et la poser dans ccn/ (appli) — maj_dares le tente chaque lundi", "référentiel des conventions")
            add(C, "grilles", "Référentiel des conventions (codes IDCC)", ["GrillePaye/ccn-data.json"],
                "Vérifier les conventions fusionnées ou disparues", "référentiel")

        # MonLegiTexte.
        elif cat.startswith("noindex") or cat in ("site-injoignable", "changement-reel"):
            fichiers = ["_headers"] if cat.startswith("noindex") else []
            act = {"site-injoignable": "Vérifier le Worker Cloudflare de MonLegiTexte",
                   "changement-reel": "Se met à jour seul pour les lecteurs — ouvrir seulement si le sujet te concerne"}.get(
                       cat, "Remettre l'en-tête / la balise noindex")
            add(C, "mlt", "Site MonLegiTexte", fichiers, act, "MonLegiTexte", auto=(cat == "changement-reel"))
            if cat == "changement-reel":
                self._themes(C, titre, guide=False)

        # Grilles de salaires et SMIC.
        elif cat.startswith("grille") or cat in ("lien-mort-grillepaye", "reference-age-resume", "reference-plus-3-mois",
                                                   "reference-plus-12-mois", "identite-divergente", "hors-referentiel-dares"):
            codes = idcc_de(tout)
            act = {
                "grille-sous-smic": "Rien à corriger (le SMIC prime) — à revoir quand la branche renégocie",
                "grille-ancienne": "Chercher un avenant salaires plus récent (KALI, BOCC)",
                "grille-perimee": "Mettre à jour la grille avec le texte plus récent du fonds",
                "grille-a-creer": "Créer la grille à partir du texte du fonds",
                "grille-sur-texte-ancien": "Remplacer la source de la grille par le texte en vigueur",
                "grille-sans-date": "Ajouter la date d'effet et la source",
                "grilles-placeholder": "Sourcer les grilles en attente",
                "lien-mort-grillepaye": "Corriger le lien de la source",
            }.get(cat, "Vérifier la convention dans GrillePaye")
            if codes and cat.startswith(("grille", "reference-plus")) and cat != "grilles-placeholder":
                self._idcc(C, codes, act, avec_guide=cat in ("grille-perimee", "grille-a-creer"), avec_regles=False)
            else:
                add(C, "grilles", "GrillePaye (données et page)", ["GrillePaye/ccn-data.json"], act, "grilles")
            for ch in self.chemins_de(tout):
                self._par_chemin(C, ch, "Aligner ce fichier sur le référentiel")
        elif cat.startswith("smic"):
            add(C, "grilles", "SMIC de GrillePaye", ["GrillePaye/index.html", "GrillePaye/ccn-data.json"],
                "Mettre à jour la valeur du SMIC et sa date", "SMIC")
            for ch in self.chemins_de(tout):
                self._par_chemin(C, ch, "Mettre la même valeur du SMIC partout")
            self._themes(C, "smic salaire minimum cotisations", action="Mettre à jour le SMIC utilisé par l'outil")
            add(C, "app", MODULES["commun"], ["js/hs-officiel.js"], "Mettre à jour les valeurs officielles (SMIC)", "SMIC")
        elif cat == "texte-pour-ccn-en-alerte":
            self._idcc(C, idcc_de(titre) or idcc_de(detail), "Le texte paru peut lever l'alerte : créer / mettre à jour la grille",
                       avec_guide=False)

        # Fichiers, pages, structure : le fichier nommé décide.
        elif (cat.startswith(("page-", "syntaxe", "jsonld", "outil-", "lien-interne")) or
              cat in ("ressource-hors-precache", "asset-casse", "module-absent-de-prod", "livrable-session",
                      "convention-perimee-sans-mention", "fichier-modifie")):
            act = {
                "fichier-modifie": "Simple constat — rien à faire si c'est ton travail",
                "page-image-404": "Remettre l'image ou corriger son chemin",
                "convention-perimee-sans-mention": "Mentionner la fusion / la convention qui reprend",
                "outil-orphelin": "Ajouter l'outil à une catégorie de outils.html",
                "outil-fichier-manquant": "Créer le fichier ou retirer l'entrée de outils.html",
                "module-absent-de-prod": "Pousser la version attendue en production",
                "livrable-session": "Pousser la version attendue en production",
            }.get(cat, "Corriger le fichier")
            chemins = self.chemins_de(titre) or self.chemins_de(detail)
            tete = titre.split(" : ")[0].strip()
            if cat.startswith(("jsonld", "lien-interne", "convention-perimee")) and section_id in ("guide", "structure") \
                    and tete.endswith(".html") and "/" not in tete:
                chemins = ["guide:" + tete]
            if cat.startswith("outil-"):
                cle = titre.split(" : ")[0].strip()
                chemins = [f"outils/{cle if cle.startswith('module-') else 'module-' + cle}.html", "outils.html"]
            if cat in ("module-absent-de-prod", "livrable-session", "asset-casse"):
                nom = titre.split(" : ")[0].strip()
                if nom in MODULES:
                    chemins = [FICHIER_MODULE.get(nom, nom + "/index.html")] + chemins
            if cat == "fichier-modifie":
                for bloc in re.findall(r"(?m)^([A-Z]+) \(\d+\) : (.+)$", detail):
                    z, liste = bloc
                    for n in [x.strip() for x in liste.split(",")]:
                        if z == "GUIDE":
                            self._par_chemin(C, "guide:" + n, act)
                        elif z == "APP":
                            n2 = n.replace("grillepaye:", "GrillePaye/").replace("outil:", "outils/")
                            if n2.startswith("module:"):
                                n2 = FICHIER_MODULE.get(n2[7:], n2[7:] + "/index.html")
                            self._par_chemin(C, n2, act)
                        else:
                            add(C, "mlt", "Site MonLegiTexte", [n], act, "fichier modifié", auto=True)
                for c in C:
                    c["auto"] = True
            if cat in ("page-hors-precache", "ressource-hors-precache"):
                chemins = chemins + ["sw.js"]
            for ch in chemins:
                if cat.startswith(("jsonld", "lien-interne", "convention-perimee")) and not ch.startswith("guide:") \
                        and section_id in ("guide", "structure") and "/" not in ch:
                    ch = "guide:" + ch
                self._par_chemin(C, ch, act)

        # Articles cités.
        elif cat.startswith(("citation", "article-", "contenu-article", "nouvel-article")):
            arts = articles_de(titre) or articles_de(detail)
            act = {
                "article-abroge": "Remplacer l'article abrogé par le nouveau numéro (ou retirer la citation)",
                "article-abroge-ecosysteme": "Remplacer l'article abrogé par le nouveau numéro (ou retirer la citation)",
                "article-introuvable": "Corriger le numéro (faute de frappe ?) ou retirer la citation",
                "contenu-article-modifie": "Relire ce que le fichier dit de l'article : le texte a changé",
                "nouvel-article-section": "Voir si le nouvel article doit être cité ou change une règle",
                "citation-orpheline": "Ajouter l'article à outils/articles-loi.js",
            }.get(cat, "Vérifier le numéro et le code de l'article cité")
            for ch in self.chemins_de(detail):
                self._par_chemin(C, ch, act, "fichier nommé")
            self._articles(C, arts, act)
            if cat == "citation-orpheline":
                self._par_chemin(C, "outils/articles-loi.js", act)
            if cat in ("contenu-article-modifie", "article-abroge", "article-abroge-ecosysteme", "nouvel-article-section"):
                add(C, "mlt", "Fiches articles de MonLegiTexte", [], "Se met à jour seul — vérifier la fiche si besoin",
                    "texte du Code", auto=True)
            if cat == "nouvel-article-section":
                self._themes(C, titre + " " + detail[:600], guide=False)

        # Règles officielles (CDTN, URSSAF, OpenFisca), BOSS, Parlement,
        # circulaires, décisions, nouveaux textes, jurisprudence, accords.
        else:
            # Le détail des nouveaux textes répète l'étiquette de thème de la
            # veille (« Ce texte parle de : Durée du travail ») : seul le
            # titre dit de quoi parle vraiment le texte.
            texte_theme = titre if cat in ("nouveau-texte-jorf", "nouvel-avenant-ccn", "nouvelle-jurisprudence") \
                else titre + " " + detail[:900]
            if cat == "accords-entreprise":
                self._themes(C, titre, action="Pour info : repérer une pratique, rien d'obligatoire", guide=False)
            else:
                codes = idcc_de(titre) or idcc_de(detail[:400])
                nt = norm(titre + " " + str(a.get("theme", "")))
                salaires = bool(re.search(r"salaires?|minima|remuneration|grille|classification|bocc", nt))
                extension = bool(re.search(r"portant extension|portant agrement", norm(titre)))
                temps = bool(re.search(r"heures? sup|heures? complementaires?|temps partiel|forfait|duree du travail|"
                                       r"temps de travail|repos|nuit|dimanche|astreinte|conges? payes?|amenagement", nt))
                if codes:
                    act = ("Reporter les nouveaux montants dans la grille (vérifier dans le texte / le BOCC)"
                           if salaires else "Lire l'avenant : grille, primes ou règles de temps de travail changées ?"
                           if extension else "Mettre à jour la date du dernier texte connu ; grille inchangée sauf primes")
                    # Guide : seulement quand le texte change des montants (les pages
                    # métier citent les minima) ; sinon il noierait la destination.
                    # Règles HS/TP/forfait de l'appli : sujet inconnu (arrêté
                    # d'extension) -> si la convention a des règles propres ; sujet
                    # connu -> seulement s'il touche le temps de travail.
                    self._idcc(C, codes, act, avec_guide=salaires, avec_regles=(extension and not salaires))
                    if temps:
                        for n in codes[:4]:
                            add(C, "app", MODULES["ccn"], ["ccn/conventions-collectives.js"],
                                f"Ajouter ou mettre à jour la règle conventionnelle de l'IDCC {n} (HS, temps partiel, forfait, repos)",
                                f"texte de l'IDCC {n} sur le temps de travail")
                # Un arrêté d'extension cite les articles de la procédure
                # d'extension (L2261-15…) : bruit, on ne s'en sert pas.
                arts = [] if extension else articles_de(titre + " " + detail[:1500])
                if arts:
                    self._articles(C, arts, "Vérifier ce que le fichier dit de cet article à la lumière du nouveau texte",
                                   "cite")
                # Pas d'IDCC : le thème décide (texte général). Avec IDCC, la
                # règle vit dans la convention, pas dans les modules généraux.
                designes = self._outils_designes(C, detail)
                if not codes:
                    self._themes(C, titre if arts else texte_theme, guide=not arts, sans_outils=designes)
                elif not extension and not salaires:
                    # Avenant au sujet connu (prévoyance, indemnité de licenciement…) :
                    # l'outil qui traite ce sujet est à vérifier s'il gère la convention.
                    av = C[:]
                    self._themes(C, re.sub(r"\s*:\s*nouveau texte.*$", "", titre), guide=False,
                                 action=f"Vérifier si l'outil reprend une règle propre à l'IDCC {codes[0]}")
                    C[:] = [c for c in C if c in av or c["zone"] == "outils"]
                if arts and not C:
                    add(C, "mlt", "Articles concernés (non cités dans l'écosystème)", [],
                        "Rien à corriger : " + ", ".join(arts[:6]) + " ne sont cités nulle part dans l'appli ni le guide",
                        "articles", auto=True)
                if cat in ("nouveau-texte-jorf",) and arts:
                    add(C, "mlt", "Fiches articles de MonLegiTexte", [], "Se met à jour seul au prochain passage",
                        "articles du Code modifiés", auto=True)

        # Rien trouvé : on le dit (et on le range dans la veille pour tri).
        if not C:
            add(C, "veille", "À trier", [], "Aucune destination reconnue : lire et décider", "non routé")
        return C


def _resumer(c, max_fichiers=8):
    c["plus"] = max(0, len(c["fichiers"]) - max_fichiers)
    c["fichiers"] = c["fichiers"][:max_fichiers]
    return c


def router_sections(sections, hs=None, guide=None, pages_articles=None):
    """Ajoute cibles/zones à chaque alerte. Renvoie des statistiques."""
    ix = Index(hs, guide, pages_articles)
    r = Routeur(ix)
    stats = {z: 0 for z in ORDRE_ZONES}
    non_routees = 0
    for s in sections:
        for a in s.get("alertes", []):
            try:
                cibles = r.router(a, s.get("id", ""))
            except Exception as e:                   # noqa: BLE001 — jamais bloquant
                print(f"routage : {a.get('titre','')[:60]} : {e}", file=sys.stderr)
                cibles = [{"zone": "veille", "cible": "À trier", "fichiers": [], "action": "Lire et décider",
                           "raison": "erreur de routage", "auto": False}]
            # Ordre : zones dans l'ordre de l'écosystème, « auto » à la fin.
            cibles.sort(key=lambda c: (c["auto"], ORDRE_ZONES.index(c["zone"])))
            a["cibles"] = [_resumer(c) for c in cibles]
            a["zones"] = list(dict.fromkeys(c["zone"] for c in cibles if not c["auto"])) or \
                list(dict.fromkeys(c["zone"] for c in cibles))
            for z in a["zones"]:
                stats[z] += 1
            if a["cibles"] and a["cibles"][0]["cible"] == "À trier":
                non_routees += 1
    return {"par_zone": stats, "non_routees": non_routees, "zones": ZONES, "ordre": ORDRE_ZONES,
            "index": {"articles": len(ix.citations), "pages_guide": len(ix.pages_guide),
                      "outils": len(ix.outils), "idcc_grilles": len(ix.idcc_grilles)}}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Teste le routage sur un donnees.json existant.")
    ap.add_argument("--donnees", default="../donnees.json")
    ap.add_argument("--hs")
    ap.add_argument("--guide")
    ap.add_argument("--sortie", help="écrire le donnees.json routé ici")
    args = ap.parse_args()
    d = json.load(open(args.donnees, encoding="utf-8"))
    st = router_sections(d["sections"], args.hs, args.guide,
                         os.path.join(os.path.dirname(os.path.abspath(args.donnees)), "pages-articles.json"))
    d["routage"] = st
    print(json.dumps(st["par_zone"], ensure_ascii=False), "non routées :", st["non_routees"])
    for s in d["sections"]:
        for a in s.get("alertes", [])[:40]:
            print(f"[{a['categorie']}] {a['titre'][:80]}")
            for c in a["cibles"]:
                print(f"    {'(auto) ' if c['auto'] else ''}{c['zone']:7} {c['cible'][:48]:48} {', '.join(c['fichiers'][:3])}{' +'+str(c['plus']) if c['plus'] else ''}  — {c['action'][:60]}")
    if args.sortie:
        json.dump(d, open(args.sortie, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
