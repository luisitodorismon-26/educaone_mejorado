/**
 * PRIMARIA P2A-R1 — la pantalla de recuperación no puede inventarse la
 * modalidad, ni perder intervenciones del historial, ni dejar pasar un
 * formulario incompleto.
 *
 * Misma técnica que los otros harnesses: sin framework. Extrae del PROPIO
 * `recuperacionCualitativa.ts` las funciones puras, las transpila con el
 * esbuild que ya trae Vite, y además comprueba sobre el texto de los .tsx que
 * la columna RP desaparece en 1ro/2do y que el rótulo viejo ya no está.
 *
 *   cd frontend && node scripts/primaria-recuperacion-cualitativa.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const SRC = join(aqui, '..', 'src', 'pages');
const leer = (...p) => readFileSync(join(SRC, ...p), 'utf8').split(CR).join('');

const fuente = leer('recuperaciones-primaria', 'recuperacionCualitativa.ts');
const js = transformSync(fuente, { loader: 'ts', format: 'esm' }).code;
const mod = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

const TIPOS = leer('academico', 'primaria', 'tipos.ts');
const POR_PERIODO = leer('academico', 'primaria', 'TabNotasPorPeriodo.tsx');
const POR_COMPETENCIA = leer('academico', 'primaria', 'TabNotasPorCompetencia.tsx');
const TAB_CUAL = leer('recuperaciones-primaria', 'TabRecuperacionCualitativa.tsx');

// `tipos.ts` vive en otra carpeta y se carga igual que el otro módulo.
const jsTipos = transformSync(TIPOS, { loader: 'ts', format: 'esm' }).code;
const tipos = await import('data:text/javascript;base64,' + Buffer.from(jsTipos).toString('base64'));
const mod2 = () => tipos;

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg) => {
  if (JSON.stringify(a) !== JSON.stringify(b))
    throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`);
};
const cierto = (v, msg) => { if (!v) throw new Error(msg); };

console.log('\n\x1b[1mMODALIDAD POR GRADO\x1b[0m');

prueba('1ro y 2do son cualitativos; 3ro a 6to no', () => {
  igual([1, 2, 3, 4, 5, 6].map(mod.esGradoCualitativo),
        [true, true, false, false, false, false], 'modalidad por grado');
});

prueba('el número del grado sale del nombre, y ante la duda es null', () => {
  igual(mod.numeroDeGrado('1ro Primaria'), 1, '1ro');
  igual(mod.numeroDeGrado('2do Primaria'), 2, '2do');
  igual(mod.numeroDeGrado('6to Primaria'), 6, '6to');
  igual(mod.numeroDeGrado('Primero'), null, 'sin dígito no se adivina');
  igual(mod.numeroDeGrado('9no Primaria'), null, 'fuera de 1..6');
  igual(mod.numeroDeGrado(''), null, 'vacío');
  igual(mod.numeroDeGrado(null), null, 'null');
});

prueba('un grado indeterminado NO cae en cualitativa por defecto', () => {
  igual(mod.esGradoCualitativo(mod.numeroDeGrado('Curso raro')), false,
        'sin número no debe abrirse la vía cualitativa');
});

console.log('\n\x1b[1mVALIDACIÓN DEL FORMULARIO\x1b[0m');

const base = {
  estudiante_id: 7, competencia_numero: null, periodo: 1,
  aspectos_no_logrados: 'No identifica las vocales',
  estrategias_evidencias: '', resultado: 'no_lograda', observacion: '',
};

prueba('un borrador completo pasa', () => {
  igual(mod.validarIntervencion(base), null, 'debería pasar');
});

prueba('faltan estudiante, período, aspectos o resultado', () => {
  cierto(mod.validarIntervencion({ ...base, estudiante_id: null }), 'sin estudiante');
  cierto(mod.validarIntervencion({ ...base, periodo: null }), 'sin período');
  cierto(mod.validarIntervencion({ ...base, periodo: 5 }), 'período 5');
  cierto(mod.validarIntervencion({ ...base, aspectos_no_logrados: '   ' }), 'aspectos en blanco');
  cierto(mod.validarIntervencion({ ...base, resultado: null }), 'sin resultado');
});

prueba('la competencia puede ser 1/2/3 o «varias» (null)', () => {
  igual(mod.validarIntervencion({ ...base, competencia_numero: 2 }), null, 'C2');
  igual(mod.validarIntervencion({ ...base, competencia_numero: null }), null, 'varias');
  cierto(mod.validarIntervencion({ ...base, competencia_numero: 4 }), 'C4 no existe');
});

prueba('no se acepta una nota como resultado', () => {
  cierto(mod.validarIntervencion({ ...base, resultado: '65' }), '65 no es un resultado');
  cierto(mod.validarIntervencion({ ...base, resultado: 'lograda_casi' }), 'valor inventado');
});

console.log('\n\x1b[1mHISTORIAL\x1b[0m');

const i = (id, est, fecha, resultado, activo = true) => ({
  id, estudiante_id: est, fecha_registro: fecha, resultado, activo,
  competencia_numero: 1, periodo: 2, aspectos_no_logrados: 'x',
  estrategias_evidencias: null, observacion: null, registrado_por: 9, motivo_retiro: null,
});

prueba('dos intervenciones del mismo estudiante y período conviven', () => {
  const h = mod.historialPorEstudiante([
    i(2, 50, '2025-12-01', 'lograda'),
    i(1, 50, '2025-11-01', 'no_lograda'),
  ]);
  igual(h.get(50).map(x => x.id), [1, 2], 'las dos, en orden cronológico');
  igual(h.get(50).map(x => x.resultado), ['no_lograda', 'lograda'], 'no se deduplica');
});

prueba('las retiradas siguen en el historial', () => {
  const h = mod.historialPorEstudiante([i(1, 50, '2025-11-01', 'no_lograda', false)]);
  igual(h.get(50).length, 1, 'la retirada no se oculta');
  igual(h.get(50)[0].activo, false, 'queda marcada');
});

prueba('cada estudiante lleva su propia lista', () => {
  const h = mod.historialPorEstudiante([
    i(1, 50, '2025-11-01', 'lograda'), i(2, 51, '2025-11-02', 'lograda'),
  ]);
  igual([...h.keys()].sort(), [50, 51], 'dos estudiantes');
});

prueba('sólo el autor modifica, y sólo si está activa', () => {
  const viva = i(1, 50, '2025-11-01', 'lograda');
  const muerta = i(2, 50, '2025-11-01', 'lograda', false);
  igual(mod.puedeModificar(viva, 9, true), true, 'autor profesor');
  igual(mod.puedeModificar(viva, 8, true), false, 'otro profesor');
  igual(mod.puedeModificar(viva, 9, false), false, 'no profesor');
  igual(mod.puedeModificar(muerta, 9, true), false, 'retirada');
});

console.log('\n\x1b[1mLA PANTALLA NO SE INVENTA LA MODALIDAD\x1b[0m');

prueba('la pestaña cualitativa la pide al servidor', () => {
  cierto(TAB_CUAL.includes('/recuperacion-primaria/contexto/'),
         'debe consultar el contexto del curso');
  cierto(!/esGradoCualitativo|numeroDeGrado/.test(TAB_CUAL),
         'no debe deducir la modalidad por su cuenta');
});

prueba('si el curso es cuantitativo, remite a Calificaciones', () => {
  cierto(TAB_CUAL.includes("modalidad === 'cuantitativa'"), 'debe contemplar el caso');
  cierto(/cuantitativa<\/strong>/.test(TAB_CUAL), 'debe explicarlo');
});

console.log('\n\x1b[1mRP NUMÉRICA FUERA DE 1ro Y 2do\x1b[0m');

prueba('admiteRpNumerica sólo cierra la puerta a lo cualitativo', () => {
  igual(mod2().admiteRpNumerica('cualitativa'), false, '1ro/2do');
  igual(mod2().admiteRpNumerica('cuantitativa'), true, '3ro-6to');
  igual(mod2().admiteRpNumerica(null), true, 'sin dato, no se oculta nada');
});

prueba('las dos pestañas condicionan la columna RP', () => {
  for (const [nombre, src] of [['por período', POR_PERIODO], ['por competencia', POR_COMPETENCIA]]) {
    cierto(src.includes('const conRp = admiteRpNumerica('), `${nombre}: falta conRp`);
    cierto(/\{conRp && <th/.test(src), `${nombre}: la cabecera RP no es condicional`);
    cierto(/\{conRp && <td/.test(src), `${nombre}: la celda RP no es condicional`);
  }
});

prueba('el rótulo ambiguo desapareció', () => {
  for (const [nombre, src] of [['por período', POR_PERIODO], ['por competencia', POR_COMPETENCIA]]) {
    cierto(!src.includes('Se toma el mayor de los dos'), `${nombre}: sigue el texto viejo`);
    cierto(src.includes('AYUDA_RP_PRIMARIA'), `${nombre}: falta la ayuda nueva`);
  }
  cierto(TIPOS.includes('calificación final del período después de la recuperación'),
         'la ayuda debe decir qué se escribe en RP');
  cierto(TIPOS.includes('No escriba los puntos ganados'),
         'la ayuda debe decir qué NO se escribe');
});

console.log('');
if (fallos.length) {
  console.log(`\x1b[91m\x1b[1m  ${fallos.length} fallo(s) de ${ok + fallos.length}\x1b[0m`);
  for (const [n, e] of fallos) console.log(`   - ${n}: ${e}`);
  process.exit(1);
}
console.log(`\x1b[92m\x1b[1m  ${ok}/${ok} pruebas pasaron\x1b[0m`);
