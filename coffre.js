/* 🔐 Coffre du tableau de bord — les secrets ne sont plus jamais gardés en clair dans le navigateur.
 *
 * Pourquoi : toutes tes pages GitHub (anthonychauvel.github.io/droit, /Vol, /51…) partagent le MÊME stockage du
 * navigateur. Une seule faille sur l'une d'elles suffisait à lire la clé d'administration de Vezoria, ta clé GitHub
 * et les codes de carnets gardés ici. Maintenant, ils sont chiffrés (AES-256) avec une phrase de verrouillage que
 * toi seul connais ; elle n'est enregistrée nulle part.
 *
 * Une fois déverrouillé, l'onglet reste ouvert 12 h (ou jusqu'à sa fermeture, ou « 🔒 Verrouiller »).
 * Utilisation dans les pages : Coffre.get(nom), Coffre.set(nom, valeur), Coffre.del(nom), Coffre.verrouiller().
 */
(function () {
  const NOMS = ['vz_admin_key', 'veille_jeton_github', 'vz_admin_known'];   // secrets protégés
  const LSK = 'tdb_coffre', SSK = 'tdb_coffre_ouvert', DUREE = 12 * 3600e3, TOURS = 310000;
  const ls = { get: k => { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} }, del: k => { try { localStorage.removeItem(k); } catch (e) {} } };
  const ss = { get: k => { try { return sessionStorage.getItem(k) || ''; } catch (e) { return ''; } }, set: (k, v) => { try { sessionStorage.setItem(k, v); } catch (e) {} }, del: k => { try { sessionStorage.removeItem(k); } catch (e) {} } };
  const b64 = u => { let s = ''; new Uint8Array(u).forEach(x => { s += String.fromCharCode(x); }); return btoa(s); };
  const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const te = new TextEncoder(), td = new TextDecoder();

  let S = null, KRAW = null, SALT = null;   // secrets en clair et clé, en mémoire de cet onglet seulement
  async function cle(phrase, salt) {
    const base = await crypto.subtle.importKey('raw', te.encode(phrase), 'PBKDF2', false, ['deriveBits']);
    return new Uint8Array(await crypto.subtle.deriveBits({ name: 'PBKDF2', salt, iterations: TOURS, hash: 'SHA-256' }, base, 256));
  }
  const aes = raw => crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
  async function sceller() {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await aes(KRAW), te.encode(JSON.stringify(S)));
    ls.set(LSK, JSON.stringify({ v: 1, s: b64(SALT), i: b64(iv), c: b64(ct) }));
    ss.set(SSK, JSON.stringify({ k: b64(KRAW), s: b64(SALT), d: S, at: Date.now() }));
  }
  async function ouvrir(phrase) {
    const o = JSON.parse(ls.get(LSK)), salt = unb64(o.s), raw = await cle(phrase, salt);
    const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(o.i) }, await aes(raw), unb64(o.c));   // mauvaise phrase → erreur
    S = JSON.parse(td.decode(pt)); KRAW = raw; SALT = salt;
    ss.set(SSK, JSON.stringify({ k: b64(KRAW), s: b64(SALT), d: S, at: Date.now() }));
  }
  async function creer(phrase, depart) {
    SALT = crypto.getRandomValues(new Uint8Array(16)); KRAW = await cle(phrase, SALT); S = depart || {};
    await sceller();
    NOMS.forEach(ls.del);   // les anciennes copies en clair disparaissent
  }
  // onglet déjà déverrouillé (moins de 12 h) : tout est disponible tout de suite, sans rien demander
  try {
    const o = JSON.parse(ss.get(SSK) || 'null');
    if (o && ls.get(LSK) && Date.now() - o.at < DUREE) { S = o.d || {}; KRAW = unb64(o.k); SALT = unb64(o.s); } else ss.del(SSK);
  } catch (e) { ss.del(SSK); }
  const enClair = () => { const o = {}; NOMS.forEach(n => { const v = ls.get(n); if (v) o[n] = v; }); return o; };
  const aProteger = () => !ls.get(LSK) && Object.keys(enClair()).length > 0;   // anciennes clés en clair à mettre au coffre

  // ── fenêtre de déverrouillage / création ──
  const phraseOk = p => p.length >= 8 && !(/^\d+$/.test(p) && p.length < 12);
  let attente = null;
  function fenetre(mode) {
    if (document.getElementById('cf-fond')) return;
    const f = document.createElement('div'); f.id = 'cf-fond';
    f.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(5,8,14,.86);display:flex;align-items:center;justify-content:center;padding:16px;font:15px -apple-system,system-ui,sans-serif';
    const neuf = mode !== 'ouvrir';
    f.innerHTML = `<div style="background:#141a24;color:#e8edf3;border:1px solid #2a3443;border-radius:16px;max-width:380px;width:100%;padding:18px">
      <div style="font-size:17px;font-weight:750;margin-bottom:6px">🔐 ${neuf ? 'Protéger tes clés' : 'Tableau de bord verrouillé'}</div>
      <div style="font-size:13px;line-height:1.5;color:#a9b4c2;margin-bottom:12px">${neuf
        ? 'Tes clés (administration Vezoria, GitHub, codes de carnets) vont être chiffrées. Choisis une phrase de verrouillage : <b>au moins 8 caractères</b>, pas seulement des chiffres. Elle n’est enregistrée nulle part : note-la.'
        : 'Tape ta phrase de verrouillage pour ouvrir tes clés (valable 12 h dans cet onglet).'}</div>
      <input id="cf-p1" type="password" autocomplete="off" placeholder="Phrase de verrouillage" style="width:100%;box-sizing:border-box;padding:12px;border-radius:12px;border:1px solid #2a3443;background:#0d121a;color:#e8edf3;font-size:16px">
      ${neuf ? '<input id="cf-p2" type="password" autocomplete="off" placeholder="La même, encore une fois" style="width:100%;box-sizing:border-box;padding:12px;border-radius:12px;border:1px solid #2a3443;background:#0d121a;color:#e8edf3;font-size:16px;margin-top:8px">' : ''}
      <div id="cf-err" style="color:#ff8a8a;font-size:13px;min-height:18px;margin-top:8px"></div>
      <button id="cf-go" style="width:100%;padding:12px;border:0;border-radius:12px;background:#7c5cff;color:#fff;font-weight:700;font-size:15px">${neuf ? '🔐 Chiffrer mes clés' : '🔓 Déverrouiller'}</button>
      ${neuf ? (mode === 'creer' ? '<button id="cf-non" style="width:100%;margin-top:8px;padding:10px;border:0;border-radius:12px;background:none;color:#a9b4c2;font-size:13px">Annuler</button>' : '')
        : '<button id="cf-oubli" style="width:100%;margin-top:8px;padding:10px;border:0;border-radius:12px;background:none;color:#a9b4c2;font-size:13px">Phrase oubliée : effacer le coffre (tu retaperas tes clés)</button>'}
    </div>`;
    document.body.appendChild(f);
    const p1 = f.querySelector('#cf-p1'), p2 = f.querySelector('#cf-p2'), err = f.querySelector('#cf-err'), go = f.querySelector('#cf-go');
    setTimeout(() => p1.focus(), 50);
    const valider = async () => {
      const p = p1.value; err.textContent = '';
      if (neuf) {
        if (!phraseOk(p)) { err.textContent = 'Au moins 8 caractères (12 si ce ne sont que des chiffres).'; return; }
        if (p !== p2.value) { err.textContent = 'Les deux phrases ne sont pas identiques.'; return; }
      }
      go.disabled = true; go.textContent = '…';
      try {
        if (neuf) await creer(p, mode === 'migrer' ? enClair() : Object.assign({}, S || {}, attente ? attente.v : {}));
        else await ouvrir(p);
        location.reload();
      } catch (e) { go.disabled = false; go.textContent = neuf ? '🔐 Chiffrer mes clés' : '🔓 Déverrouiller'; err.textContent = neuf ? 'Impossible de chiffrer : ' + e.message : 'Phrase incorrecte.'; p1.value = ''; p1.focus(); }
    };
    go.onclick = valider; [p1, p2].forEach(x => x && x.addEventListener('keydown', e => { if (e.key === 'Enter') valider(); }));
    const non = f.querySelector('#cf-non'); if (non) non.onclick = () => { attente = null; f.remove(); };
    const oubli = f.querySelector('#cf-oubli');
    if (oubli) oubli.onclick = () => { if (!confirm('Effacer le coffre ? Tu devras retaper ta clé d’administration et ta clé GitHub.')) return; ls.del(LSK); ss.del(SSK); location.reload(); };
  }
  function bouton() {   // petit cadenas pour verrouiller l'onglet
    if (document.getElementById('cf-lock') || !S) return;
    const b = document.createElement('button'); b.id = 'cf-lock'; b.type = 'button'; b.textContent = '🔒'; b.title = 'Verrouiller le tableau de bord';
    b.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:9999;width:42px;height:42px;border-radius:50%;border:1px solid #2a3443;background:#141a24;color:#fff;font-size:18px';
    b.onclick = () => window.Coffre.verrouiller(); document.body.appendChild(b);
  }
  function auDemarrage() {
    if (aProteger()) fenetre('migrer');            // anciennes clés en clair : on les met au coffre tout de suite
    else if (ls.get(LSK) && !S) fenetre('ouvrir'); // coffre fermé
    bouton();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', auDemarrage); else auDemarrage();

  window.Coffre = {
    ouvert: () => !!S,
    // tant que le coffre n'est pas en place, les anciennes valeurs en clair restent lisibles (la fenêtre propose de les protéger)
    get: n => S ? (S[n] || '') : (!ls.get(LSK) ? ls.get(n) : ''),
    set: (n, v) => {
      v = String(v || '');
      if (S) { if (v) S[n] = v; else delete S[n]; sceller().catch(() => {}); return true; }
      if (ls.get(LSK)) { fenetre('ouvrir'); return false; }   // coffre fermé : il faut d'abord le déverrouiller
      if (aProteger()) { if (v) ls.set(n, v); else ls.del(n); return true; }   // la fenêtre « Protéger tes clés » est ouverte : elle l'emportera au coffre
      attente = { v: { [n]: v } }; fenetre('creer'); return false;   // premier secret : on crée le coffre
    },
    del: n => { if (S) { delete S[n]; sceller().catch(() => {}); } ls.del(n); },
    verrouiller: () => { ss.del(SSK); S = null; KRAW = null; location.reload(); },
  };
})();
