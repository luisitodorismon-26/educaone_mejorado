/**
 * «Consultar lista» de AvisoEnvio — vigencia de las consultas y formato de la respuesta.
 *
 * Sin framework, como los demás scripts. Transpila `utils/consultaVigente.ts`
 * (la lógica que usa AvisoEnvio) y la prueba con promesas controladas a mano:
 *   · respuestas demoradas y fuera de orden: una consulta vieja nunca pisa a una posterior;
 *   · cambio de aviso / de formulario / desmontaje durante la consulta: su respuesta
 *     o su error no se aplican y su petición se cancela;
 *   · `aplicar` (actualizar la lista de la página) solo corre si la consulta es vigente;
 *   · formato inesperado = fallo de consulta; solo `[]` válido es «lista vacía».
 * Además comprueba en el código que AvisoEnvio y las 5 consultas usan esta lógica.
 *
 *   cd frontend && node scripts/aviso-envio-consultas.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const rama = (rel) => readFileSync(join(aqui, '..', 'src', rel), 'utf8').split(CR).join('');
const js = transformSync(rama('utils/consultaVigente.ts'), { loader: 'ts', format: 'esm' }).code;
const { crearControlConsultas, exigirLista, ConsultaInvalida } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = async (nombre, fn) => {
  try { await fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };
const contiene = (t, s) => { if (!String(t).includes(s)) throw new Error(`no contiene ${JSON.stringify(s)}`); };
const noContiene = (t, s) => { if (String(t).includes(s)) throw new Error(`NO debía contener ${JSON.stringify(s)}`); };

// Promesa que se resuelve o rechaza cuando el test quiere (respuesta «demorada»).
const diferida = () => { let resolver, rechazar; const p = new Promise((a, b) => { resolver = a; rechazar = b; }); return { p, resolver, rechazar }; };
const tick = () => new Promise((r) => setTimeout(r, 0));

/**
 * Reproduce lo que hace AvisoEnvio al terminar una consulta: si ok → aplicar() a la
 * página y mostrar items; si error → estado «fallo». Registra todo para comprobarlo.
 */
const montarAviso = () => {
  const control = crearControlConsultas();
  const v = { estado: 'inicial', items: [], pagina: 'lista-original', aplicaciones: 0 };
  const consultar = (fn) => control.ejecutar(fn, (r) => {
    if (!r.ok) { v.estado = 'fallo'; return; }
    r.valor.aplicar?.(); v.items = r.valor.items; v.estado = 'consultada';
  });
  // El efecto de AvisoEnvio ante un cambio de aviso/contexto o al desmontar:
  const cambiarAviso = () => { control.invalidar(); v.estado = 'inicial'; v.items = []; };
  return { v, consultar, cambiarAviso, desmontar: () => control.invalidar() };
};
const respuesta = (v, etiqueta) => ({ items: [{ id: etiqueta, texto: etiqueta }], aplicar: () => { v.pagina = etiqueta; v.aplicaciones++; } });

