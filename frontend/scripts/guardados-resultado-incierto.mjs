/**
 * GUARDADOS — rechazo frente a resultado incierto (Comunicación, Psicología,
 * Notas personales).
 *
 * Sin framework, como los demás scripts:
 *   1. Transpila `utils/errorServidor.ts` y prueba `clasificarFalloEnvio`.
 *   2. Compara con `origin/main` (vía git): solo cambian los archivos previstos;
 *      notas académicas, asistencia, configuración, cierre de año y backend no.
 *   3. Comprueba que no se añadió ningún envío ni reintento automático: las
 *      líneas nuevas no hacen POST/PUT/DELETE y «Consultar lista» solo lee.
 *   4. Comprueba la doble protección de Psicología (ref + botón deshabilitado).
 * El comportamiento en pantalla se probó en la app real (ver el informe).
 *
 *   cd frontend && node scripts/guardados-resultado-incierto.mjs
 */
import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const FE = join(aqui, '..');
const CR = String.fromCharCode(13);
const rama = (rel) => readFileSync(join(FE, 'src', rel), 'utf8').split(CR).join('');
const git = (cmd) => execSync(`git ${cmd}`, { cwd: FE, encoding: 'utf8' }).split(CR).join('');

const js = transformSync(rama('utils/errorServidor.ts'), { loader: 'ts', format: 'esm' }).code;
const { clasificarFalloEnvio, MSG_ENVIO_INCIERTO } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = async (nombre, fn) => {
  try { await fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };
const contiene = (t, s) => { if (!String(t).includes(s)) throw new Error(`no contiene ${JSON.stringify(s)}`); };
const noContiene = (t, s) => { if (String(t).includes(s)) throw new Error(`NO debía contener ${JSON.stringify(s)}`); };

const axiosResp = (status, data) => ({ isAxiosError: true, request: {}, response: { status, data } });
const OP = { porDefecto: 'El servidor no aceptó el comunicado.' };
const INCIERTO = 'No pudimos confirmar el envío. Puede haberse guardado. Consulte la lista antes de volver a enviarlo.';

console.log('\nclasificarFalloEnvio');
await prueba('el texto incierto es exactamente el acordado', () => igual(MSG_ENVIO_INCIERTO, INCIERTO));
await prueba('400 con `error`: rechazo con el texto del servidor', async () =>
  igual(await clasificarFalloEnvio(axiosResp(400, { error: 'Título y contenido son requeridos' }), OP), { tipo: 'rechazo', mensaje: 'Título y contenido son requeridos' }));
await prueba('403 con `detail`: rechazo', async () =>
  igual(await clasificarFalloEnvio(axiosResp(403, { detail: 'No tiene permisos para esta acción' }), OP), { tipo: 'rechazo', mensaje: 'No tiene permisos para esta acción' }));
await prueba('409 en Blob con `error`: rechazo', async () =>
  igual(await clasificarFalloEnvio(axiosResp(409, new Blob([JSON.stringify({ error: 'Ya existe' })])), OP), { tipo: 'rechazo', mensaje: 'Ya existe' }));
await prueba('422 con `detail` en lista: rechazo con el mensaje por defecto, nunca un objeto', async () =>
  igual(await clasificarFalloEnvio(axiosResp(422, { detail: [{ msg: 'Field required' }] }), OP), { tipo: 'rechazo', mensaje: OP.porDefecto }));
await prueba('4xx con texto interno ficticio: rechazo sin mostrarlo', async () => {
  const r = await clasificarFalloEnvio(axiosResp(400, { error: 'postgres://usuario:CLAVE_FICTICIA@servidor/base' }), OP);
  igual(r.tipo, 'rechazo'); noContiene(r.mensaje, 'CLAVE_FICTICIA');
});
for (const [nombre, err] of [
  ['corte de conexión (ERR_NETWORK, sin response)', { isAxiosError: true, code: 'ERR_NETWORK', request: {} }],
  ['tiempo agotado (ECONNABORTED)', { isAxiosError: true, code: 'ECONNABORTED', request: {} }],
  ['500', axiosResp(500, { error: 'Detalle técnico: KeyError' })],
  ['502 de la pasarela', axiosResp(502, '<html>Bad Gateway</html>')],
  ['503', axiosResp(503, '')],
  ['504 de la pasarela', axiosResp(504, '<html>504 Gateway Time-out</html>')],
  ['error que no es de axios', new Error('fallo inesperado')],
  ['undefined', undefined],
]) {
  await prueba(`${nombre}: incierto`, async () => igual(await clasificarFalloEnvio(err, OP), { tipo: 'incierto', mensaje: INCIERTO }));
}

console.log('\nAlcance frente a main');
const PERMITIDOS = new Set([
  'frontend/src/utils/errorServidor.ts',
  'frontend/src/components/AvisoEnvio.tsx',
  'frontend/src/pages/comunicacion/ComunicacionPage.tsx',
  'frontend/src/pages/psicologia/PsicologiaPage.tsx',
  'frontend/src/pages/notas/NotasPage.tsx',
  'frontend/src/pages/dashboard/DashboardPage.tsx',
  'frontend/scripts/guardados-resultado-incierto.mjs',
  // corrección de auditoría: vigencia de «Consultar lista» y formato de la respuesta
  'frontend/src/utils/consultaVigente.ts',
  'frontend/scripts/aviso-envio-consultas.mjs',
]);
// Cambios de la rama: confirmados + sin confirmar + nuevos sin seguimiento dentro de frontend/src.
const cambiados = [...new Set([
  ...git('diff --name-only origin/main...HEAD').split('\n'),
  ...git('diff --name-only').split('\n'),
  ...git('ls-files --others --exclude-standard -- src scripts').split('\n').map((f) => f && 'frontend/' + f),
].filter(Boolean))].sort();
await prueba('solo cambian los archivos previstos', () => {
  const fuera = cambiados.filter((f) => !PERMITIDOS.has(f));
  if (fuera.length) throw new Error('cambios fuera del alcance: ' + fuera.join(', '));
});
for (const [nombre, patron] of [
  ['notas académicas', /^frontend\/src\/pages\/academico\//],
  ['asistencia', /^frontend\/src\/pages\/asistencia\//],
  ['configuración', /^frontend\/src\/pages\/configuracion\//],
  ['cierre / creación de año', /^frontend\/src\/pages\/cierre-ano\//],
  ['backend', /^backend\//],
  ['rutas y permisos (Router.tsx)', /^frontend\/src\/Router\.tsx$/],
]) {
  await prueba(`sin cambios en ${nombre}`, () => igual(cambiados.filter((f) => patron.test(f)), []));
}

console.log('\nSin envíos ni reintentos automáticos');
const lineasNuevas = (rel) => git(`diff origin/main -- src/${rel}`).split('\n').filter((l) => l.startsWith('+') && !l.startsWith('+++')).join('\n');
for (const rel of ['pages/comunicacion/ComunicacionPage.tsx', 'pages/psicologia/PsicologiaPage.tsx', 'pages/notas/NotasPage.tsx', 'pages/dashboard/DashboardPage.tsx', 'utils/errorServidor.ts']) {
  await prueba(`${rel}: las líneas nuevas no envían (sin api.post/put/delete ni setTimeout de reenvío)`, () => {
    const n = lineasNuevas(rel);
    if (/api\.(post|put|patch|delete)\(/.test(n)) throw new Error('línea nueva con escritura');
    if (/setTimeout\([^)]*(guardar|enviar|solicitar|publicar|handle)/i.test(n)) throw new Error('posible reintento temporizado');
  });
}
await prueba('AvisoEnvio no importa la API: «Consultar lista» solo llama a la lectura que recibe', () => {
  const A = rama('components/AvisoEnvio.tsx');
  noContiene(A, "services/api"); noContiene(A, 'api.');
});
await prueba('las funciones de consulta solo leen (api.get)', () => {
  for (const [rel, fn] of [['pages/comunicacion/ComunicacionPage.tsx', 'consultarComunicados'], ['pages/comunicacion/ComunicacionPage.tsx', 'consultarEnviados'],
    ['pages/psicologia/PsicologiaPage.tsx', 'consultarCasos'], ['pages/notas/NotasPage.tsx', 'consultarNotas'], ['pages/dashboard/DashboardPage.tsx', 'consultarNotas']]) {
    const s = rama(rel); const i = s.indexOf(`const ${fn} = async`); const cuerpo = s.slice(i, s.indexOf('};', i));
    contiene(cuerpo, 'api.get('); if (/api\.(post|put|patch|delete)\(/.test(cuerpo)) throw new Error(`${fn} escribe`);
  }
});

console.log('\nProtecciones de pantalla');
const PSI = rama('pages/psicologia/PsicologiaPage.tsx');
await prueba('Psicología: corte inmediato en el manejador (ref) antes de validar y enviar', () => {
  const i = PSI.indexOf('const handleSolicitar = async () => {');
  igual(PSI.slice(i).split('\n')[1].trim(), 'if (enviandoRef.current) return;');
  contiene(PSI, 'enviandoRef.current = true;'); contiene(PSI, 'enviandoRef.current = false;');
});
await prueba('Psicología: botón deshabilitado mientras se envía', () => contiene(PSI, 'disabled={enviando} loading={enviando}'));
const COM = rama('pages/comunicacion/ComunicacionPage.tsx');
await prueba('Comunicación: con el modal abierto el error no se pinta detrás del velo', () => contiene(COM, '{error && !showModal && ('));
await prueba('Comunicación: los 3 manejadores (mensaje individual y masivo, respuesta, comunicado) clasifican el fallo',
  () => igual((COM.match(/clasificarFalloEnvio\(err,/g) || []).length, 3));
await prueba('Comunicación: el masivo añade la nota de destinatarios', () => contiene(COM, "setNotaFallo(modoIndividual ? '' : NOTA_MASIVO);"));
for (const rel of ['pages/notas/NotasPage.tsx', 'pages/dashboard/DashboardPage.tsx']) {
  await prueba(`${rel}: el error ya no se queda solo en la consola`, () => {
    const s = rama(rel); contiene(s, 'setFalloEnvio(await clasificarFalloEnvio(e,');
    noContiene(s.slice(s.indexOf('const guardar = async'), s.indexOf('const eliminar')), 'console.error');
  });
}
await prueba('tras un fallo nunca se cierra ni se limpia el formulario (solo en el camino de éxito)', () => {
  for (const [rel, cierre] of [['pages/comunicacion/ComunicacionPage.tsx', 'setShowModal(false)'], ['pages/psicologia/PsicologiaPage.tsx', 'setShowModal(false)'], ['pages/notas/NotasPage.tsx', 'setShowForm(false)']]) {
    const s = rama(rel);
    for (const bloque of s.split('} catch').slice(1).map((b) => b.slice(0, b.indexOf('} finally') > 0 ? b.indexOf('} finally') : 300))) {
      if (bloque.includes('clasificarFalloEnvio') && bloque.includes(cierre)) throw new Error(`${rel}: el catch cierra el formulario`);
    }
  }
});

console.log(`\n${ok} pasan, ${fallos.length} fallan`);
process.exit(fallos.length ? 1 : 0);
