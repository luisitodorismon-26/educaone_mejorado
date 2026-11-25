/**
 * FAM-DOC-1 · Vigencia de respuestas DEMORADAS (historial de enlaces y panel).
 *
 * Sin framework ni DOM: compila con esbuild el código REAL de
 *   - components/HistorialEnlacesFamilia.tsx
 *   - pages/calificaciones-general/CompartirFamiliasPanel.tsx
 * y lo ejecuta con un mini-motor de hooks (useState/useRef/useEffect) que anota
 * cada cambio de estado. `api` y `mensajeDeError` se sustituyen por promesas que
 * la prueba resuelve cuando quiere: así se cierra o recarga la lista JUSTO mientras
 * se espera la respuesta o mientras se prepara el mensaje de error, y después se
 * entrega la respuesta vieja.
 *
 *   cd frontend && node scripts/vigencia-respuestas-demoradas.mjs
 *
 * Variables opcionales (para demostrar que la prueba detecta el fallo con el código
 * anterior): EO_HISTORIAL_TSX / EO_PANEL_TSX = ruta a otra versión del archivo.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { build } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const SRC = join(aqui, '..', 'src');
const HISTORIAL = process.env.EO_HISTORIAL_TSX ? resolve(process.env.EO_HISTORIAL_TSX) : join(SRC, 'components', 'HistorialEnlacesFamilia.tsx');
const PANEL = process.env.EO_PANEL_TSX ? resolve(process.env.EO_PANEL_TSX) : join(SRC, 'pages', 'calificaciones-general', 'CompartirFamiliasPanel.tsx');

let ok = 0; const fallos = [];
const prueba = async (nombre, fn) => {
  try { await fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const si = (c, msg) => { if (!c) throw new Error(msg || 'falso'); };

// ───────────── Mini-motor de hooks (un solo componente, render superficial) ─────────────
const MOTOR = `
let actual = null;
export const Fragment = Symbol('Fragment');
export const jsx = (type, props, key) => ({ type, props: props || {}, key });
export const jsxs = jsx;
export const createElement = (type, props, ...children) => ({ type, props: { ...(props || {}), children }, key: props && props.key });
const iguales = (a, b) => a && b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));
export function useState(inicial) {
  const inst = actual, i = inst.i++;
  if (!(i in inst.hooks)) inst.hooks[i] = { valor: typeof inicial === 'function' ? inicial() : inicial };
  const h = inst.hooks[i];
  const set = (v) => {
    const nuevo = typeof v === 'function' ? v(h.valor) : v;
    inst.cambios.push({ hook: i, valor: nuevo, montado: inst.montado });
    if (!inst.montado) return;             // desmontado: React lo ignora (y avisa); aquí se ANOTA
    h.valor = nuevo; inst.sucio = true;
  };
  return [h.valor, set];
}
export function useRef(inicial) {
  const inst = actual, i = inst.i++;
  if (!(i in inst.hooks)) inst.hooks[i] = { current: inicial };
  return inst.hooks[i];
}
export function useEffect(fn, deps) {
  const inst = actual, i = inst.i++;
  const h = inst.hooks[i] || (inst.hooks[i] = {});
  if (!deps || !iguales(h.deps, deps)) { h.deps = deps; inst.pendientes.push(h); h.fn = fn; }
}
export function montar(Comp, props) {
  const inst = { Comp, props, hooks: {}, cambios: [], pendientes: [], montado: true, sucio: true, arbol: null };
  const render = () => {
    let vueltas = 0;
    while (inst.sucio && inst.montado && vueltas++ < 50) {
      inst.sucio = false; inst.i = 0; actual = inst;
      inst.arbol = Comp(inst.props);
      actual = null;
      const pend = inst.pendientes.splice(0);
      for (const h of pend) { if (h.limpiar) h.limpiar(); const r = h.fn(); h.limpiar = typeof r === 'function' ? r : null; }
    }
  };
  inst.render = render;
  inst.actualizar = (props) => { inst.props = { ...inst.props, ...props }; inst.sucio = true; render(); };
  inst.desmontar = () => { for (const h of Object.values(inst.hooks)) if (h && h.limpiar) { h.limpiar(); h.limpiar = null; } inst.montado = false; };
  render();
  return inst;
}
`;

// Promesa controlable.
const diferida = () => { let res, rej; const p = new Promise((a, b) => { res = a; rej = b; }); return { p, res, rej }; };
const esperar = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setImmediate(r)); };

// Simulaciones de api y mensajeDeError: cada llamada queda en una cola que la prueba resuelve.
const COLAS = `
export const llamadas = { get: [], post: [], mensaje: [] };
const diferida = () => { let res, rej; const p = new Promise((a, b) => { res = a; rej = b; }); return { p, res, rej }; };
const api = {
  get: (url, cfg) => { const d = diferida(); llamadas.get.push({ url, cfg, ...d }); return d.p; },
  post: (url, body, cfg) => { const d = diferida(); llamadas.post.push({ url, body, cfg, ...d }); return d.p; },
};
export default api;
export const mensajeDeError = (e, op) => { const d = diferida(); llamadas.mensaje.push({ e, op, ...d }); return d.p; };
`;

const compilar = async (entrada, { historialSuperficial = false } = {}) => {
  // Entrada intermedia: el archivo real + la cola de llamadas simuladas + el motor de hooks.
  const res = await build({
    stdin: {
      contents: `export * from ${JSON.stringify(entrada)};
export { llamadas } from './services/api';
export { montar } from 'motor/jsx-runtime';`,
      resolveDir: SRC, loader: 'js',
    },
    bundle: true, write: false, format: 'esm', platform: 'node',
    jsx: 'automatic', jsxImportSource: 'motor', logLevel: 'silent',
    plugins: [{
      name: 'sustitutos',
      setup(b) {
        b.onResolve({ filter: /^react$|^motor\/jsx-runtime$|^motor\/jsx-dev-runtime$/ }, () => ({ path: 'motor', namespace: 'v' }));
        b.onResolve({ filter: /services\/api$/ }, () => ({ path: 'api', namespace: 'v' }));
        b.onResolve({ filter: /utils\/errorServidor$/ }, () => ({ path: 'api', namespace: 'v' }));
        b.onResolve({ filter: /^lucide-react$/ }, () => ({ path: 'iconos', namespace: 'v' }));
        if (historialSuperficial) b.onResolve({ filter: /components\/HistorialEnlacesFamilia$/ }, () => ({ path: 'historial', namespace: 'v' }));
        b.onLoad({ filter: /.*/, namespace: 'v' }, (a) => ({
          loader: 'js', resolveDir: SRC,
          contents: a.path === 'motor' ? MOTOR
            : a.path === 'api' ? COLAS
            : a.path === 'historial' ? 'export const HistorialEnlacesFamilia = () => null;'
            : 'const I = () => null; export const X=I,Users=I,Mail=I,MessageCircle=I,User=I,ArrowRight=I,Info=I,AlertTriangle=I,RefreshCw=I,Ban=I,Loader2=I,ExternalLink=I;',
        }));
      },
    }],
  });
  return import('data:text/javascript;base64,' + Buffer.from(res.outputFiles[0].text).toString('base64'));
};

