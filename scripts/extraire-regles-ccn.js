#!/usr/bin/env node
/**
 * EXTRAIRE-REGLES-CCN.JS — majoration heures sup, contingent et source, pour
 * chaque convention connue de l'app.
 *
 * Différent de tout le reste de veille-perso : ce n'est pas une alerte, c'est
 * une consultation. Pas de "c'est périmé" ou "c'est faux" -- juste "voici ce
 * que dit l'app aujourd'hui pour cette CCN", pour éviter d'aller rouvrir
 * conventions-collectives.js à la main à chaque fois qu'on veut vérifier un
 * taux ou un contingent.
 *
 * Charge le VRAI fichier de l'app via require() plutôt que de le reparser à
 * la main -- si la logique de résolution (getGroupeForCCN) change un jour,
 * cet extrait suit automatiquement, sans jamais pouvoir diverger du vrai
 * comportement de l'app.
 *
 * USAGE
 *   node extraire-regles-ccn.js --hs /chemin/vers/hs --out sortie.json
 */
const fs = require("fs");
const path = require("path");

function args() {
  const a = process.argv.slice(2);
  const o = {};
  for (let i = 0; i < a.length; i++) {
    if (a[i] === "--hs") o.hs = a[++i];
    if (a[i] === "--out") o.out = a[++i];
  }
  return o;
}

function main() {
  const { hs, out } = args();
  if (!hs || !out) {
    console.error("usage: node extraire-regles-ccn.js --hs <racine_app> --out <sortie.json>");
    process.exit(1);
  }

  const chemin = path.join(hs, "ccn", "conventions-collectives.js");
  const api = require(path.resolve(chemin));

  const entrees = api.CCN_ALIASES.map((c) => {
    const r = api.getGroupeForCCN(c.i);
    return {
      idcc: c.i,
      brochure: c.b || null,
      nom: c.n,
      secteur: c.s,
      groupe: r.id,
      groupeNom: r.nom,
      seuil: r.seuil,
      taux1: r.taux1,
      palier1: r.palier1,
      taux_inter: r.taux_inter,
      palier_inter: r.palier_inter,
      taux2: r.taux2,
      contingent: r.contingent,
      maxHebdo: r.maxHebdo,
      notes: r.notes,
    };
  });

  // Un IDCC peut apparaître plusieurs fois dans CCN_ALIASES (alias internes,
  // ex. 5730/16110 -- voir les commentaires du fichier source) -- on ne garde
  // que la première résolution par IDCC pour la consultation, l'app gère les
  // alias elle-même en interne, ce n'est pas ce qu'on veut exposer ici.
  const vus = new Set();
  const dedupliquees = entrees.filter((e) => {
    if (vus.has(e.idcc)) return false;
    vus.add(e.idcc);
    return true;
  });

  dedupliquees.sort((a, b) => a.idcc - b.idcc);

  const sortie = {
    genere: new Date().toISOString(),
    versionSource: api.version,
    nombreGroupes: Object.keys(api.REGLES_HS).length,
    entrees: dedupliquees,
  };

  fs.writeFileSync(out, JSON.stringify(sortie, null, 2), "utf-8");
  console.log(
    `${dedupliquees.length} CCN extraites (source v${api.version}, ` +
      `${entrees.length - dedupliquees.length} alias interne(s) fusionné(s)), écrit dans ${out}`
  );
}

main();