console.log('\nVigencia de las consultas');
await prueba('fuera de orden: A (vieja) llega DESPUÉS de B (nueva) → se queda B, A no pisa nada', async () => {
  const { v, consultar } = montarAviso();
  const A = diferida(), B = diferida(); let senalA;
  const pa = consultar((s) => { senalA = s; return A.p; });
  const pb = consultar(() => B.p);
  B.resolver(respuesta(v, 'B')); igual(await pb, true, 'B debía aplicarse');
  A.resolver(respuesta(v, 'A')); igual(await pa, false, 'A no debía aplicarse');
  igual(v.items, [{ id: 'B', texto: 'B' }]); igual(v.pagina, 'B'); igual(v.aplicaciones, 1);
  igual(senalA.aborted, true, 'la petición de A debía cancelarse');
});
await prueba('fuera de orden con error: el ERROR de A llega tarde y no convierte en «fallo» la consulta B', async () => {
  const { v, consultar } = montarAviso();
  const A = diferida(), B = diferida();
  const pa = consultar(() => A.p); const pb = consultar(() => B.p);
  B.resolver(respuesta(v, 'B')); await pb;
  A.rechazar(new Error('respuesta vieja fallida')); igual(await pa, false);
  igual(v.estado, 'consultada'); igual(v.pagina, 'B');
});
await prueba('orden normal: A demorada sin otra consulta → se aplica una sola vez', async () => {
  const { v, consultar } = montarAviso();
  const A = diferida(); const pa = consultar(() => A.p);
  await tick(); igual(v.estado, 'inicial', 'nada antes de responder');
  A.resolver(respuesta(v, 'A')); igual(await pa, true);
  igual(v.pagina, 'A'); igual(v.aplicaciones, 1);
});
await prueba('cambio de aviso DURANTE la consulta → su respuesta no toca el aviso nuevo ni la página', async () => {
  const { v, consultar, cambiarAviso } = montarAviso();
  const A = diferida(); let senal;
  const pa = consultar((s) => { senal = s; return A.p; });
  cambiarAviso();                       // p. ej. un nuevo envío dio otro aviso
  A.resolver(respuesta(v, 'A-vieja')); igual(await pa, false);
  igual(v.estado, 'inicial'); igual(v.items, []); igual(v.pagina, 'lista-original'); igual(senal.aborted, true);
});
await prueba('cambio de aviso durante la consulta → su ERROR tampoco se aplica', async () => {
  const { v, consultar, cambiarAviso } = montarAviso();
  const A = diferida(); const pa = consultar(() => A.p);
  cambiarAviso(); A.rechazar(new Error('cortada')); igual(await pa, false);
  igual(v.estado, 'inicial');
});
await prueba('cambio de contexto del formulario (otro modal / otra nota) → igual que un cambio de aviso', async () => {
  const { v, consultar, cambiarAviso } = montarAviso();
  const A = diferida(); const pa = consultar(() => A.p);
  cambiarAviso(); /* el efecto de AvisoEnvio depende de [fallo, contexto] */
  A.resolver(respuesta(v, 'A')); igual(await pa, false); igual(v.pagina, 'lista-original');
});
await prueba('desmontaje durante la consulta (cerrar modal) → nada se aplica y la petición se cancela', async () => {
  const { v, consultar, desmontar } = montarAviso();
  const A = diferida(); let senal;
  const pa = consultar((s) => { senal = s; return A.p; });
  desmontar(); A.resolver(respuesta(v, 'A')); igual(await pa, false);
  igual(v.pagina, 'lista-original'); igual(v.aplicaciones, 0); igual(senal.aborted, true);
});
await prueba('nueva consulta tras un cambio de aviso → la nueva sí se aplica', async () => {
  const { v, consultar, cambiarAviso } = montarAviso();
  const A = diferida(), B = diferida();
  const pa = consultar(() => A.p); cambiarAviso(); const pb = consultar(() => B.p);
  A.resolver(respuesta(v, 'A')); B.resolver(respuesta(v, 'B'));
  igual([await pa, await pb], [false, true]); igual(v.pagina, 'B');
});

