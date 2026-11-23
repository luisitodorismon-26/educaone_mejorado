/**
 * Traduce un error de una petición a un mensaje que el usuario pueda entender.
 *
 * El backend explica los rechazos en distintos campos según el endpoint:
 *   · `mensaje`  (409/422 de Registro: «… hay 11 días y la hoja tiene 10 columnas»)
 *   · `error`    (400/403/404 de la app; a veces con `detalle: string[]` y `sugerencia`)
 *   · `detail`   (HTTPException de FastAPI)
 * y cuando se pidió un PDF (`responseType: 'blob'`) ese JSON llega DENTRO de un Blob.
 *
 * Reglas:
 *   · Solo se muestran textos (se comprueba el tipo): nunca objetos ni `[object Object]`.
 *   · En los 5xx no se muestra `detalle`: suele ser el texto interno de la excepción.
 *   · Cualquier texto que parezca interno (traza, SQL, credenciales, HTML, rutas,
 *     parámetros de URL) se descarta y se usa el mensaje genérico.
 *   · Sin respuesta del servidor no se afirma un rechazo: se dice que no hubo
 *     conexión o respuesta. En un guardado, además, se avisa de que el resultado
 *     es incierto en vez de decir que «no se guardó».
 *
 * Solo lee el error: no cambia validaciones, permisos ni el bloqueo que lo produjo.
 */

export type Operacion = 'lectura' | 'guardado';

export interface OpcionesMensaje {
  /** Mensaje si el servidor rechazó sin dar una explicación utilizable. */
  porDefecto: string;
  /** `guardado` cambia los textos de conexión/tiempo agotado a «resultado incierto». */
  operacion?: Operacion;
  /** Acción recomendada por `motivo` conocido, si el servidor no trae una. */
  accionesPorMotivo?: Record<string, string>;
}

const MAX_LARGO = 600;
const MAX_DETALLES = 6;

