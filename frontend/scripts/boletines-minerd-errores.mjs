/**
 * BOLETINES MINERD — alcance y conservación del comportamiento.
 *
 * Sin framework, como los demás scripts. Compara el código de la rama con el de
 * `main` (vía git) para comprobar que:
 *   · las URLs, los nombres de descarga y los roles de las rutas no cambian;
 *   · en BoletinesPage, de las 6 descargas que comparten `descargarPDF`, solo las
 *     2 MINERD v2 activan mensajeDeError; las de Primaria y padres siguen igual;
 *   · las 3 pantallas usan mensajeDeError solo en las descargas MINERD;
 *   · el camino de éxito (crear Blob y descargar) es idéntico al de main.
 * El comportamiento ante cada error se probó en la app real (ver el informe).
 *
 *   cd frontend && node scripts/boletines-minerd-errores.mjs
 */
import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const rama = (rel) => readFileSync(join(aqui, '..', 'src', rel), 'utf8').split(CR).join('');
const main = (rel) => execSync(`git show origin/main:frontend/src/${rel}`, { cwd: join(aqui, '..'), encoding: 'utf8' }).split(CR).join('');

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };

const ARCHIVOS = {
  tab: 'pages/academico/secundaria/TabBoletin.tsx',
  ficha: 'pages/academico/FichaEstudianteAsignatura.tsx',
  bol: 'pages/boletines/BoletinesPage.tsx',
};
const urls = (s) => [...s.matchAll(/`(\/boletines[^`]*)`/g)].map((m) => m[1]).sort();
const descargas = (s) => [...s.matchAll(/(?:download = |setAttribute\('download', )([^;)]*)/g)].map((m) => m[1].trim()).sort();
const nombres = (s) => [...s.matchAll(/`((?:Boletin|Boletines)[^`]*\.pdf)`/g)].map((m) => m[1]).sort();

console.log('\nURLs, nombres de descarga y camino de éxito iguales a main');
for (const [k, rel] of Object.entries(ARCHIVOS)) {
  const R = rama(rel), M = main(rel);
  prueba(`${k}: mismas URLs de boletines`, () => igual(urls(R), urls(M)));
  prueba(`${k}: mismos nombres de archivo`, () => igual(nombres(R), nombres(M)));
  prueba(`${k}: misma forma de descargar`, () => igual(descargas(R), descargas(M)));
  prueba(`${k}: misma comprobación de 200-que-no-es-PDF`, () => igual(
    (R.match(/res(?:ponse)?\.data\.type === 'application\/json' \|\| res(?:ponse)?\.data\.size < \d+/g) || []),
    (M.match(/res(?:ponse)?\.data\.type === 'application\/json' \|\| res(?:ponse)?\.data\.size < \d+/g) || [])));
}

console.log('\nAlcance');
const BOL = rama(ARCHIVOS.bol);
prueba('BoletinesPage: 6 llamadas a descargarPDF, solo las 2 MINERD v2 pasan `true`', () => {
  // Cada llamada termina en el `)}` que va solo en su línea (el nombre de archivo tiene otro `)}` dentro).
  const llamadas = [...BOL.matchAll(/descargarPDF\(\s*`([^`]+)`,[\s\S]*?\n\s*\)\}/g)].map((m) => ({ url: m[1], activa: /,\s*true,?\s*\)\}$/.test(m[0]) }));
  igual(llamadas.length, 6, 'número de descargas');
  igual(llamadas.filter((l) => l.activa).map((l) => l.url).sort(),
    ['/boletines/curso/${cursoId}/pdf-minerd-v2', '/boletines/estudiante/${estudianteId}/pdf-minerd-v2']);
});
prueba('BoletinesPage: las otras 4 conservan el camino anterior (`err?.response?.data?.error || msgError`)', () => {
  if (!BOL.includes(': (err?.response?.data?.error || msgError));')) throw new Error('falta la rama anterior');
});
prueba('TabBoletin: ya no existe extraerErrorDeBlob y se usa mensajeDeError en las 2 descargas', () => {
  const T = rama(ARCHIVOS.tab);
  if (T.includes('extraerErrorDeBlob')) throw new Error('quedó extraerErrorDeBlob');
  igual((T.match(/mensajeErrorBoletin\(err,/g) || []).length, 2);
});
prueba('Ficha: mensajeDeError solo en descargarBoletin; los demás catch no cambian', () => {
  const F = rama(ARCHIVOS.ficha), M = main(ARCHIVOS.ficha);
  igual((F.match(/await mensajeDeError\(/g) || []).length, 1);
  const otros = (s) => (s.match(/err\.response\?\.data\?\.error \|\| '[^']+'/g) || []).sort();
  igual(otros(F), otros(M), 'catch de carga y guardado');
});
prueba('rutas y roles de las pantallas sin cambios (Router.tsx no se toca)', () => igual(rama('Router.tsx'), main('Router.tsx')));

console.log(`\n${ok} pasan, ${fallos.length} fallan`);
process.exit(fallos.length ? 1 : 0);