// Recorrido del árbol superficial.
const nodos = (n, out = []) => {
  if (!n || typeof n !== 'object') return out;
  if (Array.isArray(n)) { n.forEach(x => nodos(x, out)); return out; }
  out.push(n); nodos(n.props?.children, out); return out;
};
const texto = (n) => typeof n === 'string' || typeof n === 'number' ? String(n) : Array.isArray(n) ? n.map(texto).join('') : n && n.props ? texto(n.props.children) : '';
const boton = (arbol, contiene) => nodos(arbol).find(n => n.type === 'button' && texto(n).includes(contiene));
const errorAxios = (status, error) => ({ isAxiosError: true, response: { status, data: { error } } });
globalThis.window = { confirm: () => true };

// ═════════════════ Historial de enlaces ═════════════════
console.log('\nHistorial de enlaces (componente real)');
const H = await compilar(HISTORIAL);
const L = H.llamadas;
const LISTA = [{ id: 7, ano: '2026-2027', periodo: 1, version: 1, estado: 'activo', fecha_preparado: '2026-11-25T10:00:00', fecha_anulado: null, visitas: 0 }];
// Índices de estado del componente: 0 abierta, 1 lista, 2 error, 3 anulando.
const SE_ERROR = 2, SE_LISTA = 1;
const cambiosDe = (inst, hook, desde) => inst.cambios.slice(desde).filter(c => c.hook === hook).map(c => c.valor);