const PATRONES_INTERNOS: RegExp[] = [
  /traceback/i,
  /File "/,
  /\bline \d+/i,
  /sqlalchemy|psycopg|sqlite|asyncpg|uvicorn|starlette/i,
  /\b\w*(Integrity|Operational|Programming|Attribute|Key|Type|Value|Index|Runtime|Name)Error\b/,
  /\bselect\b[\s\S]+\bfrom\b/i,
  /\binsert\s+into\b/i,
  /\bupdate\s+\w+\s+set\b/i,
  /\bdelete\s+from\b/i,
  /\bpassword\b|\bpasswd\b|\bsecret\b|\btoken\b|\bbearer\b|authorization|api[_-]?key/i,
  /eyJ[A-Za-z0-9_-]{10,}/,
  /<\/?[a-z!][^>]*>/i,
  /\?[a-z_]+=/i,
  /[A-Za-z]:\\|\/(usr|app|home|opt|var)\//,
  /\[object /i,
];

/** Devuelve el texto si es seguro y comprensible; si no, `null`. */
export function textoSeguro(valor: unknown): string | null {
  if (typeof valor !== 'string') return null;
  const t = valor.trim();
  if (!t || t.length > MAX_LARGO || !/\p{L}/u.test(t)) return null;
  if (PATRONES_INTERNOS.some((p) => p.test(t))) return null;
  return t;
}

const sinPuntoFinal = (t: string) => t.replace(/[.:;\s]+$/, '');

/** Mensaje a partir del estado HTTP y el cuerpo ya convertido a objeto (o texto). */
export function mensajeDesdeRespuesta(estado: number, cuerpo: unknown, opciones: OpcionesMensaje): string {
  const { porDefecto, operacion = 'lectura', accionesPorMotivo } = opciones;
  const datos = cuerpo && typeof cuerpo === 'object' && !Array.isArray(cuerpo)
    ? (cuerpo as Record<string, unknown>) : {};

  // 502/503/504: lo devuelve la pasarela, no la aplicación. La petición pudo
  // haberse procesado o no.
  if (estado === 502 || estado === 503 || estado === 504) {
    return operacion === 'guardado'
      ? `El servidor no respondió a tiempo (error ${estado}). No se sabe si el cambio quedó guardado: recargue para comprobarlo antes de repetirlo.`
      : `El servidor no está disponible en este momento (error ${estado}). Inténtelo de nuevo en unos minutos.`;
  }

  const principal = textoSeguro(datos.mensaje) ?? textoSeguro(datos.error) ?? textoSeguro(datos.detail)
    ?? (typeof cuerpo === 'string' && estado < 500 ? textoSeguro(cuerpo) : null);

  if (estado >= 500) {
    const base = principal ?? 'El servidor tuvo un problema al procesar la solicitud';
    return `${sinPuntoFinal(base)} (error ${estado}). Si se repite, avise a soporte técnico.`;
  }

  // Lista de causas (p. ej. errores de validación del Registro). Solo textos.
  const detalles = Array.isArray(datos.detalle)
    ? (datos.detalle as unknown[]).map(textoSeguro).filter((d): d is string => !!d && d !== principal)
    : [];

  const motivo = typeof datos.motivo === 'string' ? datos.motivo : '';
  const accion = textoSeguro(datos.accion) ?? textoSeguro(datos.sugerencia)
    ?? (motivo && accionesPorMotivo ? accionesPorMotivo[motivo] ?? null : null);

  let texto = principal ?? (
    estado === 401 ? 'Su sesión expiró. Inicie sesión de nuevo.'
      : estado === 403 ? 'Su usuario no tiene permiso para esta acción.'
        : estado === 404 ? 'No se encontró lo solicitado. Puede que se haya eliminado o que no pertenezca a su centro.'
          : porDefecto);

  if (detalles.length) {
    const visibles = detalles.slice(0, MAX_DETALLES);
    const resto = detalles.length - visibles.length;
    texto = `${sinPuntoFinal(texto)}:\n${visibles.map((d) => `• ${d}`).join('\n')}`
      + (resto > 0 ? `\n• … y ${resto} más.` : '');
  }
  if (accion && !texto.includes(accion)) texto += `\nQué hacer: ${accion}`;
  return texto;
}

/** Convierte el cuerpo de la respuesta (objeto, texto JSON o Blob con JSON) a objeto o texto. */
async function leerCuerpo(data: unknown): Promise<unknown> {
  let crudo: unknown = data;
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    try { crudo = await data.text(); } catch { return null; }
  }
  if (typeof crudo === 'string') {
    const t = crudo.trim();
    if (t.startsWith('{') || t.startsWith('[')) {
      try { return JSON.parse(t); } catch { return null; }
    }
    return t;
  }
  return crudo;
}

/** Mensaje para cualquier error de axios (o desconocido). Nunca lanza. */
export async function mensajeDeError(err: unknown, opciones: OpcionesMensaje): Promise<string> {
  const e = (err ?? {}) as { response?: { status?: number; data?: unknown }; code?: string; request?: unknown };
  const guardado = opciones.operacion === 'guardado';

  if (!e.response) {
    if (e.code === 'ECONNABORTED' || e.code === 'ETIMEDOUT') {
      return guardado
        ? 'El servidor no confirmó a tiempo. No se sabe si el cambio quedó guardado: recargue para comprobarlo antes de repetirlo.'
        : 'El servidor tardó demasiado en responder. Inténtelo de nuevo.';
    }
    if (e.request || e.code === 'ERR_NETWORK') {
      return guardado
        ? 'Se perdió la conexión con el servidor antes de recibir confirmación. No se sabe si el cambio quedó guardado: compruebe su conexión y recargue para verificarlo.'
        : 'No se pudo conectar con el servidor. Compruebe su conexión a internet e inténtelo de nuevo.';
    }
    return opciones.porDefecto;
  }

  const cuerpo = await leerCuerpo(e.response.data);
  return mensajeDesdeRespuesta(e.response.status ?? 0, cuerpo, opciones);
}
