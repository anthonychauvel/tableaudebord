// RELAIS BOSS — Worker Cloudflare (02/10/2026)
// boss.gouv.fr ne répond pas aux machines de GitHub (test du 02/10/2026 :
// délai dépassé). Ce Worker va chercher la page à leur place.
// SÉCURITÉ : il ne relaie QUE boss.gouv.fr (sinon n'importe qui pourrait
// s'en servir comme proxy ouvert).
//
// Mise en place (depuis l'iPhone, tableau de bord Cloudflare) :
//   1. Workers & Pages → Créer → Worker → nom « relais-boss » → Déployer
//   2. Modifier le code → coller ce fichier → Déployer
//   3. Copier l'adresse (https://relais-boss.<toi>.workers.dev)
//   4. GitHub → tableaudebord → Settings → Secrets and variables → Actions
//      → onglet Variables → New variable :
//      nom  VEILLE_RELAIS
//      valeur  https://relais-boss.<toi>.workers.dev/?url=
export default {
  async fetch(req) {
    const cible = new URL(req.url).searchParams.get("url") || "";
    let u;
    try { u = new URL(cible); } catch { return new Response("url ?", { status: 400 }); }
    if (u.protocol !== "https:" || !/^(www\.)?boss\.gouv\.fr$/.test(u.hostname)) {
      return new Response("refusé : seul boss.gouv.fr est relayé", { status: 403 });
    }
    const r = await fetch(u.toString(), {
      headers: { "User-Agent": "Mozilla/5.0 (veille SimulHeures)", "Accept-Language": "fr-FR,fr;q=0.9" },
      cf: { cacheTtl: 3600 },
    });
    return new Response(r.body, { status: r.status, headers: { "Content-Type": r.headers.get("Content-Type") || "text/html" } });
  },
};
