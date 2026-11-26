/**
 * DESCARGAS PDF/CSV — mensajes de error en Notas por período, Cuadro de honor,
 * Informes de Aprendizaje (Primaria) y CSV de SuperAdmin.
 *
 * Sin framework, como los demás scripts:
 *   1. Transpila `utils/errorServidor.ts` y prueba `mensajeDeErrorDescarga` con
 *      errores con la forma de axios y con el Error propio de las descargas.
 *   2. Compara el código con `origin/main` (vía git): URLs, nombres de archivo,
 *      forma de descargar y rutas no cambian; solo cambian los `catch` de las
 *      descargas indicadas.
 *
 *   cd frontend && node scripts/descargas-pdf-errores.mjs
 */
import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const rama = (rel) => readFileSync(join(aqui, '..', 'src', rel), 'utf8').split(CR).join('');
const main = (rel) => execSync(`git show origin/main:frontend/src/${rel}`, { cwd: join(aqui, '..'), encoding: 'utf8' }).split(CR).join('');

const js = transformSync(rama('utils/errorServidor.ts'), { loader: 'ts', format: 'esm' }).code;
const { mensajeDeErrorDescarga } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = async (nombre, fn) => {
  try { await fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };
const contiene = (t, s) => { if (!String(t).includes(s)) throw new Error(`no contiene ${JSON.stringify(s)} en ${JSON.stringify(t)}`); };
const noContiene = (t, s) => { if (String(t).includes(s)) throw new Error(`NO debía contener ${JSON.stringify(s)} en ${JSON.stringify(t)}`); };

// Error con la forma de axios (isAxiosError, response con Blob, o sin response)
const axiosErr = (status, cuerpo) => ({
  isAxiosError: true, message: `Request failed with status code ${status}`, request: {},
  response: { status, data: new Blob([typeof cuerpo === 'string' ? cuerpo : JSON.stringify(cuerpo)]) },
});
const OP = { porDefecto: 'Error al descargar PDF' };
const MSG_500 = 'El servidor tuvo un problema al procesar la solicitud (error 500). Inténtelo de nuevo; si se repite, avise a soporte técnico.';

console.log('\nmensajeDeErrorDescarga');
await prueba('400 con `error` en Blob: el texto del servidor, no «Request failed…»', async () => {
  const m = await mensajeDeErrorDescarga(axiosErr(400, { error: 'Curso requerido' }), OP);
  igual(m, 'Curso requerido'); noContiene(m, 'Request failed');
});
await prueba('403 de RolesRequired (`detail`)', async () => {
  igual(await mensajeDeErrorDescarga(axiosErr(403, { detail: 'No tiene permisos para esta acción' }), OP), 'No tiene permisos para esta acción');
});
await prueba('404 «No hay año escolar configurado»', async () => {
  igual(await mensajeDeErrorDescarga(axiosErr(404, { error: 'No hay año escolar configurado' }), OP), 'No hay año escolar configurado');
});
await prueba('422 con `detail` en lista: mensaje por defecto, nunca un objeto', async () => {
  igual(await mensajeDeErrorDescarga(axiosErr(422, { detail: [{ type: 'missing', loc: ['query', 'periodo'], msg: 'Field required' }] }), OP), OP.porDefecto);
});
await prueba('500 con texto técnico ficticio: mensaje controlado', async () => {
  const m = await mensajeDeErrorDescarga(axiosErr(500, { error: "Error generando PDF. Detalle técnico: KeyError: 'periodo_ficticio' en /srv/educaone/app.py" }), OP);
  igual(m, MSG_500); noContiene(m, 'KeyError'); noContiene(m, '/srv');
});
await prueba('corte de conexión (axios sin response): conexión, no «Network Error»', async () => {
  const m = await mensajeDeErrorDescarga({ isAxiosError: true, code: 'ERR_NETWORK', message: 'Network Error', request: {} }, OP);
  igual(m, 'No se pudo conectar con el servidor. Compruebe su conexión a internet e inténtelo de nuevo.');
});
await prueba('Error propio ante un 200 que no es PDF: conserva su texto, como antes', async () => {
  igual(await mensajeDeErrorDescarga(new Error('El servidor no devolvio un PDF'), OP), 'El servidor no devolvio un PDF');
});
await prueba('error sin mensaje o desconocido: mensaje por defecto, sin lanzar', async () => {
  igual(await mensajeDeErrorDescarga(new Error(''), OP), OP.porDefecto);
  igual(await mensajeDeErrorDescarga(undefined, OP), OP.porDefecto);
  igual(await mensajeDeErrorDescarga({ isAxiosError: 'sí' }, OP), OP.porDefecto);
});

console.log('\nAlcance frente a main');
const ARCH = {
  notas: 'pages/calificaciones-general/CalificacionesGeneralPage.tsx',
  honor: 'pages/cuadro-honor/CuadroHonorPage.tsx',
  prim: 'pages/academico/AcademicoPrimariaPage.tsx',
  sa: 'pages/superadmin/SuperAdminPage.tsx',
};
const urls = (s) => [...s.matchAll(/(?:api\.get|fetch)\(\s*`([^`]+)`/g)].map((m) => m[1]).concat([...s.matchAll(/api\.get\('([^']+)'/g)].map((m) => m[1])).sort();
const archivos = (s) => [...s.matchAll(/`([^`]*\.(?:pdf|csv))`|'([^']*\.(?:pdf|csv))'/g)].map((m) => m[1] || m[2]).sort();
const descarga = (s) => [...s.matchAll(/(?:setAttribute\('download', [^)]*\)|\.download\s*=\s*[^;]+;|createObjectURL\([^;]+;)/g)].map((m) => m[0]).sort();
// Quita las líneas que esta entrega cambia a propósito para comparar el resto con main.
const sinCambiosPrevistos = (s) => s.split('\n')
  .filter((l) => !/mensajeDeError|data-error-descarga|setError\(e\.message|setError\(e\?\.message|setMensaje\(e\?\.response|setError\('Error exportando'\)/.test(l))
  // el aviso de error (se envuelve en un span con whitespace-pre-line)
  .filter((l) => !/^\s*\{(error|mensaje) && <Alert variant="error" onClose=/.test(l))
  .join('\n');

// Las comprobaciones de IDENTIDAD con main (mismas URLs, archivo idéntico) miden
// el alcance de ESTA entrega (#77, base 0504032). Una rama posterior que cambia
// a propósito una de estas pantallas (p. ej. FAM-DOC-1 en Notas por período)
// las omite SOLO para los archivos que ella misma cambia; las demás pruebas
// (nombres de archivo, forma de descargar, extractor de errores) se aplican siempre.
const git = (cmd) => execSync(`git ${cmd}`, { cwd: join(aqui, '..'), encoding: 'utf8' }).split(CR).join('');
const BASE_ENTREGA_77 = '050403277bef16e1a980a6aad08b9ba7939f9586';
const BASE_RAMA = git('merge-base HEAD origin/main').trim();
const CAMBIADOS_EN_RAMA = BASE_RAMA === BASE_ENTREGA_77 ? new Set() : new Set(
  git(`diff --name-only ${BASE_RAMA}`).split('\n').concat(git('ls-files --others --exclude-standard').split('\n'))
    .map((f) => f.trim().replace(/^frontend\//, '')).filter(Boolean));
const omitida = (nombre) => console.log(`  \x1b[90mOMITIDA\x1b[0m ${nombre} (alcance de #77; esta rama cambia el archivo a propósito)`);

for (const [k, rel] of Object.entries(ARCH)) {
  const R = rama(rel), M = main(rel);
  const cambiadoAqui = CAMBIADOS_EN_RAMA.has(`src/${rel}`);
  if (cambiadoAqui) omitida(`${k}: mismas URLs`); else
  await prueba(`${k}: mismas URLs`, () => igual(urls(R), urls(M)));
  await prueba(`${k}: mismos nombres de archivo`, () => igual(archivos(R), archivos(M)));
  await prueba(`${k}: misma forma de descargar`, () => igual(descarga(R), descarga(M)));
  if (cambiadoAqui) { omitida(`${k}: fuera de los catch previstos, el archivo es idéntico a main`); continue; }
  await prueba(`${k}: fuera de los catch previstos, el archivo es idéntico a main`, () => {
    const a = sinCambiosPrevistos(R), b = sinCambiosPrevistos(M);
    if (a !== b) {
      const la = a.split('\n'), lb = b.split('\n'); const i = la.findIndex((l, j) => l !== lb[j]);
      throw new Error(`primera diferencia en la línea ${i + 1}:\n        rama: ${la[i]}\n        main: ${lb[i]}`);
    }
  });
}
await prueba('Notas por período: las 3 descargas de descargarBlob usan el extractor', () => {
  igual((rama(ARCH.notas).match(/await mensajeDeErrorDescarga\(e,/g) || []).length, 3);
});
await prueba('Notas por período: la carga de cursos y notas sigue igual', () => {
  const R = rama(ARCH.notas);
  contiene(R, "catch { setError('Error al cargar cursos'); }");
  contiene(R, "setError(err.response?.data?.error || 'Error al cargar notas')");
});
await prueba('Informes de Aprendizaje: imprimirPlanilla no cambia', () => {
  const trozo = (s) => s.slice(s.indexOf('const imprimirPlanilla'), s.indexOf("alert('No se pudo generar la planilla')"));
  igual(trozo(rama(ARCH.prim)), trozo(main(ARCH.prim)));
});
await prueba('SuperAdmin: solo cambia el catch de exportCSV', () => {
  igual((rama(ARCH.sa).match(/mensajeDeError\(/g) || []).length, 1);
  contiene(rama(ARCH.sa), "catch(e:any){setError(await mensajeDeError(e,{porDefecto:'Error exportando'}));}");
});
await prueba('rutas y roles sin cambios (Router.tsx idéntico)', () => igual(rama('Router.tsx'), main('Router.tsx')));

console.log(`\n${ok} pasan, ${fallos.length} fallan`);
process.exit(fallos.length ? 1 : 0);
