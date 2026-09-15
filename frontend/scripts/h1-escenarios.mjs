/**
 * H1 — escenarios A–M de la cuadrícula de Horarios.
 *
 * No añade ningún framework de tests: extrae del PROPIO HorariosPage.tsx las
 * funciones que deciden qué se ve —`seSolapan`, `identidadBloque`, el cálculo de
 * conflictos, la agrupación y el rótulo de la columna de hora—, las transpila
 * con el esbuild que ya trae Vite y las ejecuta contra los casos reales de
 * producción. Si alguien cambia esas funciones en el .tsx, este script prueba la
 * versión nueva; no hay una copia que se pueda quedar desfasada.
 *
 *   cd frontend && node scripts/h1-escenarios.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const FUENTE = join(aqui, '..', 'src', 'pages', 'horarios', 'HorariosPage.tsx');
const tsx = readFileSync(FUENTE, 'utf8');
const NL = String.fromCharCode(10);

/** Recorta un fragmento del fichero real entre dos marcas. */
function recorta(desde, hasta, nombre) {
  const i = tsx.indexOf(desde);
  if (i < 0) throw new Error(`no encuentro el inicio de ${nombre}`);
  const j = tsx.indexOf(hasta, i);
  if (j < 0) throw new Error(`no encuentro el final de ${nombre}`);
  return tsx.slice(i, j);
}

// --- helpers de módulo, tal cual están en el componente --------------------
const helpers = recorta('const aMinutos =', '// Generar bloques de horario', 'helpers');

// --- getHorariosEnCelda, tal cual (usa `horarios` del closure) ------------
const cuerpoCelda = recorta(
  '    horarios.filter(h => h.dia === dia',
  ';' + NL + NL + '  // Ids de bloques', 'getHorariosEnCelda');

// --- cuerpo del cálculo de conflictos, tal cual --------------------------
const cuerpoConflictos = recorta(
  '    const clases = horarios.filter', '    return ids;\n  })();', 'idsEnConflicto');

// --- cuerpo de la agrupación, tal cual -----------------------------------
const cuerpoAgrupar = recorta(
  '    const grupos = new Map<string, Horario[]>();',
  '    return Array.from(grupos.values());', 'agruparPorIdentidad');

// --- cuerpo del rótulo de la columna de hora, tal cual --------------------
const MARCA_RET_BUSQUEDA = '      return { ' + NL + '        inicio,';
const cuerpoFines = recorta(
  '      const finesDistintos = Array.from(new Set(',
  '      return { \n        inicio,', 'finesDistintos');

// --- el return real del rótulo, tal cual ---------------------------------
const MARCA_RET = MARCA_RET_BUSQUEDA;
const retornoFines = recorta(MARCA_RET, '      };', 'retorno del rótulo')
  .replace(MARCA_RET, '      return { ') + '      };';

const modulo = `
type Horario = any;
${helpers}
export function conflictos(horarios: Horario[]): Set<number> {
${cuerpoConflictos}
  return ids;
}
export function agrupar(bloques: Horario[]) {
${cuerpoAgrupar}
  return Array.from(grupos.values());
}
export function celdaDe(horarios: Horario[]) {
  return (dia: string, hora: {inicio: string; fin: string}) =>
${cuerpoCelda};
}
export function rotuloFila(horarios: Horario[], inicio: string) {
${cuerpoFines}
${retornoFines}
}
export { seSolapan, identidadBloque, aMinutos, profesorIdParaGuardar, recargarSegunVista };
`;

const js = transformSync(modulo, { loader: 'ts', format: 'esm' }).code;
const mod = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

// ==========================================================================
let ok = 0, fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const iguales = (a, b, msg) => {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error(`${msg}\n        esperado ${B}\n        obtenido ${A}`);
};

// Misma forma que devuelve `Horario.to_dict()` en el backend: trae `profesor_id`
// y NO trae el nombre del profesor. Fabricar un `profesor` que el API nunca
// envía era lo que ocultaba el fallo de la vista Por Curso.
const h = (id, dia, ini, fin, extra = {}) => ({
  id, dia, hora_inicio: ini, hora_fin: fin, tipo_bloque: 'clase',
  profesor_id: 4, curso_id: 1, asignatura_id: 1,
  asignatura: 'Mat', curso: '1ro A', tanda: 'Matutina', aula: null, ...extra,
});
// Se usa la MISMA getHorariosEnCelda del componente, no una reimplementación.
const enCelda = (hs, dia, inicio) => mod.celdaDe(hs)(dia, { inicio, fin: '' });

console.log('\nH1 — ESCENARIOS DE LA CUADRÍCULA\n' + '='.repeat(74));

