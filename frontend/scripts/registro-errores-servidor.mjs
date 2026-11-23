/**
 * REGISTRO ESCOLAR — la pantalla debe mostrar la explicación del servidor.
 *
 * Misma técnica que los demás scripts: sin framework. Transpila con el esbuild
 * de Vite el PROPIO `src/utils/errorServidor.ts` y le pasa errores con la forma
 * exacta que produce axios (incluido el Blob cuando se pidió un PDF).
 * Los cuerpos imitan los que devuelve hoy el backend (app.py / registro_*.py).
 *
 *   cd frontend && node scripts/registro-errores-servidor.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { transformSync } from 'esbuild';

const aqui = dirname(fileURLToPath(import.meta.url));
const CR = String.fromCharCode(13);
const leer = (...p) => readFileSync(join(aqui, '..', 'src', ...p), 'utf8').split(CR).join('');

const js = transformSync(leer('utils', 'errorServidor.ts'), { loader: 'ts', format: 'esm' }).code;
const { mensajeDeError, textoSeguro, AVISO_RESUMIDO } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));

let ok = 0; const fallos = [];
const prueba = async (nombre, fn) => {
  try { await fn(); ok++; console.log(`  \x1b[92mPASA\x1b[0m  ${nombre}`); }
  catch (e) { fallos.push([nombre, e.message]); console.log(`  \x1b[91mFALLA\x1b[0m ${nombre}\n        ${e.message}`); }
};
const igual = (a, b, msg = '') => {
  if (a !== b) throw new Error(`${msg}\n        esperado ${JSON.stringify(b)}\n        obtenido ${JSON.stringify(a)}`);
};
const contiene = (t, sub) => { if (!t.includes(sub)) throw new Error(`no contiene ${JSON.stringify(sub)} en ${JSON.stringify(t)}`); };
const noContiene = (t, sub) => { if (t.includes(sub)) throw new Error(`NO debía contener ${JSON.stringify(sub)} en ${JSON.stringify(t)}`); };

// Forma de los errores de axios
const conRespuesta = (status, data) => ({ response: { status, data }, request: {} });
const blobJSON = (o) => new Blob([JSON.stringify(o)], { type: 'application/json' });
const ACC = {
  DIAS_EXCEDEN_PLANTILLA: 'Revise los días de clase y la asistencia de ese mes. El Registro no se imprime hasta que quepan en la hoja.',
};
const LECTURA = { porDefecto: 'El servidor no generó la vista previa.', accionesPorMotivo: ACC };
const GUARDADO = { porDefecto: 'No se pudo guardar.', operacion: 'guardado' };

const MSG_422 = 'Formación Humana — noviembre: hay 11 días de clase y la hoja oficial solo tiene 10 columnas. No se imprime un Registro que esconda días.';

console.log('\nFormatos del servidor');
await prueba('422 en Blob con `mensaje` (PDF esperado): se muestra la causa y la acción', async () => {
  const m = await mensajeDeError(conRespuesta(422, blobJSON({ motivo: 'DIAS_EXCEDEN_PLANTILLA', mensaje: MSG_422, dias: [1, 2], columnas: 10 })), LECTURA);
  igual(m, `${MSG_422}\nQué hacer: ${ACC.DIAS_EXCEDEN_PLANTILLA}`);
});
await prueba('ANTES fallaba: el código viejo solo leía `error` y mostraba el genérico', async () => {
  const parsed = { motivo: 'DIAS_EXCEDEN_PLANTILLA', mensaje: MSG_422 };
  igual(parsed.error || 'Error al generar la vista previa', 'Error al generar la vista previa');
});
await prueba('422 como objeto (sin Blob) con `mensaje`', async () => {
  igual(await mensajeDeError(conRespuesta(422, { mensaje: MSG_422 }), LECTURA), MSG_422);
});
await prueba('400 con `error`, `detalle: string[]` y `sugerencia` (validación del oficial)', async () => {
  const m = await mensajeDeError(conRespuesta(400, blobJSON({
    error: 'Datos incompletos o inconsistentes',
    detalle: ['Lengua Española: faltan 3 calificaciones', 'Matemática: sin docente asignado'],
    warnings: [], sugerencia: 'Corrija los errores antes de generar el registro.',
  })), LECTURA);
  igual(m, 'Datos incompletos o inconsistentes:\n• Lengua Española: faltan 3 calificaciones\n• Matemática: sin docente asignado\nQué hacer: Corrija los errores antes de generar el registro.');
});
await prueba('409 de advertencias: se descarta la sugerencia técnica «?force=true»', async () => {
  const m = await mensajeDeError(conRespuesta(409, blobJSON({
    error: 'Advertencias detectadas', detalle: ['Hay 2 estudiantes sin fecha de nacimiento'],
    sugerencia: 'Use ?force=true para ignorar advertencias.', validacion: { valid: true },
  })), LECTURA);
  igual(m, 'Advertencias detectadas:\n• Hay 2 estudiantes sin fecha de nacimiento');
});
await prueba('`detail` de FastAPI (texto)', async () => {
  igual(await mensajeDeError(conRespuesta(403, { detail: 'Solo puedes ver el borrador de tus cursos asignados' }), LECTURA),
    'Solo puedes ver el borrador de tus cursos asignados');
});
await prueba('`detail` como lista de objetos (validación de FastAPI): nunca [object Object]', async () => {
  const m = await mensajeDeError(conRespuesta(422, { detail: [{ loc: ['query', 'x'], msg: 'field required', type: 'missing' }] }), LECTURA);
  igual(m, LECTURA.porDefecto);
});
await prueba('`mensaje` con tipo incorrecto (objeto) cae a `error` si es texto', async () => {
  igual(await mensajeDeError(conRespuesta(400, { mensaje: { a: 1 }, error: 'El curso no tiene grado asignado' }), LECTURA),
    'El curso no tiene grado asignado');
});
await prueba('prioridad: `mensaje` antes que `error` antes que `detail`', async () => {
  igual(await mensajeDeError(conRespuesta(422, { detail: 'c', error: 'b', mensaje: 'a válida' }), LECTURA), 'a válida');
});
await prueba('`detalle` mezcla textos y objetos: solo se listan los textos', async () => {
  const m = await mensajeDeError(conRespuesta(400, { error: 'Datos incompletos', detalle: ['Falta tanda', { x: 1 }, 7, 'Falta sección'] }), LECTURA);
  igual(m, 'Datos incompletos:\n• Falta tanda\n• Falta sección');
});
await prueba('más de 6 causas: se resumen las restantes', async () => {
  const m = await mensajeDeError(conRespuesta(400, { error: 'Datos incompletos', detalle: Array.from({ length: 9 }, (_, i) => `Causa ${i + 1}`) }), LECTURA);
  contiene(m, '• Causa 6'); noContiene(m, 'Causa 7'); contiene(m, '… y 3 más.');
});
await prueba('404 sin cuerpo: texto propio del 404', async () => {
  contiene(await mensajeDeError(conRespuesta(404, ''), LECTURA), 'No se encontró lo solicitado');
});

console.log('\nDetalles internos que no se muestran');
const MSG_500 = 'El servidor tuvo un problema al procesar la solicitud (error 500). Inténtelo de nuevo; si se repite, avise a soporte técnico.';
await prueba('500 con `detalle: str(e)` con SQL: mensaje controlado por el frontend, nada del cuerpo', async () => {
  const m = await mensajeDeError(conRespuesta(500, blobJSON({
    error: 'Error generando preview',
    detalle: '(sqlite3.OperationalError) no such column: x [SQL: SELECT * FROM asistencias WHERE ...]',
  })), LECTURA);
  igual(m, MSG_500);
});
await prueba('mensaje con traza de Python: se descarta', async () => {
  const m = await mensajeDeError(conRespuesta(400, { error: 'Traceback (most recent call last):\n  File "app.py", line 3' }), LECTURA);
  igual(m, LECTURA.porDefecto);
});
await prueba('mensaje con un token JWT o la palabra password: se descarta', async () => {
  igual(await mensajeDeError(conRespuesta(400, { error: 'Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijk' }), LECTURA), LECTURA.porDefecto);
  igual(await mensajeDeError(conRespuesta(400, { mensaje: 'password=admin123 inválida' }), LECTURA), LECTURA.porDefecto);
});
await prueba('409 de catálogo con `detalle` textual interno: se muestra `mensaje`, no `detalle`', async () => {
  const m = await mensajeDeError(conRespuesta(409, { motivo: 'catalogo_clave_invalida', detalle: "KeyError: 'LEN-2-C1'", mensaje: 'Un indicador guardado ya no corresponde al catálogo oficial. No se imprime nada inventado: contacte a soporte técnico.' }), LECTURA);
  noContiene(m, 'KeyError'); contiene(m, 'contacte a soporte técnico');
});
await prueba('página HTML de error dentro del Blob (500): genérico, sin HTML', async () => {
  const m = await mensajeDeError(conRespuesta(500, new Blob(['<html><body>Internal Server Error</body></html>'])), LECTURA);
  igual(m, MSG_500);
});
await prueba('Blob con JSON roto: mensaje por defecto', async () => {
  igual(await mensajeDeError(conRespuesta(422, new Blob(['{"mensaje": "sin cerrar'])), LECTURA), LECTURA.porDefecto);
});
await prueba('texto absurdo (más de 20 000 caracteres): se descarta', async () => {
  igual(await mensajeDeError(conRespuesta(400, { error: 'palabra '.repeat(3000) }), LECTURA), LECTURA.porDefecto);
});
await prueba('textoSeguro rechaza no-textos y textos sin letras', async () => {
  igual(textoSeguro(null), null); igual(textoSeguro(42), null); igual(textoSeguro({}), null); igual(textoSeguro('  ...  '), null);
});

console.log('\nTextos largos: se resumen, no se pierden');
const NOTAS_5 = 'No se puede emitir el Registro oficial de 3ro A: faltan calificaciones de 5 estudiantes. '
  + 'Estudiante Ficticio Uno (n.º 3): Lengua Española P2 y P3, Matemática P3, Ciencias de la Naturaleza P3. '
  + 'Estudiante Ficticio Dos (n.º 7): Ciencias Sociales P1 a P4 y Educación Artística P4. '
  + 'Estudiante Ficticio Tres (n.º 12): Formación Integral Humana y Religiosa P2, Educación Física P2 y P3. '
  + 'Estudiante Ficticio Cuatro (n.º 18): Lengua Española P4, Matemática P4, Ciencias Sociales P4, Ciencias de la Naturaleza P4. '
  + 'Estudiante Ficticio Cinco (n.º 25): todas las asignaturas del período 4. '
  + 'Complete esas calificaciones en la pantalla de Calificaciones y vuelva a diagnosticar el curso.';
await prueba('notas faltantes de 5 estudiantes (> 600 caracteres): se conserva la causa con aviso de resumen', async () => {
  if (NOTAS_5.length <= 600) throw new Error('el mensaje de prueba debe superar 600 caracteres: ' + NOTAS_5.length);
  const m = await mensajeDeError(conRespuesta(400, blobJSON({ error: NOTAS_5 })), LECTURA);
  contiene(m, 'faltan calificaciones de 5 estudiantes');
  contiene(m, 'Estudiante Ficticio Uno (n.º 3): Lengua Española P2 y P3');
  contiene(m, 'Estudiante Ficticio Cuatro');
  if (!m.endsWith(AVISO_RESUMIDO)) throw new Error('falta el aviso visible de resumen: ' + JSON.stringify(m.slice(-80)));
  if (m.length > 600 + AVISO_RESUMIDO.length) throw new Error('demasiado largo: ' + m.length);
  if (!NOTAS_5.startsWith(m.slice(0, m.length - AVISO_RESUMIDO.length))) throw new Error('el resumen debe ser el comienzo exacto del texto');
});
await prueba('texto largo con un dato interno AL FINAL: se descarta entero (protección antes de resumir)', async () => {
  const m = await mensajeDeError(conRespuesta(400, { error: NOTAS_5 + ' Conexión: postgres://usuario:CLAVE_FICTICIA@servidor/base' }), LECTURA);
  igual(m, LECTURA.porDefecto);
});
await prueba('causa larga dentro de `detalle[]`: se resume a 300 con aviso', async () => {
  const larga = 'Estudiante Ficticio Seis: ' + 'falta la calificación del período 4 en Lengua Española; '.repeat(10);
  const m = await mensajeDeError(conRespuesta(400, { error: 'Datos incompletos', detalle: [larga] }), LECTURA);
  contiene(m, '• Estudiante Ficticio Seis: falta'); contiene(m, AVISO_RESUMIDO);
});

console.log('\n5xx: siempre mensaje controlado (datos ficticios)');
for (const [nombre, cuerpo] of [
  ['ruta /srv/... en `mensaje`', { mensaje: 'No se pudo abrir /srv/educaone/plantillas/registro.pdf' }],
  ['conexión postgres con clave en `error`', { error: 'Fallo al conectar a postgres://usuario:CLAVE_FICTICIA@servidor/base' }],
  ['texto aparentemente inocuo en `detail`', { detail: 'No se pudo generar el documento' }],
  ['texto plano', 'Internal Server Error'],
]) {
  await prueba(`500 con ${nombre}: no se reproduce`, async () => {
    const m = await mensajeDeError(conRespuesta(500, typeof cuerpo === 'string' ? cuerpo : blobJSON(cuerpo)), LECTURA);
    igual(m, MSG_500);
  });
}
await prueba('5xx en guardado: resultado incierto, sin reproducir el cuerpo', async () => {
  const m = await mensajeDeError(conRespuesta(500, { error: 'postgres://usuario:CLAVE_FICTICIA@servidor/base' }), GUARDADO);
  contiene(m, 'No se pudo confirmar si el cambio quedó guardado'); noContiene(m, 'CLAVE_FICTICIA'); noContiene(m.toLowerCase(), 'no se guardó');
});

console.log('\n4xx: textos internos descartados (datos ficticios)');
for (const [nombre, texto] of [
  ['ruta absoluta /srv/...', 'No se encontró la plantilla en /srv/educaone/plantillas/registro.pdf'],
  ['ruta /tmp/...', 'Archivo temporal /tmp/registro_123.pdf no disponible'],
  ['conexión postgres con usuario y clave', 'No se pudo leer el curso desde postgres://usuario:CLAVE_FICTICIA@servidor/base'],
  ['usuario:clave@host sin esquema', 'Origen usuario:CLAVE_FICTICIA@servidor.interno no responde'],
  ['URL interna https', 'Consulte https://interno.ejemplo.test/admin para más datos'],
  ['dirección IP', 'El servicio 10.0.0.12 rechazó la conexión'],
  ['localhost', 'No responde localhost en el puerto configurado'],
  ['variable de entorno', 'Revise DATABASE_URL en la configuración'],
  ['asignación clave=valor', 'Configuración inválida: modo=depuracion'],
  ['«contraseña:» con valor', 'contraseña: Ficticia123 no válida'],
  ['ruta de Windows', 'No existe C:\\srv\\educaone\\registro.pdf'],
  ['ruta UNC', 'Sin acceso a \\\\servidor\\compartida\\registros'],
  ['traza de JavaScript', 'Fallo at generarRegistro (registro.js:10:5)'],
  ['representación de objeto Python', "Valor <class 'dict'> object at 0x7f3a2b1c9d10 inesperado"],
  ['excepción de base de datos', 'UniqueViolation: psycopg2 rechazó la fila'],
  ['nombre de excepción', 'Fallo de ResourceException al generar'],
  ['detalle de PostgreSQL', 'Clave duplicada. DETAIL: Key (id)=(5) already exists.'],
  ['SQL DDL', 'DROP TABLE estudiantes falló'],
]) {
  await prueba(`4xx con ${nombre}: mensaje por defecto`, async () => {
    igual(await mensajeDeError(conRespuesta(422, blobJSON({ mensaje: texto })), LECTURA), LECTURA.porDefecto);
  });
}

console.log('\n4xx: explicaciones legítimas que deben seguir mostrándose');
for (const texto of [
  'Asistencia de Primaria: hay 1 asistencia(s) registradas fuera del año escolar (2025-09-01 a 2026-06-19). No se imprimen en otro mes ni se ocultan: corrija su fecha o el rango del año antes de emitir el Registro.',
  MSG_422,
  'Formación Humana, noviembre: se necesitan 11 columnas y la hoja permite 10.',
  'La asistencia del 14/05/2024 está fuera del año escolar.',
  'Revise P1/P2 de Matemática y/o Lengua Española.',
  'Solo puedes imprimir el registro de tus cursos asignados',
  'Este curso tiene más de una asignatura vinculada al bloque curricular LEN del Registro Escolar. Dirección debe dejar solo una asignatura vinculada a ese bloque.',
]) {
  await prueba(`se muestra: «${texto.slice(0, 50)}…»`, async () => {
    igual(await mensajeDeError(conRespuesta(422, blobJSON({ mensaje: texto })), LECTURA), texto);
  });
}

console.log('\nSin respuesta del servidor');
await prueba('fallo de conexión en lectura: conexión, no rechazo', async () => {
  igual(await mensajeDeError({ code: 'ERR_NETWORK', request: {} }, LECTURA),
    'No se pudo conectar con el servidor. Compruebe su conexión a internet e inténtelo de nuevo.');
});
await prueba('tiempo agotado en lectura', async () => {
  contiene(await mensajeDeError({ code: 'ECONNABORTED', request: {} }, LECTURA), 'tardó demasiado');
});
await prueba('guardado sin respuesta: resultado incierto, nunca «no se guardó»', async () => {
  for (const code of ['ERR_NETWORK', 'ECONNABORTED']) {
    const m = await mensajeDeError({ code, request: {} }, GUARDADO);
    contiene(m, 'No se sabe si el cambio quedó guardado'); noContiene(m.toLowerCase(), 'no se guardó');
  }
});
await prueba('502/503/504 de la pasarela: no disponible (lectura) / incierto (guardado)', async () => {
  contiene(await mensajeDeError(conRespuesta(503, new Blob(['<html>Service Unavailable</html>'])), LECTURA), 'no está disponible');
  contiene(await mensajeDeError(conRespuesta(504, ''), GUARDADO), 'No se sabe si el cambio quedó guardado');
});
await prueba('error que no es de axios: mensaje por defecto, sin lanzar', async () => {
  igual(await mensajeDeError(undefined, LECTURA), LECTURA.porDefecto);
  igual(await mensajeDeError(new Error('x'), LECTURA), LECTURA.porDefecto);
});

console.log('\nRegistroEscolarPage.tsx (fuente)');
const PAGINA = leer('pages', 'registro-escolar', 'RegistroEscolarPage.tsx');
await prueba('las 4 peticiones usan mensajeDeError; ya no se lee solo `.error`', async () => {
  igual((PAGINA.match(/await mensajeDeError\(err/g) || []).length, 4);
  noContiene(PAGINA, 'data?.error ||'); noContiene(PAGINA, 'parsed.error');
});
await prueba('el bloqueo del oficial sigue igual', async () => {
  contiene(PAGINA, 'const isBlocked = preview ? !preview.validacion.valid : false;');
  contiene(PAGINA, 'disabled={generating || isBlocked}');
});

console.log(`\n${ok} pasan, ${fallos.length} fallan`);
process.exit(fallos.length ? 1 : 0);