await prueba('error demorado: se OCULTA la lista mientras se prepara el mensaje → no aparece', async () => {
  L.get.length = L.mensaje.length = 0;
  const c = H.montar(H.HistorialEnlacesFamilia, { estudianteId: 1, nombre: 'Est', abiertaAlInicio: false });
  boton(c.arbol, 'Versiones y enlaces anteriores').props.onClick(); c.render();
  si(L.get.length === 1, 'no pidió la lista');
  L.get[0].rej(errorAxios(500, 'x')); await esperar();
  si(L.mensaje.length === 1, 'no empezó a preparar el mensaje');
  const marca = c.cambios.length;
  boton(c.arbol, 'Ocultar').props.onClick(); c.render();          // cerrar MIENTRAS se prepara el mensaje
  L.mensaje[0].res('ERROR VIEJO'); await esperar(); c.render();
  si(!cambiosDe(c, SE_ERROR, marca).includes('ERROR VIEJO'), 'el error viejo se aplicó tras ocultar');
  si(!cambiosDe(c, SE_LISTA, marca).some(v => Array.isArray(v) && v.length === 0), 'la lista se vació con la respuesta vieja');
});

await prueba('error demorado: se RECARGA la lista mientras se prepara el mensaje → queda la lista nueva, sin error', async () => {
  L.get.length = L.mensaje.length = 0;
  const c = H.montar(H.HistorialEnlacesFamilia, { estudianteId: 1, nombre: 'Est', abiertaAlInicio: true, recarga: 0 });
  L.get[0].rej(errorAxios(500, 'x')); await esperar();            // la carga vieja falla…
  si(L.mensaje.length === 1, 'no empezó a preparar el mensaje');
  c.actualizar({ recarga: 1 });                                     // …y mientras tanto se recarga
  si(L.get.length === 2, 'no hubo recarga');
  L.get[1].res({ data: { versiones: LISTA } }); await esperar(); c.render();
  const marca = c.cambios.length;
  L.mensaje[0].res('ERROR VIEJO'); await esperar(); c.render();     // llega el mensaje viejo
  si(!cambiosDe(c, SE_ERROR, marca).includes('ERROR VIEJO'), 'el error viejo tapó la lista nueva');
  si(!cambiosDe(c, SE_LISTA, marca).length, 'la respuesta vieja cambió la lista');
  si(nodos(c.arbol).some(n => n.type === 'li'), 'no se ve la lista nueva');
  si(!texto(c.arbol).includes('ERROR VIEJO'), 'se ve el error viejo');
});