prueba('A  celda normal: un bloque, un grupo, sin conflicto', () => {
  const hs = [h(1, 'Lunes', '08:00', '08:45')];
  iguales(mod.agrupar(enCelda(hs, 'Lunes', '08:00')).length, 1, 'grupos');
  iguales([...mod.conflictos(hs)], [], 'no debe haber conflicto');
  iguales(mod.rotuloFila(hs, '08:00'), { fin: '08:45', variosFines: false }, 'rótulo');
});

// El caso real: Luis Dorismon, lunes 11:15. Antes solo se veía uno de los dos.
prueba('B  mismo inicio, dos clases distintas: AMBAS visibles y en conflicto', () => {
  const hs = [
    h(19, 'Lunes', '11:15', '12:00', { curso_id: 2, asignatura_id: 5, asignatura: 'Inglés', curso: '2do Secundaria A' }),
    h(37, 'Lunes', '11:15', '12:00', { curso_id: 1, asignatura_id: 17, asignatura: 'Francés', curso: '1ro Secundaria A' }),
  ];
  const celda = enCelda(hs, 'Lunes', '11:15');
  iguales(celda.length, 2, 'la celda trae los dos bloques');
  iguales(mod.agrupar(celda).length, 2, 'son dos tarjetas, no una');
  iguales([...mod.conflictos(hs)].sort((a, b) => a - b), [19, 37], 'ambos marcados');
});

prueba('C  mismo inicio, tres clases: las tres visibles', () => {
  const hs = [
    h(42, 'Lunes', '08:15', '09:00', { curso_id: 4 }),
    h(43, 'Lunes', '08:15', '09:00', { curso_id: 2 }),
    h(77, 'Lunes', '08:15', '09:00', { curso_id: 3 }),
  ];
  iguales(mod.agrupar(enCelda(hs, 'Lunes', '08:15')).length, 3, 'tres tarjetas');
  iguales([...mod.conflictos(hs)].sort((a, b) => a - b), [42, 43, 77], 'los tres marcados');
});

prueba('D  dos duplicados exactos: UN grupo que dice que son 2', () => {
  const hs = [h(34, 'Viernes', '09:00', '09:45'), h(35, 'Viernes', '09:00', '09:45')];
  const g = mod.agrupar(enCelda(hs, 'Viernes', '09:00'));
  iguales(g.length, 1, 'las idénticas forman un solo grupo');
  iguales(g[0].length, 2, 'y el grupo dice que son 2');
  iguales(g[0].map(x => x.id), [34, 35], 'con sus ids, para Dirección');
  iguales([...mod.conflictos(hs)], [], 'repetido NO es choque de agenda');
});

prueba('E  ocho duplicados exactos: el grupo dice 8, no se deduplica a 1', () => {
  const hs = [62, 63, 64, 65, 66, 67, 68, 69].map(id => h(id, 'Jueves', '08:15', '09:00'));
  const g = mod.agrupar(enCelda(hs, 'Jueves', '08:15'));
  iguales(g.length, 1, 'un grupo');
  iguales(g[0].length, 8, 'de ocho registros');
  iguales(g[0].map(x => x.id), [62, 63, 64, 65, 66, 67, 68, 69], 'los ocho ids');
});

prueba('F  mismo inicio, finales distintos: no se inventa ninguna hora_fin', () => {
  const hs = [
    h(1, 'Lunes', '11:15', '11:45', { curso_id: 1 }),
    h(2, 'Lunes', '11:15', '12:00', { curso_id: 2 }),
  ];
  const r = mod.rotuloFila(hs, '11:15');
  iguales(r.variosFines, true, 'la fila avisa que hay varios finales');
  iguales(r.fin, '11:15', 'y NO elige uno de los dos como si fuera el de la fila');
  // cada tarjeta conserva el suyo
  iguales(enCelda(hs, 'Lunes', '11:15').map(x => x.hora_fin), ['11:45', '12:00'], 'finales propios');
});

prueba('G  solapamiento con inicio distinto: ambos marcados (caso 78/79)', () => {
  const hs = [
    h(78, 'Miércoles', '12:00', '12:45'),
    h(79, 'Miércoles', '12:40', '13:15', { asignatura_id: 2 }),
  ];
  iguales([...mod.conflictos(hs)].sort((a, b) => a - b), [78, 79], 'los 5 minutos cuentan');
  // y viven en filas distintas, cada una con su propio rótulo
  iguales(mod.rotuloFila(hs, '12:00').variosFines, false, 'fila 12:00');
  iguales(mod.rotuloFila(hs, '12:40').variosFines, false, 'fila 12:40');
});

