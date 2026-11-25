/**
 * FAM-DOC-1 · Compartir el Reporte del Período con las familias (frontend).
 *
 * Sin framework, como los demás scripts:
 *   1. Transpila `utils/compartirFamilias.ts` y prueba sus reglas: contacto elegido
 *      solo si tiene teléfono utilizable, mensaje con el enlace YA incluido y sin
 *      notas, enlace de WhatsApp al número elegido, estados que nunca dicen
 *      «enviado/entregado/leído», recorrido «Siguiente familia».
 *   2. Comprueba en la pantalla y el panel que se conservan las tres descargas,
 *      que no hay envío automático (solo un enlace que abre WhatsApp), que el
 *      correo del estudiante no se usa y que Correo queda como «Próximamente».
 *
 *   cd frontend && node scripts/compartir-familias.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const leer = (rel) => readFileSync(join(aqui, '..', 'src', rel), 'utf8').split(CR).join('');
const js = transformSync(leer('utils/compartirFamilias.ts'), { loader: 'ts', format: 'esm' }).code;
const F = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = (nombre, fn) => {
  try { fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`); };
const si = (c, msg) => { if (!c) throw new Error(msg || 'falso'); };
const contiene = (t, s) => { if (!String(t).includes(s)) throw new Error(`no contiene ${JSON.stringify(s)}`); };
const noContiene = (t, s) => { if (String(t).includes(s)) throw new Error(`NO debía contener ${JSON.stringify(s)}`); };

// Contactos sintéticos.
const c = (rol, nombre, tel, extra = {}) => ({ rol, nombre, parentesco: null, telefono_whatsapp: tel, telefono_final: tel ? tel.slice(-4) : null,
  tiene_telefono: !!tel, valido: !!tel, ...extra });
const doc = (extra = {}) => ({ id: 1, estudiante_id: 10, version: 1, estado: 'activo', fecha_preparado: '2026-11-25T10:00:00', preparado_por: 'D',
  url: 'https://ejemplo.invalid/doc/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA', tamano_bytes: 2500, visitas: 0, descargas: 0, vistas_previas: 0,
  primera_visita: null, ultima_visita: null, whatsapp_abierto: 0, ultimo_whatsapp: null, ...extra });
const fam = (extra = {}) => ({ estudiante_id: 10, nombre: 'Ana Pérez', contactos: [], contacto_sugerido: null, notas_pendientes: 0,
  documento: doc(), desactualizado: false, ...extra });

console.log('\n1. Contacto elegido');
const tutorSinTel = c('tutor', 'Abuela Rosa', null, { tiene_telefono: false });
const padre = c('padre', 'Ramón Santos', '18095553333');
const madre = c('madre', 'Lucía Gómez', '18095552048');
prueba('sugerido = el que indica el servidor (con teléfono)', () =>
  igual(F.contactoElegido(fam({ contactos: [tutorSinTel, padre, madre], contacto_sugerido: 'padre' }))?.rol, 'padre'));
prueba('elegir al tutor SIN teléfono no tiene efecto (queda el sugerido)', () =>
  igual(F.contactoElegido(fam({ contactos: [tutorSinTel, padre, madre], contacto_sugerido: 'padre' }), 'tutor')?.rol, 'padre'));
prueba('elegir a la madre (con teléfono) sí cambia', () =>
  igual(F.contactoElegido(fam({ contactos: [tutorSinTel, padre, madre], contacto_sugerido: 'padre' }), 'madre')?.rol, 'madre'));
prueba('sin teléfonos utilizables → ninguno', () =>
  igual(F.contactoElegido(fam({ contactos: [tutorSinTel, c('padre', 'X', null, { tiene_telefono: true, telefono_final: '5512' })] })), null));
prueba('etiqueta oculta el número: «Madre · •••• 2048»', () => igual(F.etiquetaContacto(madre), 'Madre · •••• 2048'));
prueba('etiqueta del tutor sin teléfono lo dice', () => igual(F.etiquetaContacto(tutorSinTel), 'Tutor · sin teléfono'));

console.log('\n2. Mensaje y enlace de WhatsApp');
const url = 'https://ejemplo.invalid/doc/Abc_def-123AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
const msg = F.mensajeFamilia({ colegio: 'Colegio Sintético', periodo: 1, ano: '2026-2027', estudiante: 'Ana Pérez', url });
prueba('el mensaje lleva el enlace individual completo', () => contiene(msg, url));
prueba('menciona el período y el estudiante, sin notas', () => { contiene(msg, 'primer período (2026-2027)'); contiene(msg, 'Ana Pérez'); si(!/\b\d{2}\b(?!\d)/.test(msg.replace(url, '').replace('2026-2027', '')), 'parece llevar una nota'); });
prueba('avisa que quien reciba el enlace podrá abrirlo', () => contiene(msg, 'cualquier persona que lo reciba'));
const wa = F.enlaceWhatsApp('1 (809) 555-2048', msg);
prueba('wa.me al número del contacto, solo dígitos', () => si(wa.startsWith('https://wa.me/18095552048?text='), wa.slice(0, 40)));
prueba('el texto viaja codificado y se recupera idéntico (con & # y tildes)', () => {
  const m2 = F.mensajeFamilia({ colegio: 'Colegio A & B #1', periodo: 2, ano: '2026-2027', estudiante: 'José Núñez', url });
  igual(new URL(F.enlaceWhatsApp('18095552048', m2)).searchParams.get('text'), m2);
});

console.log('\n3. Estados: lo que el sistema sabe');
const prohibidas = /enviado|entregado|le[ií]do/i;
const casos = [
  fam({ contactos: [] }),
  fam({ contactos: [madre], documento: null }),
  fam({ contactos: [madre] }),
  fam({ contactos: [madre], desactualizado: true }),
  fam({ contactos: [madre], documento: doc({ whatsapp_abierto: 2 }) }),
];
prueba('ningún estado dice enviado, entregado ni leído', () => casos.forEach(f => si(!prohibidas.test(F.estadoFamilia(f).texto), F.estadoFamilia(f).texto)));
prueba('WhatsApp abierto lo aclara: «no confirma el envío»', () => contiene(F.estadoFamilia(casos[4]).texto, 'no confirma el envío'));
prueba('desactualizado tiene prioridad sobre «preparado»', () => igual(F.estadoFamilia(casos[3]).tipo, 'desactualizado'));
prueba('visitas: no confirman lectura', () => { contiene(F.textoVisitas(doc({ visitas: 2, descargas: 1 })), 'no confirma que se haya leído'); contiene(F.textoVisitas(doc({ visitas: 3 })), '3 veces'); });

console.log('\n4. Siguiente familia');
const lista = [fam({ contactos: [madre] }), fam({ contactos: [] }), fam({ contactos: [madre], documento: null }), fam({ contactos: [padre] })];
prueba('salta familias sin teléfono o sin documento', () => igual(F.siguienteFamilia(lista, 0), 3));
prueba('es cíclico', () => igual(F.siguienteFamilia(lista, 3), 0));
prueba('sin ninguna disponible → -1', () => igual(F.siguienteFamilia([fam({ contactos: [] })], 0), -1));

console.log('\n5. Pantalla y panel');
const pagina = leer('pages/calificaciones-general/CalificacionesGeneralPage.tsx');
const panel = leer('pages/calificaciones-general/CompartirFamiliasPanel.tsx');
prueba('se conservan las tres descargas (tabla general, curso, individual)', () => {
  contiene(pagina, '/calificaciones/por-periodo/pdf?curso_id=');
  contiene(pagina, '/calificaciones-secundaria/reporte-padres/curso/${cursoId}/pdf?periodo=${periodo}`');
  contiene(pagina, '/calificaciones-secundaria/reporte-padres/curso/${cursoId}/pdf?periodo=${periodo}&estudiante_id=${estId}');
  contiene(pagina, 'Tabla general PDF'); contiene(pagina, 'Reportes del curso PDF');
});
prueba('se conserva la vista por competencia', () => contiene(pagina, "/calificaciones-secundaria/curso/${cursoId}/periodo/${periodo}/competencias"));
prueba('selección individual y de todo el curso', () => { contiene(pagina, 'Seleccionar todo el curso'); contiene(pagina, 'aria-label={`Seleccionar a ${est.nombre}`}'); });
prueba('pendientes informativos: no deshabilitan PDF ni compartir', () => {
  si(!/disabled=\{[^}]*pendientes/i.test(pagina), 'un botón se deshabilita por notas pendientes');
});
prueba('WhatsApp se abre con un enlace (sin envío automático ni bucles de apertura)', () => {
  contiene(panel, 'href={hrefWhatsApp}'); contiene(panel, 'target="_blank"');
  noContiene(panel, 'window.open'); noContiene(panel, 'setInterval');
  si(!/for\s*\([^)]*\)\s*\{[^}]*wa\.me/s.test(panel), 'hay un bucle que abre WhatsApp');
});
prueba('el panel nunca muestra «enviado», «entregado» ni «leído» como estado', () => {
  const textos = (panel.match(/>[^<>{}]*</g) || []).join(' ');
  si(!/\b(enviado|entregado|le[ií]do)\b/i.test(textos.replace(/no confirma que el mensaje se envió/g, '')), 'texto de estado prohibido');
});
prueba('Correo queda «Próximamente» y deshabilitado; no se usa el correo del estudiante', () => {
  contiene(panel, 'Correo · Próximamente'); si(/<button disabled[^>]*>\s*<Mail/.test(panel), 'botón de correo no deshabilitado');
  noContiene(panel, '.email'); noContiene(pagina, '.email');
});
prueba('el panel avisa: solo pulsar Enviar, sin copiar el enlace', () => contiene(panel, 'No necesitas copiar ni pegar el enlace'));
prueba('doble clic: preparar/versión/anular protegidos con useRef', () => {
  contiene(panel, 'if (enCurso.current) return;'); contiene(panel, 'const g = generacion.current;');
  si((panel.match(/if \(![a-z?.]+ \|\| enCurso\.current\) return;|if \(!familia \|\| enCurso\.current\) return;/g) || []).length >= 2, 'versión/anular sin corte');
});
prueba('Primaria: compartir deshabilitado con explicación (no hay datos que compartir)', () => { contiene(pagina, 'disabled={esPrimaria'); contiene(pagina, 'todavía no incluye las calificaciones de Primaria'); });

console.log('\n6. Correcciones de la revisión');
prueba('cambiar curso o período limpia la tabla y cierra el panel hasta «Ver notas»', () => {
  contiene(pagina, "onChange={e => { setCursoId(Number(e.target.value)); limpiarConsulta(); }}");
  contiene(pagina, "onChange={e => { setPeriodo(Number(e.target.value)); limpiarConsulta(); }}");
  const i = pagina.indexOf('const limpiarConsulta = () => {'); const cuerpo = pagina.slice(i, pagina.indexOf('};', i));
  ['setData(null)', 'setCompData(null)', 'setSeleccion(new Set())', 'setPanel(null)', 'setConsulta(null)', 'consultaVigente.current += 1']
    .forEach(x => contiene(cuerpo, x));
});
prueba('una carga de notas que llega después de cambiar un filtro se descarta', () => {
  const i = pagina.indexOf('const cargar = async () => {'); const cuerpo = pagina.slice(i, pagina.indexOf('const descargarBlob', i));
  contiene(cuerpo, 'const id = ++consultaVigente.current;');
  si((cuerpo.match(/if \(id !== consultaVigente\.current\) return;/g) || []).length === 2, 'faltan guardas en las dos vistas');
});
prueba('el panel comparte el curso y período de la consulta, no los selectores', () => {
  contiene(pagina, 'cursoId={consulta.cursoId} periodo={consulta.periodo}');
});
prueba('cerrar el panel: no pide más lotes, cancela la petición y descarta respuestas tardías', () => {
  contiene(panel, 'if (generacion.current === g) generacion.current += 1;');
  contiene(panel, 'cancelar.current?.abort();');
  contiene(panel, "if (!vigente(g)) return;                         // panel cerrado: no pedir más lotes");
  contiene(panel, "if (!vigente(g)) return;                         // respuesta tardía: se descarta");
  contiene(panel, '{ signal: ctrl.signal }');
  contiene(panel, '.then(res => vigente(g) && setFamilias(prev');
  noContiene(panel, 'vivo.current');
});
prueba('lista de versiones con fecha y «Anular enlace» (también años anteriores); anular no borra el PDF', () => {
  contiene(panel, '/documentos-familia/estudiante/${estId}/versiones');
  contiene(panel, 'Versiones y enlaces anteriores');
  contiene(panel, "{v.estado !== 'anulado' && (");
  contiene(panel, 'Preparado el {fecha(v.fecha_preparado)}');
  contiene(panel, 'Anular no borra el PDF');
  noContiene(panel, 'api.delete');
});
prueba('enlace con clave retirada: se avisa y se ofrece versión nueva', () => {
  contiene(panel, 'enlace_disponible === false'); contiene(panel, 'ya se retiró');
});

console.log(`\n${ok}/${ok + fallos.length}`);
process.exit(fallos.length ? 1 : 0);
