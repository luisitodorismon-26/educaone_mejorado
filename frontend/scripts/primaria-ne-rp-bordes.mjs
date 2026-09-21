/**
 * PRIMARIA R2-A8 — los tres bordes que la pantalla llevaba mal.
 *
 *   A8.1  desmarcar un NE ya guardado tiene que encender el botón Guardar.
 *   A8.2  marcar NE y arrepentirse NO puede borrar la nota que había.
 *   A8.4  una RP ya asentada no puede desaparecer de la pantalla porque la
 *         P suba de 65 — desde R2 la RP ES la nota del período.
 *
 * Misma técnica que el resto de harnesses de Primaria: sin framework. Se
 * importa `rpEditable` del propio `tipos.ts` transpilado (eso es la función
 * real, no una copia), y para el estado de borradores se reconstruye el bucle
 * de `TabNotasPorPeriodo.tsx` con la misma forma que el .tsx. Para que esa
 * reconstrucción no se separe del componente, hay además comprobaciones
 * ESTRUCTURALES sobre el fuente: si alguien vuelve a meter el borrador
 * destructivo en `marcarNE`, este fichero falla.
 *
 *   cd frontend && node scripts/primaria-ne-rp-bordes.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const DIR = join(aqui, '..', 'src', 'pages', 'academico', 'primaria');
const leer = (f) => readFileSync(join(DIR, f), 'utf8').split(CR).join('');

const js = transformSync(leer('tipos.ts'), { loader: 'ts', format: 'esm' }).code;
const T = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

const PERIODO = leer('TabNotasPorPeriodo.tsx');
const COMPETENCIA = leer('TabNotasPorCompetencia.tsx');

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

// ─────────────────────────────────────────────────────────────────────
// La pestaña, reconstruida con la misma forma que el .tsx.
// `servidor` = las competencias tal y como llegaron del backend.
// ─────────────────────────────────────────────────────────────────────
function pantalla(servidor, periodo = 1) {
  const campoP = `p${periodo}`, campoRP = `rp${periodo}`, campoNE = `ne${periodo}`;
  const drafts = {}, draftsNE = {};
  const k = (est, comp) => `${est}-${comp}`;
  const comp = (est, c) => servidor.find(x => x.est === est && x.competencia_numero === c);

  const getValor = (est, c, campo) => {
    const d = drafts[k(est, c)]?.[campo];
    if (d !== undefined) return d;
    const v = comp(est, c)?.[campo];
    return v != null ? String(v) : '';
  };
  const getNE = (est, c) => {
    const d = draftsNE[k(est, c)]?.[campoNE];
    if (d !== undefined) return d;
    return Boolean(comp(est, c)?.[campoNE]);
  };

  const api = {
    escribir(est, c, campo, valor) {
      drafts[k(est, c)] = { ...drafts[k(est, c)], [campo]: valor };
    },
    marcarNE(est, c, valor) {
      // A8.2: SOLO toca draftsNE. Ni un setDrafts aquí.
      draftsNE[k(est, c)] = { ...(draftsNE[k(est, c)] || {}), [campoNE]: valor };
    },
    // A8.1: unión de notas y NE, sin contar dos veces, y sin contar un NE
    // que volvió a quedarse como estaba.
    celdasSucias() {
      const sucias = new Set();
      for (const [key, d] of Object.entries(drafts)) {
        if (Object.keys(d).length > 0) sucias.add(key);
      }
      for (const [key, d] of Object.entries(draftsNE)) {
        const propuesto = d?.[campoNE];
        if (propuesto === undefined) continue;
        const [est, c] = key.split('-').map(Number);
        const guardado = Boolean(comp(est, c)?.[campoNE]);
        if (propuesto !== guardado) sucias.add(key);
      }
      return sucias;
    },
    payloads() {
      return Array.from(api.celdasSucias()).map(key => {
        const [est, c] = key.split('-').map(Number);
        const p = { estudiante_id: est, competencia_numero: c };
        const neFinal = getNE(est, c);
        if (!neFinal) {
          for (const [campo, val] of Object.entries(drafts[key] || {})) {
            p[campo] = val === '' ? null : Number(val);
          }
        }
        for (const [campo, val] of Object.entries(draftsNE[key] || {})) p[campo] = val;
        return p;
      });
    },
    // Lo que se ve en la casilla RP.
    rpEnPantalla(est, c) {
      const pVal = getValor(est, c, campoP) !== '' ? Number(getValor(est, c, campoP)) : null;
      const ne = getNE(est, c);
      const on = T.rpEditable(pVal, comp(est, c)?.[campoRP], drafts[k(est, c)]?.[campoRP]) && !ne;
      return { visible: on, valor: on ? getValor(est, c, campoRP) : '' };
    },
    pEnPantalla(est, c) {
      return getNE(est, c) ? '' : getValor(est, c, campoP);
    },
  };
  return api;
}

console.log('\n\x1b[1mA8.1 — un cambio de NE es un cambio\x1b[0m');

prueba('desmarcar un NE ya guardado enciende Guardar', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: null, rp1: null, ne1: true }]);
  igual(s.celdasSucias().size, 0, 'sin tocar nada no hay cambios');
  s.marcarNE(1, 1, false);
  igual(s.celdasSucias().size, 1, 'desmarcar NE sin escribir nota debe contar como cambio');
  igual(s.payloads(), [{ estudiante_id: 1, competencia_numero: 1, ne1: false }],
    'debe mandar ne1=false y el período queda PENDIENTE');
});

prueba('marcar y volver a desmarcar no deja un cambio fantasma', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 70, ne1: false }]);
  s.marcarNE(1, 1, true);
  igual(s.celdasSucias().size, 1, 'marcar NE es un cambio');
  s.marcarNE(1, 1, false);
  igual(s.celdasSucias().size, 0, 'volver al estado original no deberia pedir guardar');
});

prueba('la misma celda con nota Y NE se cuenta UNA vez', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: null, ne1: false }]);
  s.escribir(1, 1, 'p1', '80');
  s.marcarNE(1, 1, true);
  igual(s.celdasSucias().size, 1, 'no debe contarse dos veces');
});

prueba('celdas distintas suman', () => {
  const s = pantalla([
    { est: 1, competencia_numero: 1, p1: null, ne1: false },
    { est: 2, competencia_numero: 1, p1: null, ne1: true },
  ]);
  s.escribir(1, 1, 'p1', '80');
  s.marcarNE(2, 1, false);
  igual(s.celdasSucias().size, 2, 'una nota en una celda y un NE en otra son dos cambios');
});

console.log('\n\x1b[1mA8.2 — marcar NE y arrepentirse no borra nada\x1b[0m');

prueba('LA SECUENCIA: nota existente -> marcar NE -> desmarcar -> nota intacta', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 85, rp1: null, ne1: false }]);
  igual(s.pEnPantalla(1, 1), '85', 'punto de partida');
  s.marcarNE(1, 1, true);
  igual(s.pEnPantalla(1, 1), '', 'con NE la casilla se ve vacia');
  s.marcarNE(1, 1, false);
  igual(s.pEnPantalla(1, 1), '85', 'al desmarcar tiene que reaparecer el 85');
  igual(s.celdasSucias().size, 0, 'y no queda ningun cambio pendiente');
  igual(s.payloads(), [], 'no se manda NADA: nada cambio');
});

prueba('marcar NE de verdad manda NE y NO manda notas en blanco', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 85, rp1: 90, ne1: false }]);
  s.marcarNE(1, 1, true);
  igual(s.payloads(), [{ estudiante_id: 1, competencia_numero: 1, ne1: true }],
    'el backend ya limpia pN/rpN; el frontend no debe fabricar nulls');
});

prueba('escribir una nota sobre un NE manda la nota y retira el NE', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: null, ne1: true }]);
  s.marcarNE(1, 1, false);
  s.escribir(1, 1, 'p1', '70');
  igual(s.payloads(), [{ estudiante_id: 1, competencia_numero: 1, p1: 70, ne1: false }],
    'nota + ne=false');
});

prueba('un borrador escrito antes de marcar NE no se cuela en el envio', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 40, ne1: false }]);
  s.escribir(1, 1, 'p1', '55');
  s.marcarNE(1, 1, true);
  igual(s.payloads(), [{ estudiante_id: 1, competencia_numero: 1, ne1: true }],
    'con NE activo no viaja ninguna nota');
});

prueba('ESTRUCTURAL: marcarNE no toca los borradores de nota', () => {
  const i = PERIODO.indexOf('const marcarNE =');
  cierto(i > 0, 'no encuentro marcarNE');
  const cuerpo = PERIODO.slice(i, PERIODO.indexOf('\n  };', i));
  cierto(!cuerpo.includes('setDrafts('),
    'marcarNE volvio a fabricar borradores de P/RP: eso borra notas al arrepentirse');
});

prueba('ESTRUCTURAL: el contador mira draftsNE', () => {
  const i = PERIODO.indexOf('const celdasSucias');
  cierto(i > 0, 'no encuentro celdasSucias');
  const cuerpo = PERIODO.slice(i, PERIODO.indexOf('const cambios', i));
  cierto(cuerpo.includes('draftsNE'), 'el contador ignora los cambios de NE');
  cierto(PERIODO.includes('const cambios = celdasSucias.size'),
    'el boton Guardar no usa la union');
});

console.log('\n\x1b[1mA8.4 — una RP asentada nunca se oculta\x1b[0m');

prueba('rpEditable: los casos exigidos', () => {
  igual(T.rpEditable(50, null, undefined), true, 'P=50 RP=None -> se puede crear RP');
  igual(T.rpEditable(80, null, undefined), false, 'P=80 RP=None -> no se abre una RP nueva');
  igual(T.rpEditable(80, 50, undefined), true, 'P=80 con RP=50 ya asentada -> visible');
  igual(T.rpEditable(80, 70, undefined), true, 'P corregida a 80 con RP=70 previa -> visible');
  igual(T.rpEditable(null, null, undefined), false, 'sin P no se abre RP');
  igual(T.rpEditable(80, null, '65'), true, 'RP recien escrita en esta sesion -> no desaparece');
  igual(T.rpEditable(80, 0, undefined), true, 'RP=0 es una nota: tampoco se oculta');
});

prueba('P=80 RP=50 ya existente: la pantalla ENSEÑA el 50', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 80, rp1: 50, ne1: false }]);
  const rp = s.rpEnPantalla(1, 1);
  igual(rp.visible, true, 'el RP que gobierna el calculo no puede estar oculto');
  igual(rp.valor, '50', 'y tiene que mostrar su valor');
});

prueba('corregir P de 50 a 80 no esconde el RP=70 que ya estaba', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 50, rp1: 70, ne1: false }]);
  s.escribir(1, 1, 'p1', '80');
  const rp = s.rpEnPantalla(1, 1);
  igual(rp.visible, true, 'el docente debe poder decidir si corrige o limpia ese RP');
  igual(rp.valor, '70', '');
});

prueba('P=80 sin RP: sigue sin poder abrirse una recuperacion', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 80, rp1: null, ne1: false }]);
  igual(s.rpEnPantalla(1, 1).visible, false, 'no se abre una RP que no procede');
});

prueba('NE sigue bloqueando RP aunque exista', () => {
  const s = pantalla([{ est: 1, competencia_numero: 1, p1: 80, rp1: 50, ne1: false }]);
  s.marcarNE(1, 1, true);
  igual(s.rpEnPantalla(1, 1).visible, false, 'NE bloquea P y RP');
});

prueba('el valor efectivo confirma por que importa: P=80 RP=50 vale 50', () => {
  igual(T.valorPeriodoEfectivo({ p1: 80, rp1: 50 }, 1), 50,
    'si vale 50, esconder el 50 es esconder la nota del periodo');
});

prueba('ESTRUCTURAL: las DOS pestanas usan rpEditable, ninguna rpHabilitado', () => {
  for (const [nombre, src] of [['TabNotasPorPeriodo', PERIODO], ['TabNotasPorCompetencia', COMPETENCIA]]) {
    cierto(src.includes('rpEditable('), `${nombre} no usa rpEditable`);
    cierto(!src.includes('rpHabilitado('), `${nombre} sigue decidiendo la vista con rpHabilitado`);
  }
});

console.log('\n' + '='.repeat(74));
if (fallos.length) {
  console.log(`\x1b[91m\x1b[1mPRIMARIA NE/RP BORDES: ${fallos.length} fallo(s) de ${ok + fallos.length}\x1b[0m`);
  for (const [n, e] of fallos) console.log(`  - ${n}: ${e}`);
  process.exit(1);
}
console.log(`PRIMARIA NE/RP BORDES: ${ok}/${ok}`);
console.log('\x1b[92m\x1b[1mTODO VERDE\x1b[0m');