prueba('H  bloques consecutivos NO son conflicto', () => {
  const hs = [h(1, 'Lunes', '11:15', '12:00'), h(2, 'Lunes', '12:00', '12:45', { curso_id: 2 })];
  iguales([...mod.conflictos(hs)], [], '12:00 fin y 12:00 inicio no se pisan');
  iguales(mod.seSolapan(hs[0], hs[1]), false, 'seSolapan directo');
});

prueba('I  Libre y Recreo no cuentan como choque académico', () => {
  const hs = [
    h(1, 'Lunes', '10:00', '10:45', { tipo_bloque: 'libre', curso_id: null, asignatura_id: null }),
    h(2, 'Lunes', '10:00', '10:45', { tipo_bloque: 'recreo', curso_id: null, asignatura_id: null }),
    h(3, 'Lunes', '10:00', '10:45'),
  ];
  iguales([...mod.conflictos(hs)], [], 'una clase sola con libre/recreo no es conflicto');
});

prueba('J/K  el cálculo es el mismo en Por Profesor y en Por Curso', () => {
  // El array llega acotado a un profesor (todas sus clases, cursos distintos)
  const porProfesor = [
    h(19, 'Lunes', '11:15', '12:00', { profesor_id: 4, curso_id: 2 }),
    h(37, 'Lunes', '11:15', '12:00', { profesor_id: 4, curso_id: 1, asignatura_id: 17 }),
  ];
  // o a un curso (todos sus profesores/materias)
  const porCurso = [
    h(80, 'Lunes', '11:15', '12:00', { profesor_id: 4, curso_id: 1, asignatura_id: 5 }),
    h(81, 'Lunes', '11:15', '12:00', { profesor_id: 5, curso_id: 1, asignatura_id: 1 }),
  ];
  iguales([...mod.conflictos(porProfesor)].sort((a, b) => a - b), [19, 37], 'por profesor');
  iguales([...mod.conflictos(porCurso)].sort((a, b) => a - b), [80, 81], 'por curso');
});

prueba('L  editar apunta al id correcto de cada tarjeta', () => {
  const hs = [
    h(19, 'Lunes', '11:15', '12:00', { curso_id: 2, asignatura_id: 5 }),
    h(37, 'Lunes', '11:15', '12:00', { curso_id: 1, asignatura_id: 17 }),
  ];
  // cada grupo expone su propio primer elemento, que es el que recibe Editar
  const g = mod.agrupar(enCelda(hs, 'Lunes', '11:15'));
  iguales(g.map(x => x[0].id), [19, 37], 'un id distinto por tarjeta');
});

prueba('M  la celda anómala se distingue de la normal (protege Eliminar)', () => {
  const normal = [h(1, 'Lunes', '08:00', '08:45')];
  const conflicto = [
    h(19, 'Lunes', '11:15', '12:00', { curso_id: 2, asignatura_id: 5 }),
    h(37, 'Lunes', '11:15', '12:00', { curso_id: 1, asignatura_id: 17 }),
  ];
  const repetido = [h(34, 'Viernes', '09:00', '09:45'), h(35, 'Viernes', '09:00', '09:45')];
  const anomala = (hs, dia, ini) => {
    const celda = enCelda(hs, dia, ini);
    const ids = mod.conflictos(hs);
    return celda.some(x => ids.has(x.id)) || mod.agrupar(celda).some(g => g.length > 1);
  };
  iguales(anomala(normal, 'Lunes', '08:00'), false, 'normal: Eliminar sigue activo');
  iguales(anomala(conflicto, 'Lunes', '11:15'), true, 'conflicto: Eliminar protegido');
  iguales(anomala(repetido, 'Viernes', '09:00'), true, 'repetido: Eliminar protegido');
});

// El bloqueador que encontró la revisión: en Por Curso, dos profesores distintos
// dando lo mismo a la misma hora. Con la identidad basada en el NOMBRE —un campo
// que el API no envía— ambos valían `undefined`, se agrupaban como "2 registros
// idénticos" y su conflicto entre sí desaparecía. La identidad va por id.
prueba('N  POR CURSO: dos profesores distintos NO son el mismo registro', () => {
  const hs = [
    h(80, 'Lunes', '11:15', '12:00', { profesor_id: 10, curso_id: 1, asignatura_id: 1 }),
    h(81, 'Lunes', '11:15', '12:00', { profesor_id: 11, curso_id: 1, asignatura_id: 1 }),
  ];
  const celda = enCelda(hs, 'Lunes', '11:15');
  iguales(celda.length, 2, 'la celda trae los dos');
  iguales(mod.agrupar(celda).length, 2, 'DOS grupos: no son duplicados');
  iguales(mod.agrupar(celda).map(g => g.length), [1, 1], 'ninguno dice "2 idénticos"');
  iguales([...mod.conflictos(hs)].sort((a, b) => a - b), [80, 81],
          'y su choque entre sí SÍ se detecta');
});

