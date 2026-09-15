/**
 * H2-B3 — lo que la cabecera le dice a un profesor sobre su nivel.
 *
 * Misma técnica que `h1-escenarios.mjs`: no añade framework. Extrae del PROPIO
 * MainLayout.tsx la función que decide el rótulo y la regla del badge, las
 * transpila con el esbuild que ya trae Vite y las ejecuta. Si alguien cambia el
 * .tsx, esto prueba la versión nueva; no hay copia que se quede desfasada.
 *
 *   cd frontend && node scripts/h2b3-niveles-profesor.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const FUENTE = join(aqui, '..', 'src', 'components', 'layout', 'MainLayout.tsx');
// El repo guarda CRLF en Windows: se normaliza para que los recortes
// por texto no dependan del final de línea.
const CR = String.fromCharCode(13);
const tsx = readFileSync(FUENTE, 'utf8').split(CR).join('');

function recorta(desde, hasta, nombre) {
  const i = tsx.indexOf(desde);
  if (i < 0) throw new Error(`no encuentro el inicio de ${nombre}`);
  const j = tsx.indexOf(hasta, i);
  if (j < 0) throw new Error(`no encuentro el final de ${nombre}`);
  return tsx.slice(i, j + hasta.length);
}

// La función real del componente, tal cual está en el fichero.
const fuenteEtiqueta = recorta(
  'export const etiquetaNivelesProfesor = (',
  '  return null;\n};', 'etiquetaNivelesProfesor');

const js = transformSync(fuenteEtiqueta, { loader: 'ts', format: 'esm' }).code;
const mod = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg) => {
  if (a !== b) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`);
};

const et = mod.etiquetaNivelesProfesor;

// La regla real del badge, copiada de la condición del JSX y comprobada
// después contra el fuente para que no puedan divergir.
const badge = (rol, niveles, nivelFijo, puedeCambiar, nivelVista) =>
  rol === 'profesor'
    ? (et(niveles) || null)
    : ((nivelFijo || (puedeCambiar && nivelVista !== 'todos'))
        ? `Viendo: ${(nivelFijo || nivelVista) === 'primaria' ? 'Primaria' : 'Secundaria'}`
        : null);

console.log('\nH2-B3 — NIVEL REAL DEL PROFESOR\n' + '='.repeat(74));

prueba('1  solo Primaria', () => {
  igual(et({ primaria: true, secundaria: false }), 'Imparte: Primaria', 'rótulo');
});

prueba('2  solo Secundaria', () => {
  igual(et({ primaria: false, secundaria: true }), 'Imparte: Secundaria', 'rótulo');
});

prueba('3  ambas', () => {
  igual(et({ primaria: true, secundaria: true }), 'Imparte: Primaria y Secundaria', 'rótulo');
});

prueba('4  cargando o sin datos: NO se inventa un nivel', () => {
  igual(et(null), null, 'null mientras carga');
  igual(et(undefined), null, 'undefined');
  igual(et({ primaria: false, secundaria: false }), null, 'los dos en false');
});

prueba('5  nivel_asignado Primaria pero asignaciones reales solo Secundaria', () => {
  // El caso que producía el badge equivocado: mandan las asignaciones.
  const reales = { primaria: false, secundaria: true };
  igual(badge('profesor', reales, 'primaria', false, 'todos'),
        'Imparte: Secundaria', 'nivel_asignado no puede mandar');
});

prueba('6  nivel_asignado Secundaria pero asignaciones en AMBAS', () => {
  const reales = { primaria: true, secundaria: true };
  igual(badge('profesor', reales, 'secundaria', false, 'todos'),
        'Imparte: Primaria y Secundaria', 'el profesor mixto se ve completo');
});

prueba('7  Dirección sin regresión: el badge de división sigue igual', () => {
  igual(badge('direccion', null, null, true, 'primaria'), 'Viendo: Primaria', 'switch primaria');
  igual(badge('direccion', null, null, true, 'secundaria'), 'Viendo: Secundaria', 'switch secundaria');
  igual(badge('direccion', null, null, true, 'todos'), null, 'en Todos no hay badge');
  // y el lente fijo de coordinación tampoco cambia
  igual(badge('coordinador', null, 'primaria', false, 'todos'), 'Viendo: Primaria', 'lente fijo');
});

prueba('8  es INFORMATIVO: el rótulo no recorta nada', () => {
  // El rótulo es una cadena. No devuelve un lente ni un filtro, así que no
  // puede recortar el horario del profesor mixto: no hay nada que aplicar.
  const r = et({ primaria: true, secundaria: true });
  igual(typeof r, 'string', 'el rótulo es solo texto');
  const src = tsx;
  if (/etiquetaNivelesProfesor\([^)]*\)\s*(===|!==|\?\?)/.test(src))
    throw new Error('el rótulo se está usando para decidir algo, no solo para mostrar');
  if (src.includes('filteredNavItems') && /filteredNavItems[\s\S]{0,600}etiquetaNivelesProfesor/.test(src))
    throw new Error('el rótulo entró en el filtro del menú');
});

prueba('8b la condición del badge en el .tsx es la que se probó arriba', () => {
  const src = tsx;
  if (!src.includes("user?.role === 'profesor' ? ("))
    throw new Error('el badge ya no separa al profesor del resto');
  if (!src.includes('etiquetaNivelesProfesor(nivelesProfesor)'))
    throw new Error('el badge del profesor no usa nivelesProfesor');
  // La rama del profesor no puede leer nivel_asignado. Se acota exactamente
  // donde empieza el `else`, no por un número de caracteres a ojo.
  const i = src.indexOf("user?.role === 'profesor' ? (");
  const j = src.indexOf(') : (nivelFijo', i);
  if (j < 0) throw new Error('no encuentro el cierre de la rama del profesor');
  const rama = src.slice(i, j);
  if (rama.includes('nivelFijo') || rama.includes('nivel_asignado') || rama.includes('nivelVista'))
    throw new Error('la rama del profesor mira algo que no son sus asignaciones');
  // y la rama de los demás roles se quedó exactamente como estaba
  const resto = src.slice(j, j + 500);
  if (!resto.includes('Viendo: ') || !resto.includes('División Primaria'))
    throw new Error('se alteró el badge de división del resto de roles');
});

prueba('9  el menú del profesor sigue usando nivelesProfesor, no el rótulo', () => {
  const src = tsx;
  if (!src.includes('if (!nivelesProfesor) return false;'))
    throw new Error('se perdió el fail-safe del menú');
  if (!src.includes('if (!nivelesProfesor[item.nivel]) return false;'))
    throw new Error('el menú dejó de filtrar por asignaciones reales');
});

console.log('='.repeat(74));
console.log(`H2-B3 NIVELES PROFESOR: ${ok}/${ok + fallos.length}`);
if (fallos.length) {
  console.log('\x1b[91mFALLARON:\x1b[0m');
  fallos.forEach(([n, m]) => console.log(`  - ${n}: ${m}`));
  process.exit(1);
}
console.log('\x1b[92mTODO VERDE\x1b[0m');
