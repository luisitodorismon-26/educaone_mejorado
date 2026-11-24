/**
 * COM-DUP-1 · clave de envío al CREAR comunicados (frontend).
 *
 * Sin framework, como los demás scripts:
 *   1. Transpila `utils/envioComunicado.ts` y prueba sus reglas: reintento con la
 *      misma clave, decisión explícita ante otro contenido o un conflicto, rechazo de
 *      un envío nuevo frente a rechazo de un REINTENTO (el anterior sigue pendiente),
 *      publicaciones intencionales con claves nuevas y referencias anotadas.
 *   2. Comprueba en ComunicacionPage.tsx que solo la CREACIÓN lleva clave, que
 *      editar no cambia, que hay corte inmediato del doble clic, que los campos se
 *      bloquean durante el envío y que no hay reenvíos automáticos.
 *
 *   cd frontend && node scripts/comunicado-envio-pendiente.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const rama = (rel) => readFileSync(join(aqui, '..', 'src', rel), 'utf8').split(CR).join('');
const js = transformSync(rama('utils/envioComunicado.ts'), { loader: 'ts', format: 'esm' }).code;
const E = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };
const contiene = (t, s) => { if (!String(t).includes(s)) throw new Error(`no contiene ${JSON.stringify(s)}`); };
const noContiene = (t, s) => { if (String(t).includes(s)) throw new Error(`NO debía contener ${JSON.stringify(s)}`); };

let n = 0; const clave = () => `clave-${++n}-sintetica`;
const C1 = { titulo: 'Reunión', contenido: 'Viernes 8:00', alcance: 'general', imagen: '' };
const C2 = { ...C1, contenido: 'Viernes 9:00' };
const pend = (c, estado, k = 'clave-previa-1') => ({ clave: k, huella: E.huellaContenido(c), contenido: c, estado, hora: '10:00' });
const enviado = (c, k) => ({ clave: k, huella: E.huellaContenido(c), contenido: c, hora: '10:05' });

console.log('\ndecidirEnvio');
prueba('sin pendiente → envío nuevo con clave nueva', () => {
  const d = E.decidirEnvio(null, C1, clave); igual([d.accion, d.reintento], ['enviar', false]); contiene(d.clave, 'clave-');
});
prueba('incierto + MISMO contenido → reintento con la MISMA clave', () =>
  igual(E.decidirEnvio(pend(C1, 'incierto'), C1, clave), { accion: 'enviar', clave: 'clave-previa-1', reintento: true }));
prueba('incierto + OTRO contenido → decisión explícita, no se envía', () =>
  igual(E.decidirEnvio(pend(C1, 'incierto'), C2, clave), { accion: 'decidir', motivo: 'contenido_distinto' }));
prueba('cambiar solo el alcance o la imagen también es otro contenido', () => {
  igual(E.decidirEnvio(pend(C1, 'incierto'), { ...C1, alcance: 'primaria' }, clave).accion, 'decidir');
  igual(E.decidirEnvio(pend(C1, 'incierto'), { ...C1, imagen: 'data:x' }, clave).accion, 'decidir');
});
prueba('conflicto (409) + mismo contenido → decisión explícita (la clave NO se reutiliza a ciegas)', () =>
  igual(E.decidirEnvio(pend(C1, 'conflicto'), C1, clave), { accion: 'decidir', motivo: 'conflicto' }));
prueba('conflicto + otro contenido → decisión explícita', () =>
  igual(E.decidirEnvio(pend(C1, 'conflicto'), C2, clave).accion, 'decidir'));

console.log('\ntrasRespuesta');
prueba('confirmado (201 o 200 de reintento) → la clave se descarta', () =>
  igual(E.trasRespuesta(pend(C1, 'incierto'), enviado(C1, 'clave-previa-1'), 'confirmado'), { pendiente: null, reintentoRechazado: false }));
prueba('incierto → pendiente con la misma clave', () => {
  const t = E.trasRespuesta(null, enviado(C1, 'k-1-sintetica'), 'incierto');
  igual([t.pendiente.estado, t.pendiente.clave], ['incierto', 'k-1-sintetica']);
});
prueba('409 de clave → conflicto CONSERVADO con su clave', () => {
  const t = E.trasRespuesta(null, enviado(C1, 'k-2-sintetica'), 'conflicto');
  igual([t.pendiente.estado, t.pendiente.clave], ['conflicto', 'k-2-sintetica']);
});
prueba('rechazo 4xx de un envío NUEVO → nada guardado, no queda pendiente', () =>
  igual(E.trasRespuesta(null, enviado(C1, 'k-3-sintetica'), 'rechazo'), { pendiente: null, reintentoRechazado: false }));
prueba('rechazo 4xx de un REINTENTO (p. ej. permisos revocados) → el envío anterior SIGUE pendiente', () => {
  const antes = pend(C1, 'incierto');
  const t = E.trasRespuesta(antes, enviado(C1, antes.clave), 'rechazo');
  igual(t.pendiente, antes); igual(t.reintentoRechazado, true);
});
prueba('rechazo tras un conflicto → el conflicto se conserva', () => {
  const antes = pend(C1, 'conflicto');
  igual(E.trasRespuesta(antes, enviado(C1, 'k-nueva'), 'rechazo').pendiente, antes);
});

console.log('\nPublicaciones intencionales y referencias');
prueba('tras confirmar, publicar lo MISMO otra vez lleva clave NUEVA (dos publicaciones intencionales)', () => {
  const t = E.trasRespuesta(null, enviado(C1, 'k-a'), 'confirmado');
  const d = E.decidirEnvio(t.pendiente, C1, clave); igual(d.accion, 'enviar'); igual(d.reintento, false);
  if (d.clave === 'k-a') throw new Error('reutilizó la clave de una publicación confirmada');
});
prueba('«Publicar como nuevo» anota la referencia anterior (no la borra en silencio), sin duplicarla', () => {
  const p = pend(C1, 'incierto');
  const a1 = E.anotarReferencia([], p); const a2 = E.anotarReferencia(a1, p);
  igual(a1, [{ clave: p.clave, titulo: 'Reunión', hora: '10:00', estado: 'incierto' }]); igual(a2.length, 1);
});
prueba('claves con formato aceptado por el servidor ([A-Za-z0-9-]{8,64})', () => {
  for (let i = 0; i < 50; i++) { const k = E.nuevaClaveEnvio(); if (!/^[A-Za-z0-9-]{8,64}$/.test(k)) throw new Error(k); }
});

console.log('\nComunicacionPage.tsx');
const COM = rama('pages/comunicacion/ComunicacionPage.tsx');
const cuerpoDe = (ini) => { const i = COM.indexOf(ini); return COM.slice(i, COM.indexOf('\n  };', i)); };
prueba('solo la CREACIÓN envía client_request_id; editar (PUT) sigue igual y sin clave', () => {
  const g = cuerpoDe('const guardarComunicado = async');
  contiene(g, "await api.put(`/comunicados/${selectedItem.id}`, { titulo, contenido, imagen, tipo: alcance });");
  noContiene(g, 'client_request_id');
  contiene(cuerpoDe('const publicarComunicado = async'), 'client_request_id: decision.clave');
  igual((COM.match(/client_request_id/g) || []).length, 1, 'una sola petición con clave');
});
prueba('mensajes y respuestas no llevan clave (fuera de alcance)', () => {
  noContiene(cuerpoDe('const enviarMensaje = async'), 'client_request_id');
  noContiene(cuerpoDe('const responderMensaje = async'), 'client_request_id');
});
prueba('doble clic: corte inmediato con ref ANTES de cualquier otra cosa', () => {
  igual(cuerpoDe('const publicarComunicado = async').split('\n')[1].trim(), 'if (enviandoComunicadoRef.current) return;          // doble clic: corte inmediato');
});
prueba('sin decisión explícita no se envía (accion «decidir» retorna antes del POST)', () => {
  const p = cuerpoDe('const publicarComunicado = async');
  if (p.indexOf("decision.accion === 'decidir'") > p.indexOf("api.post('/comunicados'")) throw new Error('el POST va antes');
});
prueba('el 409 de clave se trata como CONFLICTO (no como rechazo que descarta la clave)', () =>
  contiene(cuerpoDe('const publicarComunicado = async'), "datos.motivo === 'clave_con_otro_contenido'"));
prueba('«Publicar como nuevo» y «descartar» piden confirmación expresa', () => {
  contiene(cuerpoDe('const publicarComoNuevo = '), 'if (!confirm(aviso)) return;');
  contiene(cuerpoDe('const descartarReferencia = '), 'if (!confirm(');
});
prueba('los campos del comunicado se bloquean durante el envío', () =>
  igual((COM.slice(COM.indexOf('{/* Comunicado */}')).match(/disabled=\{saving\}/g) || []).length >= 6, true));
prueba('sin reenvíos automáticos (ningún POST dentro de setTimeout)', () => {
  if (/setTimeout\([^)]*api\.post/s.test(COM)) throw new Error('posible reenvío temporizado');
});
prueba('el envío pendiente vive en la PÁGINA (no se borra al cerrar el modal) y no en localStorage', () => {
  noContiene(cuerpoDe('const resetForm = '), 'setEnvioPendiente');
  noContiene(COM, 'localStorage');
});
prueba('el aviso documenta que recargar pierde la referencia', () => contiene(COM, 'Si recarga la página, esa referencia se pierde'));

console.log(`\n${ok} pasan, ${fallos.length} fallan`);
process.exit(fallos.length ? 1 : 0);