prueba('N2 mismo profesor_id y todo lo demás igual: eso SÍ es repetido', () => {
  const hs = [
    h(34, 'Viernes', '09:00', '09:45', { profesor_id: 4 }),
    h(35, 'Viernes', '09:00', '09:45', { profesor_id: 4 }),
  ];
  const g = mod.agrupar(enCelda(hs, 'Viernes', '09:00'));
  iguales(g.length, 1, 'un solo grupo');
  iguales(g[0].length, 2, 'que declara 2 registros');
  iguales([...mod.conflictos(hs)], [], 'repetido no es choque de agenda');
});

prueba('N3 el nombre del profesor no participa en la identidad', () => {
  // Aunque el API llegara a enviar nombres distintos, o ninguno, la agrupación
  // depende solo de los ids: no se puede confundir por como se escriba un nombre.
  const a = h(1, 'Lunes', '08:00', '08:45', { profesor_id: 7 });
  const b = h(2, 'Lunes', '08:00', '08:45', { profesor_id: 7 });
  iguales(mod.identidadBloque(a), mod.identidadBloque(b), 'mismos ids, misma identidad');
  const c = h(3, 'Lunes', '08:00', '08:45', { profesor_id: 8 });
  if (mod.identidadBloque(a) === mod.identidadBloque(c))
    throw new Error('profesores distintos comparten identidad');
  // y la identidad NO menciona ningún nombre
  if (/Prof|Luis|Julio/.test(mod.identidadBloque(a)))
    throw new Error('la identidad incluye un nombre: ' + mod.identidadBloque(a));
});

// ==========================================================================
// O — GUARDAR DESDE POR CURSO CON EL SELECTOR DE POR PROFESOR "SUCIO"
//
// H1 deja Editar disponible en los bloques conflictivos, asi que este camino
// —que ya existia— pasa a usarse justo donde mas dano haria: reasignar la clase
// a otro docente mientras Direccion intenta resolver un conflicto.
// ==========================================================================
prueba('O  editar Por Curso NO usa el profesor que quedo en el selector', () => {
  // Direccion miro Por Profesor (id 4), luego paso a Por Curso y edita un
  // bloque cuyo profesor real es el 11.
  const editando = h(200, 'Lunes', '11:15', '12:00', { profesor_id: 11, curso_id: 3 });
  const profesorIdSelector = 4;
  const efectivo = mod.profesorIdParaGuardar(editando, profesorIdSelector);
  iguales(efectivo, 11, 'manda el profesor del BLOQUE, no el del selector');
  if (efectivo === profesorIdSelector)
    throw new Error('el PUT reasignaria la clase al profesor equivocado');
});

prueba('O2 crear un bloque nuevo sigue usando el profesor del selector', () => {
  iguales(mod.profesorIdParaGuardar(null, 4), 4, 'alta desde Por Profesor');
  iguales(mod.profesorIdParaGuardar(undefined, 7), 7, 'sin bloque en edicion');
});

prueba('O3 un profesor_id 0 del bloque no se confunde con "no hay bloque"', () => {
  // ?? solo cae al selector con null/undefined: un 0 legitimo se respeta.
  iguales(mod.profesorIdParaGuardar({ profesor_id: 0 }, 4), 0, 'respeta el 0');
});

prueba('P  tras guardar se refresca la vista que se esta mirando', () => {
  const llamadas = [];
  const porProf = () => llamadas.push('profesor');
  const porCurso = () => llamadas.push('curso');

  mod.recargarSegunVista('profesor', porProf, porCurso);
  iguales(llamadas, ['profesor'], 'Por Profesor refresca el profesor');

  llamadas.length = 0;
  mod.recargarSegunVista('curso', porProf, porCurso);
  iguales(llamadas, ['curso'], 'Por Curso refresca el CURSO, no el profesor');
});

console.log('='.repeat(74));
console.log(`H1 ESCENARIOS: ${ok}/${ok + fallos.length}`);
if (fallos.length) {
  console.log('\x1b[91mFALLARON:\x1b[0m');
  fallos.forEach(([n, m]) => console.log(`  - ${n}: ${m}`));
  process.exit(1);
}
console.log('\x1b[92mTODO VERDE\x1b[0m');
