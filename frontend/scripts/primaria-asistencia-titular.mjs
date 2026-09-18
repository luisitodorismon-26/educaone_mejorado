/**
 * PRIMARIA P3.1 — la pantalla de asistencia en modo titular / solo lectura.
 *
 * Misma técnica que h1-escenarios: sin framework. Extrae del propio
 * `permisoAsistencia.ts` la función real y comprueba contra el fuente de
 * `AsistenciaPage.tsx` que el permiso venga del servidor y no se deduzca aquí.
 *
 *   cd frontend && node scripts/primaria-asistencia-titular.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const DIR = join(aqui, '..', 'src', 'pages', 'asistencia');
const leer = (f) => readFileSync(join(DIR, f), 'utf8').split(CR).join('');

const js = transformSync(leer('permisoAsistencia.ts'), { loader: 'ts', format: 'esm' }).code;
const mod = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
const PAGE = leer('AsistenciaPage.tsx');

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg) => {
  if (a !== b) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`);
};

// La regla real de la página, con la misma forma que el .tsx.
const puedeEditar = (esProfesor, respuesta) =>
  esProfesor && (respuesta?.puede_editar ?? null) !== false;

console.log('\nPRIMARIA — ASISTENCIA: TITULAR vs SOLO LECTURA\n' + '='.repeat(74));

prueba('1  el titular edita', () => {
  igual(puedeEditar(true, { puede_editar: true, motivo_solo_lectura: null }), true, 'titular');
});

prueba('2  el profesor del curso que NO es titular queda en solo lectura', () => {
  const r = { puede_editar: false, motivo_solo_lectura: 'no_titular' };
  igual(puedeEditar(true, r), false, 'no debe poder editar');
  igual(mod.textoSoloLectura(true, r.motivo_solo_lectura),
    'Asistencia registrada por el titular del curso. Vista de solo lectura.', 'texto');
});

prueba('3  curso sin titular: se dice qué falta y quién lo arregla', () => {
  const t = mod.textoSoloLectura(true, 'sin_titular');
  if (!t.includes('titular') || !t.includes('Dirección'))
    throw new Error('no explica el bloqueo: ' + t);
});

prueba('4  titularidad inconsistente: también se explica', () => {
  const t = mod.textoSoloLectura(true, 'titularidad_inconsistente');
  if (!t.includes('inconsistente') || !t.includes('Dirección'))
    throw new Error('no explica el bloqueo: ' + t);
});

prueba('5  quien no es profesor conserva el mensaje de siempre', () => {
  igual(mod.textoSoloLectura(false, null),
    'Solo los profesores pueden registrar asistencia.', 'direccion/coordinacion');
  igual(puedeEditar(false, { puede_editar: null }), false, 'no editan');
});

prueba('6  SECUNDARIA (puede_editar null) no cambia: el profesor sigue editando', () => {
  igual(puedeEditar(true, { puede_editar: null, motivo_solo_lectura: null }), true,
    'la regla de titular no debe aplicarse en Secundaria');
  // y si la respuesta ni siquiera trae el campo, tampoco
  igual(puedeEditar(true, {}), true, 'respuesta antigua sin el campo');
  igual(puedeEditar(true, undefined), true, 'sin cuerpo');
});

prueba('7  la página toma el permiso del SERVIDOR, no lo deduce', () => {
  if (!PAGE.includes('puedeEditar = esProfesor && permisoAsistencia.puedeEditar !== false'))
    throw new Error('la página ya no usa el permiso del servidor');
  if (!PAGE.includes('puedeEditar: res.data.puede_editar ?? null'))
    throw new Error('no lee puede_editar de la respuesta');
  if (!PAGE.includes('motivo: res.data.motivo_solo_lectura ?? null'))
    throw new Error('no lee el motivo');
});

prueba('8  la página NO deduce titularidad ni mira el horario', () => {
  if (/es_titular|esTitular/.test(PAGE))
    throw new Error('la página está deduciendo la titularidad por su cuenta');
  if (/\/horarios|Horario/.test(PAGE))
    throw new Error('la página está consultando el horario para decidir permisos');
});

prueba('9  en solo lectura se apagan los controles, NO la página', () => {
  // la tabla se sigue renderizando; lo que se desactiva son los botones
  if (!PAGE.includes('disabled={saving || !puedeMarcar || esRetirado}'))
    throw new Error('se perdió el apagado de los botones de estado');
  if (!PAGE.includes('{!puedeEditar && ('))
    throw new Error('se perdió el aviso de solo lectura');
  // el guardado masivo solo aparece si puede marcar
  if (!PAGE.includes('&& puedeMarcar && ('))
    throw new Error('el botón de guardar ya no depende del permiso');
});

prueba('10 S1 sigue siendo independiente del permiso de titular', () => {
  if (!PAGE.includes('const puedeMarcar = puedeEditar && !sesionNI;'))
    throw new Error('se alteró la relación con S1');
});

console.log('='.repeat(74));
console.log(`PRIMARIA ASISTENCIA TITULAR: ${ok}/${ok + fallos.length}`);
if (fallos.length) {
  console.log('\x1b[91mFALLARON:\x1b[0m');
  fallos.forEach(([n, m]) => console.log(`  - ${n}: ${m}`));
  process.exit(1);
}
console.log('\x1b[92mTODO VERDE\x1b[0m');