await prueba('error demorado al ANULAR: se oculta mientras se prepara el mensaje → no aparece', async () => {
  L.get.length = L.post.length = L.mensaje.length = 0;
  const c = H.montar(H.HistorialEnlacesFamilia, { estudianteId: 1, nombre: 'Est', abiertaAlInicio: false });
  boton(c.arbol, 'Versiones y enlaces anteriores').props.onClick(); c.render();
  L.get[0].res({ data: { versiones: LISTA } }); await esperar(); c.render();
  boton(c.arbol, 'Anular enlace').props.onClick(); c.render();
  si(L.post.length === 1, 'no pidió anular');
  L.post[0].rej(errorAxios(500, 'x')); await esperar();
  si(L.mensaje.length === 1, 'no empezó a preparar el mensaje');
  const marca = c.cambios.length;
  boton(c.arbol, 'Ocultar').props.onClick(); c.render();
  L.mensaje[0].res('ERROR VIEJO AL ANULAR'); await esperar(); c.render();
  si(!cambiosDe(c, SE_ERROR, marca).includes('ERROR VIEJO AL ANULAR'), 'el error viejo de anular se aplicó tras ocultar');
});

await prueba('control: sin cerrar ni recargar, el error SÍ se muestra (la prueba no es ciega)', async () => {
  L.get.length = L.mensaje.length = 0;
  const c = H.montar(H.HistorialEnlacesFamilia, { estudianteId: 1, nombre: 'Est', abiertaAlInicio: true });
  L.get[0].rej(errorAxios(500, 'x')); await esperar();
  L.mensaje[0].res('ERROR VIGENTE'); await esperar(); c.render();
  si(texto(c.arbol).includes('ERROR VIGENTE'), 'el error vigente no se muestra');
});

// ═════════════════ Panel: onAnulado tras cerrar ═════════════════
console.log('\nPanel «Compartir reportes» (código real; historial superficial)');
const P = await compilar(PANEL, { historialSuperficial: true });
const LP = P.llamadas;
const FAMILIA = {
  estudiante_id: 10, nombre: 'Est Uno', contactos: [{ rol: 'madre', nombre: 'M', parentesco: null, telefono_whatsapp: '18095550000', telefono_final: '0000', tiene_telefono: true, valido: true }],
  contacto_sugerido: 'madre', notas_pendientes: 0, desactualizado: false,
  documento: { id: 7, estudiante_id: 10, version: 1, estado: 'activo', fecha_preparado: null, preparado_por: null, url: 'https://e.invalid/doc/x', enlace_disponible: true,
    tamano_bytes: 1, visitas: 0, descargas: 0, vistas_previas: 0, primera_visita: null, ultima_visita: null, whatsapp_abierto: 0, ultimo_whatsapp: null },
};
const abrirPanel = async () => {
  LP.post.length = 0;
  const c = P.montar(P.CompartirFamiliasPanel, { cursoId: 1, periodo: 1, estudianteIds: [10], onCerrar: () => {} });
  si(LP.post.length >= 1, 'no pidió preparar');
  LP.post[LP.post.length - 1].res({ data: { colegio: 'C', ano: '2026-2027', estudiantes: [FAMILIA] } }); await esperar(); c.render();
  const hist = nodos(c.arbol).find(n => n.props && typeof n.props.onAnulado === 'function');
  si(hist, 'no se encontró el historial en el panel');
  return { c, onAnulado: hist.props.onAnulado };
};
const ID_FAMILIAS = 0;  // primer useState del panel

await prueba('onAnulado con el panel abierto: quita el documento de la familia', async () => {
  const { c, onAnulado } = await abrirPanel();
  const marca = c.cambios.length;
  onAnulado(7); c.render();
  const ult = cambiosDe(c, ID_FAMILIAS, marca).pop();
  si(Array.isArray(ult) && ult[0].documento === null, 'no se quitó el documento');
});

await prueba('onAnulado que llega DESPUÉS de cerrar el panel (respuesta demorada) → no toca el estado', async () => {
  const { c, onAnulado } = await abrirPanel();
  c.desmontar();                                   // se cierra el panel
  const marca = c.cambios.length;
  onAnulado(7);                                    // llega la anulación demorada
  si(!c.cambios.slice(marca).length, `se cambió el estado tras cerrar (${c.cambios.slice(marca).length} cambio/s)`);
});

console.log(`\n${ok}/${ok + fallos.length}`);
process.exit(fallos.length ? 1 : 0);
