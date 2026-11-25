/**
 * FAM-DOC-1 · Enlaces de las familias servidos bajo el dominio de Vercel.
 *
 * El frontend de producción está en Vercel y el backend en Render. La página del
 * documento (/doc/<enlace>) y su PDF los sirve el BACKEND, así que Vercel debe
 * reenviar esas dos rutas al backend ANTES de su regla «todo → index.html».
 * Vercel aplica la primera regla que coincide (docs: Rewrites, «Vercel applies the
 * first rewrite that matches a request, so list specific paths before the
 * catch-all») y admite destinos externos como proxy.
 *
 *   1. Siempre: lee frontend/vercel.json y comprueba, con un intérprete mínimo de
 *      la sintaxis de Vercel (`:param` = un segmento, `(.*)` = cualquier cosa), qué
 *      regla atiende cada ruta: /doc/<enlace> y /doc/<enlace>/pdf → backend https;
 *      el resto de la app (incluidas /docentes, /doc, /documentos…) → index.html.
 *   2. Opcional, con un backend LOCAL de prueba en marcha:
 *        EO_PRUEBA_BACKEND_LOCAL=http://127.0.0.1:8751 EO_PRUEBA_ENLACE=<enlace sintético>
 *      levanta un servidor local que aplica ESTAS reglas (cambiando solo el host
 *      del backend por el local) y pide la página, el PDF y la descarga a través
 *      de él. No reproduce la plataforma de Vercel: comprueba las reglas y que la
 *      respuesta del backend (tipo, Content-Disposition, cabeceras privadas) pasa.
 *
 *   cd frontend && node scripts/vercel-enlaces-familia.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import http from 'node:http';

const aqui = dirname(fileURLToPath(import.meta.url));
const BACKEND = 'https://educaone-api.onrender.com';   // servicio educaone-api de Render (producción)
const config = JSON.parse(readFileSync(join(aqui, '..', 'vercel.json'), 'utf8'));
const reglas = config.rewrites || [];

let ok = 0; const fallos = [];
const prueba = async (nombre, fn) => {
  try { await fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };
const si = (c, msg) => { if (!c) throw new Error(msg || 'falso'); };

// Intérprete mínimo de la sintaxis usada en este vercel.json (subconjunto de path-to-regexp).
const compilar = (source) => {
  const nombres = [];
  const COMODIN = '\u0000';
  const re = source.split('(.*)').join(COMODIN)
    .replace(/[.+?^${}|[\]\\()*]/g, (c) => '\\' + c)
    .replace(/:([A-Za-z_]\w*)/g, (_, n) => { nombres.push(n); return '([^/]+?)'; })
    .split(COMODIN).join('(.*)');
  return { re: new RegExp('^' + re + '/?$'), nombres };
};
const resolver = (ruta) => {
  for (const r of reglas) {
    const { re, nombres } = compilar(r.source);
    const m = ruta.match(re);
    if (m) {
      let destino = r.destination;
      nombres.forEach((n, i) => { destino = destino.replace(':' + n, m[i + 1]); });
      return destino;
    }
  }
  return null;
};

const T = 'Ab_cd-EF01234567890123456789012345678901234';  // forma de un enlace (43 caracteres, sintético)

console.log('\n1. Reglas de vercel.json');
await prueba('la regla «todo → index.html» sigue y es la ÚLTIMA', () => {
  igual(reglas[reglas.length - 1], { source: '/(.*)', destination: '/index.html' });
});
await prueba('las reglas de /doc van ANTES de la regla general', () => {
  const i = reglas.findIndex(r => r.source.startsWith('/doc/'));
  si(i >= 0 && i < reglas.length - 1, 'faltan o están después del catch-all');
});
await prueba('/doc/<enlace> → página del backend', () => igual(resolver(`/doc/${T}`), `${BACKEND}/doc/${T}`));
await prueba('/doc/<enlace>/pdf → PDF del backend', () => igual(resolver(`/doc/${T}/pdf`), `${BACKEND}/doc/${T}/pdf`));
await prueba('con barra final también', () => igual(resolver(`/doc/${T}/`), `${BACKEND}/doc/${T}`));
for (const r of ['/', '/login', '/calificaciones-general', '/docentes', '/documentos', '/doc', `/doc/${T}/pdf/otra`, '/estudiantes']) {
  await prueba(`${r} → app (index.html)`, () => igual(resolver(r), '/index.html'));
}
await prueba('los destinos externos son https y solo al backend', () => {
  reglas.filter(r => /^https?:/.test(r.destination)).forEach(r => {
    const u = new URL(r.destination.replace(/:\w+/g, 'x'));
    igual(u.origin, BACKEND, r.source);
    igual(u.protocol, 'https:');
  });
});
await prueba('solo /doc se reenvía al backend (la API sigue con VITE_API_URL)', () => {
  igual(reglas.filter(r => /^https?:/.test(r.destination)).map(r => r.source), ['/doc/:token/pdf', '/doc/:token']);
});

const LOCAL = process.env.EO_PRUEBA_BACKEND_LOCAL;
const ENLACE = process.env.EO_PRUEBA_ENLACE;
if (LOCAL && ENLACE) {
  console.log('\n2. A través de las reglas, contra el backend LOCAL de prueba');
  const lb = new URL(LOCAL);
  if (!['127.0.0.1', 'localhost'].includes(lb.hostname)) throw new Error('Solo se admite un backend local de prueba.');
  const INDEX = '<!doctype html><title>SPA</title><div id="root"></div>';
  const srv = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const destino = resolver(u.pathname);
    if (destino === '/index.html' || !destino) { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(INDEX); }
    const d = new URL(destino.replace(BACKEND, LOCAL));
    d.search = u.search;  // se asume que la query string se conserva (ver informe)
    http.get(d, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); }).on('error', () => { res.writeHead(502); res.end(); });
  });
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  const pedir = async (ruta) => { const r = await fetch(base + ruta); return { r, cuerpo: Buffer.from(await r.arrayBuffer()) }; };
  try {
    const pag = await pedir(`/doc/${ENLACE}`);
    await prueba('página del documento (200, HTML del backend con «Descargar PDF»)', () => {
      igual(pag.r.status, 200); si(pag.cuerpo.toString().includes('Descargar PDF'), 'no es la página del documento');
    });
    await prueba('cabeceras privadas pasan (no-store, noindex)', () => {
      si((pag.r.headers.get('cache-control') || '').includes('no-store')); si((pag.r.headers.get('x-robots-tag') || '').includes('noindex'));
    });
    const pdf = await pedir(`/doc/${ENLACE}/pdf`);
    await prueba('PDF en línea (application/pdf, inline)', () => {
      igual(pdf.r.status, 200); igual(pdf.r.headers.get('content-type'), 'application/pdf');
      si((pdf.r.headers.get('content-disposition') || '').startsWith('inline')); igual(pdf.cuerpo.subarray(0, 4).toString(), '%PDF');
    });
    const des = await pedir(`/doc/${ENLACE}/pdf?descargar=1`);
    await prueba('«Descargar PDF» (attachment, mismo PDF)', () => {
      si((des.r.headers.get('content-disposition') || '').startsWith('attachment')); si(des.cuerpo.equals(pdf.cuerpo), 'distinto PDF');
    });
    const mal = await pedir('/doc/' + 'A'.repeat(43));
    await prueba('enlace inexistente → 404 genérico del backend', () => { igual(mal.r.status, 404); si(!mal.cuerpo.toString().includes('SPA')); });
    const app = await pedir('/calificaciones-general');
    await prueba('el resto sigue siendo la app', () => si(app.cuerpo.toString().includes('SPA')));
  } finally { srv.close(); }
} else {
  console.log('\n2. (omitida: sin EO_PRUEBA_BACKEND_LOCAL y EO_PRUEBA_ENLACE)');
}

console.log(`\n${ok}/${ok + fallos.length}`);
process.exit(fallos.length ? 1 : 0);
