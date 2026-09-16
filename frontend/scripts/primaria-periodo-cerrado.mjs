/**
 * PRIMARIA — la pantalla no puede decir "Guardado" si el backend saltó un
 * período cerrado.
 *
 * Misma técnica que h1-escenarios: no añade framework. Extrae del PROPIO
 * `periodoCerrado.ts` las funciones que leen la respuesta, las transpila con el
 * esbuild que ya trae Vite, y reconstruye el bucle de guardado de las dos
 * pestañas para comprobar qué mensaje sale.
 *
 *   cd frontend && node scripts/primaria-periodo-cerrado.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const DIR = join(aqui, '..', 'src', 'pages', 'academico', 'primaria');
const leer = (f) => readFileSync(join(DIR, f), 'utf8').split(CR).join('');

const fuente = leer('periodoCerrado.ts');
const js = transformSync(fuente, { loader: 'ts', format: 'esm' }).code;
const mod = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

const COMPETENCIA = leer('TabNotasPorCompetencia.tsx');
const PERIODO = leer('TabNotasPorPeriodo.tsx');

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg) => {
  if (JSON.stringify(a) !== JSON.stringify(b))
    throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`);
};

// El bucle real de las dos pestañas, con la misma forma que el .tsx: por cada
// POST se mira la respuesta, se acumulan los avisos, y al final el mensaje sale
// de si hubo alguno o no.
const guardar = (respuestas, etiqueta) => {
  const avisos = [];
  for (const data of respuestas) {
    const aviso = mod.avisoPeriodoCerrado(data);
    if (aviso) avisos.push(aviso);
  }
  return avisos.length > 0
    ? { tipo: 'warning', texto: mod.mensajeAvisos(avisos) }
    : { tipo: 'success', texto: `Guardado (${respuestas.length} ${etiqueta})` };
};

const OK = { message: 'Calificación primaria guardada', id: 7, calificacion: {} };
const CERRADO = {
  message: 'No se guardó ninguna calificación: el período está cerrado',
  id: null, calificacion: null,
  periodos_cerrados_ignorados: [1],
  aviso: 'No se guardaron los períodos P1 porque están cerrados. Solicite una corrección a Dirección si necesita editarlos.',
};
const PARCIAL = {
  message: 'Calificación primaria guardada', id: 7, calificacion: {},
  periodos_cerrados_ignorados: [1],
  aviso: 'No se guardaron los períodos P1 porque están cerrados. Solicite una corrección a Dirección si necesita editarlos.',
};

console.log('\nPRIMARIA — AVISO DE PERÍODO CERRADO\n' + '='.repeat(74));

prueba('1  todo entró: se mantiene el "Guardado" de siempre', () => {
  const m = guardar([OK, OK], 'estudiantes');
  igual(m.tipo, 'success', 'tipo');
  igual(m.texto, 'Guardado (2 estudiantes)', 'texto');
});

prueba('2  respuesta sin notas guardadas: NO dice "Guardado"', () => {
  const m = guardar([CERRADO], 'estudiantes');
  igual(m.tipo, 'warning', 'tiene que avisar, no felicitar');
  if (m.texto.includes('Guardado')) throw new Error('sigue diciendo Guardado: ' + m.texto);
  if (!m.texto.includes('P1')) throw new Error('no dice qué período: ' + m.texto);
});

prueba('3  parcial —P1 cerrado, P2 guardado— tampoco es un éxito total', () => {
  const m = guardar([PARCIAL], 'celdas');
  igual(m.tipo, 'warning', 'tipo');
  if (m.texto.includes('Guardado')) throw new Error('éxito silencioso: ' + m.texto);
});

prueba('4  un aviso entre varias respuestas buenas basta para avisar', () => {
  const m = guardar([OK, OK, PARCIAL, OK], 'estudiantes');
  igual(m.tipo, 'warning', 'un solo aviso tiene que ganar');
});

prueba('5  el mismo aviso repetido no se muestra N veces', () => {
  const m = guardar([CERRADO, CERRADO, CERRADO], 'estudiantes');
  igual(m.texto, CERRADO.aviso, 'se repitió el aviso');
});

prueba('6  se usa el texto del backend, no uno inventado en frontend', () => {
  const m = guardar([CERRADO], 'estudiantes');
  igual(m.texto, CERRADO.aviso, 'el frontend reescribió el mensaje del backend');
  // y si el backend no manda `aviso`, se arma uno a partir de los ids
  const sinTexto = { periodos_cerrados_ignorados: [2, 3] };
  const m2 = guardar([sinTexto], 'estudiantes');
  if (!m2.texto.includes('P2') || !m2.texto.includes('P3'))
    throw new Error('no nombra los períodos: ' + m2.texto);
});

prueba('7  una lista vacía o ausente no es un aviso', () => {
  igual(mod.avisoPeriodoCerrado(OK), null, 'respuesta normal');
  igual(mod.avisoPeriodoCerrado({ periodos_cerrados_ignorados: [] }), null, 'lista vacía');
  igual(mod.avisoPeriodoCerrado({}), null, 'sin la clave');
  igual(mod.avisoPeriodoCerrado(null), null, 'sin cuerpo');
  igual(mod.avisoPeriodoCerrado(undefined), null, 'undefined');
});

// --- que las dos pestañas usen de verdad este camino -----------------------
for (const [nombre, src] of [['E (por competencia)', COMPETENCIA], ['F (por período)', PERIODO]]) {
  prueba(`8 ${nombre}: mira la respuesta del POST y no felicita a ciegas`, () => {
    if (!src.includes("import { avisoPeriodoCerrado, mensajeAvisos } from './periodoCerrado';"))
      throw new Error('no importa el lector de la respuesta');
    if (!src.includes("const response = await api.post('/calificaciones-primaria', payload);"))
      throw new Error('sigue ignorando la respuesta del POST');
    if (!src.includes('const aviso = avisoPeriodoCerrado(response?.data);'))
      throw new Error('no inspecciona periodos_cerrados_ignorados');
    if (!src.includes("? { tipo: 'warning', texto: mensajeAvisos(avisos) }"))
      throw new Error('no cambia el mensaje cuando hubo períodos ignorados');
    // el onReload se mantiene en los dos caminos
    if (!src.includes('await onReload();'))
      throw new Error('se perdió la recarga');
    // y no se inventa logica de periodos en frontend
    if (/p[1-4]_cerrado/.test(src))
      throw new Error('el frontend está decidiendo sobre períodos cerrados');
  });
}

console.log('='.repeat(74));
console.log(`PRIMARIA PERÍODO CERRADO: ${ok}/${ok + fallos.length}`);
if (fallos.length) {
  console.log('\x1b[91mFALLARON:\x1b[0m');
  fallos.forEach(([n, m]) => console.log(`  - ${n}: ${m}`));
  process.exit(1);
}
console.log('\x1b[92mTODO VERDE\x1b[0m');