console.log('\nFormato de la respuesta');
for (const [nombre, datos] of [
  ['objeto en vez de lista', { resultado: 'ok' }],
  ['null', null],
  ['texto (p. ej. una página HTML)', '<html>Bad Gateway</html>'],
  ['número', 0],
  ['lista con un elemento que no es objeto', [{ id: 1, titulo: 't', fecha_actualizacion: 'x' }, 'basura']],
  ['lista con un elemento al que le falta un campo', [{ id: 1, titulo: 't' }]],
  ['lista de listas', [[1, 2]]],
]) {
  await prueba(`${nombre} → ConsultaInvalida (nunca lista vacía)`, () => {
    let lanzo = null;
    try { exigirLista(datos, ['id', 'titulo', 'fecha_actualizacion']); } catch (e) { lanzo = e; }
    if (!(lanzo instanceof ConsultaInvalida)) throw new Error('no lanzó ConsultaInvalida');
  });
}
await prueba('lista vacía válida [] → [] (se mostrará «La lista no tiene registros»)', () => igual(exigirLista([], ['id']), []));
await prueba('lista válida → se devuelve tal cual', () => igual(exigirLista([{ id: 1, titulo: null, fecha_actualizacion: 'f' }], ['id', 'titulo', 'fecha_actualizacion']), [{ id: 1, titulo: null, fecha_actualizacion: 'f' }]));
await prueba('formato incorrecto dentro de una consulta → estado «fallo», la página no cambia', async () => {
  const { v, consultar } = montarAviso();
  await consultar(async () => { const lista = exigirLista({ resultado: 'ok' }, ['id']); return { items: lista, aplicar: () => { v.pagina = 'vacía'; } }; });
  igual(v.estado, 'fallo'); igual(v.pagina, 'lista-original');
});
await prueba('lista vacía válida dentro de una consulta → «consultada» con 0 elementos', async () => {
  const { v, consultar } = montarAviso();
  await consultar(async () => ({ items: exigirLista([], ['id']), aplicar: () => { v.pagina = '[]'; } }));
  igual(v.estado, 'consultada'); igual(v.items, []); igual(v.pagina, '[]');
});

console.log('\nUso en el código');
const AVISO = rama('components/AvisoEnvio.tsx');
await prueba('AvisoEnvio invalida al cambiar el aviso o el contexto, y al desmontar', () => {
  contiene(AVISO, "control.current.invalidar();\n    setEstado('inicial'); setItems([]); setHora('');\n  }, [fallo, contexto]);");
  contiene(AVISO, 'useEffect(() => () => control.current.invalidar(), []);');
});
await prueba('AvisoEnvio solo actualiza el aviso y la página desde el callback de una consulta vigente', () => {
  contiene(AVISO, 'await control.current.ejecutar(consultar, (r) => {');
  contiene(AVISO, 'r.valor.aplicar?.();');
});
await prueba('«La lista no tiene registros» solo se pinta con una consulta correcta de 0 elementos', () => {
  const i = AVISO.indexOf("{estado === 'consultada' && (");
  if (i < 0 || AVISO.indexOf('La lista no tiene registros.') < i) throw new Error('el texto de lista vacía no está dentro del estado «consultada»');
});
for (const [rel, fn, ruta] of [
  ['pages/comunicacion/ComunicacionPage.tsx', 'consultarComunicados', "'/comunicados'"],
  ['pages/comunicacion/ComunicacionPage.tsx', 'consultarEnviados', "'/mensajes'"],
  ['pages/psicologia/PsicologiaPage.tsx', 'consultarCasos', "'/psicologia/casos'"],
  ['pages/notas/NotasPage.tsx', 'consultarNotas', "'/notas-personales'"],
  ['pages/dashboard/DashboardPage.tsx', 'consultarNotas', "'/notas-personales'"],
]) {
  await prueba(`${rel} · ${fn}: señal de cancelación, exigirLista y la página solo en «aplicar»`, () => {
    const s = rama(rel); const i = s.indexOf(`const ${fn} = async (signal: AbortSignal)`);
    if (i < 0) throw new Error('no recibe la señal');
    const cuerpo = s.slice(i, s.indexOf('\n  };', i));
    contiene(cuerpo, `api.get(${ruta}, { signal })`);
    contiene(cuerpo, 'exigirLista<');
    noContiene(cuerpo, 'Array.isArray(res.data) ? res.data : []');
    // la única actualización de estado de la página está dentro de `aplicar`
    const sets = cuerpo.match(/set[A-Z]\w*\(/g) || [];
    igual(sets.length, 1, 'una sola actualización de la página');
    contiene(cuerpo, `aplicar: () => ${sets[0]}lista)`);
  });
}

console.log(`\n${ok} pasan, ${fallos.length} fallan`);
process.exit(fallos.length ? 1 : 0);
