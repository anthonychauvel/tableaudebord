    # Syntaxe JS : la seule vérification qui détecte "cette page ne charge plus
    # DU TOUT", pas seulement "cette donnée est périmée". Couvre la racine, les
    # 8 modules, GrillePaye et les 105 outils.
    sections.append({"id": "syntaxe", "titre": "Syntaxe JS (page entière cassée)",
        **lancer("verifier-syntaxe-js.py", ["--hs", args.hs])})

    # Pages ouvertes pour de vrai (P6) : la syntaxe peut être juste et la page
    # planter quand même au chargement (variable inconnue, fichier absent).
    # Contrôle aussi le précache de sw.js (pages et fichiers qu'elles chargent).
    # Le guide est ouvert lui aussi (22/09/2026) : ses ~981 pages n'étaient
    # jusque-là jamais exécutées, seulement lues. 4 pages en parallèle : appli
    # + guide en 8 à 10 minutes. Besoin de Playwright + Chromium (regenerer.yml).
    # --articles : les articles de loi VISIBLES après exécution du JavaScript,
    # gardés à côté pour le croisement avec le fonds.
    pages_args = ["--hs", args.hs, "--parallele", "4",
                  "--articles", os.path.join(os.path.dirname(args.out), "pages-articles.json")]
    if args.guide:
        pages_args += ["--guide", args.guide]
    sections.append({"id": "pages", "titre": "Pages qui ne se chargent plus (ouverture réelle)",
        **lancer("verifier-pages.py", pages_args)})

    # Croisement : citations juridiques du guide + des 8 modules contre le fonds.
    # Distinct de la vérification des outils (verifier-outils.py, incluse dans
    # la section "outils" ci-dessus) : celle-ci connaît le code (travail/sécu) de
    # chaque article grâce à articles-loi.js, alors que le guide et les modules
    # citent en texte brut, sans cette information.
    #
    # S'y ajoute (22/09/2026) le croisement de ce qui est VISIBLE à l'écran :
    # verifier-pages.py a relevé les articles lisibles après exécution du
    # JavaScript (pages-articles.json), croiser-pages-fonds.py les confronte au
    # fonds et ne garde que ceux qu'aucune lecture du code source ne voyait.
    # D'où l'ordre : la section « pages » est construite AVANT celle-ci.
    citations_args = ["--hs", args.hs, "--fonds", args.droit]
    croisement_args = ["--hs", args.hs, "--fonds", args.droit,
                       "--articles", os.path.join(os.path.dirname(args.out), "pages-articles.json")]
    if args.guide:
        citations_args += ["--guide", args.guide]
        croisement_args += ["--guide", args.guide]
    sections.append({"id": "citations", "titre": "Citations juridiques (guide + modules)",
        **fusionner(
            lancer("verifier-citations-ecosysteme.py", citations_args),
            lancer("croiser-pages-fonds.py", croisement_args),
        )})
