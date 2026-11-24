/**
 * COM-DUP-1 · clave de envío al CREAR un comunicado (lógica pura, sin React).
 *
 * La clave identifica un INTENTO de publicación, no un contenido:
 *   · reintentar el mismo envío (respuesta perdida, 504, otro clic…) reutiliza la
 *     clave → el servidor devuelve el comunicado ya creado y no lo duplica;
 *   · una publicación nueva lleva clave nueva (aunque el texto sea idéntico).
 *
 * Reglas:
 *   · Con un envío INCIERTO pendiente y el MISMO contenido → reintento (misma clave).
 *   · Con un envío incierto y OTRO contenido, o con un CONFLICTO (409: la clave ya
 *     se usó con otro contenido) → no se envía nada: hace falta una decisión
 *     explícita de la persona.
 *   · Confirmado (201, o 200 de reintento) → la clave se descarta.
 *   · Rechazo 4xx de un envío NUEVO → no se guardó nada: no queda pendiente.
 *   · Rechazo 4xx de un REINTENTO → el envío anterior sigue pendiente de comprobar
 *     (puede haberse guardado): se conserva su referencia; nunca se afirma que no
 *     se guardó.
 *   · Incierto (sin respuesta o 5xx) → pendiente, con la misma clave.
 *
 * La clave vive en memoria de la página: recargar la pierde (el servidor ya no
 * puede reconocer el reintento; hay que consultar la lista antes de repetir).
 */

export interface ContenidoComunicado {
  titulo: string;
  contenido: string;
  alcance: string;
  imagen: string;
}

export type EstadoPendiente = 'incierto' | 'conflicto';

export interface EnvioPendiente {
  clave: string;
  huella: string;
  contenido: ContenidoComunicado;
  estado: EstadoPendiente;
  hora: string;
}

/** Referencia de un envío sin confirmar que se dejó atrás por decisión expresa. */
export interface ReferenciaAnotada {
  clave: string;
  titulo: string;
  hora: string;
  estado: EstadoPendiente;
}

export type Decision =
  | { accion: 'enviar'; clave: string; reintento: boolean }
  | { accion: 'decidir'; motivo: 'contenido_distinto' | 'conflicto' };

export type ResultadoEnvio = 'confirmado' | 'rechazo' | 'incierto' | 'conflicto';

export const huellaContenido = (c: ContenidoComunicado): string =>
  JSON.stringify([c.titulo, c.contenido, c.alcance, c.imagen || '']);

/** Qué hacer al pulsar «Publicar». */
export function decidirEnvio(pendiente: EnvioPendiente | null, contenido: ContenidoComunicado,
  nuevaClave: () => string): Decision {
  if (!pendiente) return { accion: 'enviar', clave: nuevaClave(), reintento: false };
  if (pendiente.estado === 'conflicto') return { accion: 'decidir', motivo: 'conflicto' };
  if (pendiente.huella === huellaContenido(contenido)) return { accion: 'enviar', clave: pendiente.clave, reintento: true };
  return { accion: 'decidir', motivo: 'contenido_distinto' };
}

/**
 * Estado tras la respuesta. `antes` es el pendiente que había al pulsar (null si
 * era un envío nuevo); `enviado` describe lo que se acaba de mandar.
 */
export function trasRespuesta(antes: EnvioPendiente | null, enviado: Omit<EnvioPendiente, 'estado'>,
  resultado: ResultadoEnvio): { pendiente: EnvioPendiente | null; reintentoRechazado: boolean } {
  switch (resultado) {
    case 'confirmado':
      return { pendiente: null, reintentoRechazado: false };
    case 'incierto':
      return { pendiente: { ...enviado, estado: 'incierto' }, reintentoRechazado: false };
    case 'conflicto':
      return { pendiente: { ...enviado, estado: 'conflicto' }, reintentoRechazado: false };
    case 'rechazo':
      // Un rechazo de un REINTENTO no dice nada del envío anterior: sigue pendiente.
      return antes ? { pendiente: antes, reintentoRechazado: true } : { pendiente: null, reintentoRechazado: false };
  }
}

/** «Publicar como comunicado nuevo»: la referencia anterior se anota, no se borra en silencio. */
export function anotarReferencia(anotadas: ReferenciaAnotada[], pendiente: EnvioPendiente): ReferenciaAnotada[] {
  if (anotadas.some((a) => a.clave === pendiente.clave)) return anotadas;
  return [...anotadas, { clave: pendiente.clave, titulo: pendiente.contenido.titulo, hora: pendiente.hora, estado: pendiente.estado }];
}

export const nuevaClaveEnvio = (): string =>
  (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
