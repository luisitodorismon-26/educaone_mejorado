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
 *   · En los 5xx el mensaje lo pone el frontend: no se reproduce nada del cuerpo
 *     (mensaje, error, detail ni detalle), que puede ser el texto interno de la excepción.
 *   · En los 4xx, cualquier texto que parezca interno (traza, SQL, credenciales,
 *     URLs o conexiones, IPs, rutas, variables de entorno, HTML, parámetros) se
 *     descarta y se usa el mensaje genérico.
 *   · Un texto largo y seguro no se descarta: se resume con un aviso visible.
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

/** Largo máximo que se muestra de un texto; lo que sobra se resume con aviso. */
const MAX_LARGO = 600;
/** Largo máximo por causa de la lista `detalle`. */
const MAX_LARGO_DETALLE = 300;
/** Por encima de esto no es una explicación para el usuario: se descarta. */
const MAX_ANALIZABLE = 20000;
const MAX_DETALLES = 6;
export const AVISO_RESUMIDO = ' … [mensaje resumido: el servidor envió un texto más largo]';

// Se comprueban sobre el texto COMPLETO, antes de resumirlo: un dato interno al
// final de un texto largo también descarta el texto.
const PATRONES_INTERNOS: RegExp[] = [
  // Trazas y nombres de excepción
  /traceback/i,
  /File "/,
  /\bline \d+/i,
  /\bat \S+ \(/,
  /<class '|object at 0x|0x[0-9a-f]{6,}/i,
  /sqlalchemy|psycopg|sqlite|asyncpg|uvicorn|starlette|postgres|mysql|redis/i,
  /\b\w*(Integrity|Operational|Programming|Attribute|Key|Type|Value|Index|Runtime|Name|Lookup|Connection)Error\b/,
  /\b\w*Exception\b/,
  // SQL
  /\b(select|insert|update|delete|drop|alter|create|truncate)\b[\s\S]*\b(from|into|table|set|where|values)\b/i,
  /\[SQL:|\bDETAIL:|\bHINT:/,
  // Credenciales, tokens y variables de entorno
  /\bpassword\b|\bpasswd\b|\bpwd\b|\bsecret\b|\btoken\b|\bbearer\b|authorization|api[_-]?key|\bdsn\b/i,
  /\b(contraseña|clave|credencial(es)?|usuario)\s*[:=]/i,
  /eyJ[A-Za-z0-9_-]{10,}/,
  /\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/,
  /\w\s?=\s?\S/,
  // Direcciones: cualquier URL con esquema, user:clave@host, IPs, localhost
  /\b[a-z][a-z0-9+.-]*:\/\//i,
  /[^\s@:/]+:[^\s@/]+@[^\s@]+/,
  /\b\d{1,3}(\.\d{1,3}){3}\b/,
  /\blocalhost\b/i,
  // Rutas de archivo (Windows, UNC y absolutas de Unix con al menos dos tramos)
  /[A-Za-z]:\\|\\\\[\w.-]+\\/,
  /(^|[\s"'(=:,])\/[\w.-]+\/[\w.-]+/,
  // HTML, parámetros de URL y objetos serializados mal
  /<\/?[a-z!][^>]*>/i,
  /\?[a-z_]+=/i,
  /\[object /i,
];

/** Resume un texto largo por un límite de palabra y lo indica de forma visible. */
function resumir(t: string, max: number): string {
  if (t.length <= max) return t;
  let corte = t.slice(0, max);
  const espacio = corte.lastIndexOf(' ');
  if (espacio > max * 0.6) corte = corte.slice(0, espacio);
  return corte.replace(/[\s,;:.—–-]+$/, '') + AVISO_RESUMIDO;
}

/**
 * Devuelve el texto si es seguro y comprensible; si no, `null`.
 * Primero se aplican las protecciones al texto completo y después, si es largo,
 * se resume con aviso: una explicación válida no se pierde por su largo.
 */
export function textoSeguro(valor: unknown, max: number = MAX_LARGO): string | null {
  if (typeof valor !== 'string') return null;
  const t = valor.trim();
  if (!t || t.length > MAX_ANALIZABLE || !/\p{L}/u.test(t)) return null;
  if (PATRONES_INTERNOS.some((p) => p.test(t))) return null;
  return resumir(t, max);
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

  // 5xx: fallo del servidor. El texto lo controla el frontend; no se reproduce
  // nada del cuerpo (mensaje, error, detail ni detalle), que puede ser interno.
  if (estado >= 500) {
    return operacion === 'guardado'
      ? `El servidor tuvo un problema al procesar la solicitud (error ${estado}). No se pudo confirmar si el cambio quedó guardado: recargue para comprobarlo antes de repetirlo. Si se repite, avise a soporte técnico.`
      : `El servidor tuvo un problema al procesar la solicitud (error ${estado}). Inténtelo de nuevo; si se repite, avise a soporte técnico.`;
  }

  const principal = textoSeguro(datos.mensaje) ?? textoSeguro(datos.error) ?? textoSeguro(datos.detail)
    ?? (typeof cuerpo === 'string' ? textoSeguro(cuerpo) : null);

  // Lista de causas (p. ej. errores de validación del Registro). Solo textos.
  const detalles = Array.isArray(datos.detalle)
    ? (datos.detalle as unknown[]).map((d) => textoSeguro(d, MAX_LARGO_DETALLE))
      .filter((d): d is string => !!d && d !== principal)
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
