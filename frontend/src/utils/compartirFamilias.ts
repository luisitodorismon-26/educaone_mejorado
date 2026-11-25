/**
 * FAM-DOC-1 · Compartir el Reporte del Período con las familias (frontend).
 *
 * Reglas puras (sin React) para que puedan probarse solas:
 *   · El contacto se elige entre padre, madre y tutor. Solo se puede elegir uno
 *     con teléfono UTILIZABLE: tener nombre no basta.
 *   · El mensaje lleva el enlace individual ya incluido: nadie copia ni pega.
 *   · Abrir WhatsApp NO es enviar: el estado que se muestra es «WhatsApp
 *     abierto», nunca «enviado», «entregado» ni «leído».
 */

export type RolContacto = 'padre' | 'madre' | 'tutor';

export interface Contacto {
  rol: RolContacto;
  nombre: string | null;
  parentesco: string | null;
  telefono_whatsapp: string | null;
  telefono_final: string | null;
  tiene_telefono: boolean;
  valido: boolean;
}

export interface DocumentoResumen {
  id: number;
  estudiante_id: number;
  version: number;
  estado: 'activo' | 'reemplazado' | 'anulado';
  fecha_preparado: string | null;
  preparado_por: string | null;
  url: string | null;
  tamano_bytes: number;
  visitas: number;
  descargas: number;
  vistas_previas: number;
  primera_visita: string | null;
  ultima_visita: string | null;
  whatsapp_abierto: number;
  ultimo_whatsapp: { fecha: string | null; contacto_rol: RolContacto | null; telefono_final: string | null } | null;
}

export interface FamiliaEstado {
  estudiante_id: number;
  nombre: string;
  contactos: Contacto[];
  contacto_sugerido: RolContacto | null;
  notas_pendientes: number;
  documento: DocumentoResumen | null;
  desactualizado: boolean | null;
  creado?: boolean;
}

export const ETIQUETA_ROL: Record<RolContacto, string> = { padre: 'Padre', madre: 'Madre', tutor: 'Tutor' };

const ORDINAL: Record<number, string> = { 1: 'primer', 2: 'segundo', 3: 'tercer', 4: 'cuarto' };

/** «Madre · •••• 2048». Nunca muestra el número completo en pantalla. */
export const telefonoOculto = (c: Pick<Contacto, 'telefono_final'>): string =>
  c.telefono_final ? `•••• ${c.telefono_final}` : 'sin teléfono';

export const etiquetaContacto = (c: Contacto): string => {
  const rol = c.rol === 'tutor' && c.parentesco ? `Tutor (${c.parentesco})` : ETIQUETA_ROL[c.rol];
  if (!c.tiene_telefono) return `${rol} · sin teléfono`;
  if (!c.valido) return `${rol} · teléfono incompleto`;
  return `${rol} · ${telefonoOculto(c)}`;
};

/** Contacto elegido: el que eligió la persona (si sigue siendo válido) o el sugerido. */
export const contactoElegido = (f: FamiliaEstado, eleccion?: RolContacto | null): Contacto | null => {
  const validos = f.contactos.filter(c => c.valido);
  if (eleccion) {
    const c = validos.find(x => x.rol === eleccion);
    if (c) return c;
  }
  return validos.find(x => x.rol === f.contacto_sugerido) || validos[0] || null;
};

export const primerNombre = (nombre: string | null | undefined): string =>
  (nombre || '').trim().split(/\s+/)[0] || '';

/** Mensaje con el enlace YA incluido. Sin calificaciones. */
export const mensajeFamilia = (p: { colegio: string; periodo: number; ano: string; estudiante: string; url: string }): string =>
  [
    `*${p.colegio}*`,
    `Ya está disponible el reporte de notas del ${ORDINAL[p.periodo] || ''} período (${p.ano}) de ${p.estudiante}.`,
    'Puede verlo y descargarlo aquí:',
    p.url,
    '',
    'Este enlace es personal: cualquier persona que lo reciba también podrá abrir el documento.',
  ].join('\n');

/** Enlace de WhatsApp al número del contacto con el mensaje preparado. No envía nada. */
export const enlaceWhatsApp = (telefono: string, mensaje: string): string =>
  `https://wa.me/${telefono.replace(/\D/g, '')}?text=${encodeURIComponent(mensaje)}`;

export type EstadoFamilia =
  | { tipo: 'sin_contacto'; texto: string }
  | { tipo: 'sin_documento'; texto: string }
  | { tipo: 'preparado'; texto: string }
  | { tipo: 'whatsapp_abierto'; texto: string }
  | { tipo: 'desactualizado'; texto: string };

/** Lo que el sistema SABE: nunca «enviado», «entregado» ni «leído». */
export const estadoFamilia = (f: FamiliaEstado): EstadoFamilia => {
  if (!f.contactos.some(c => c.valido)) return { tipo: 'sin_contacto', texto: 'Sin teléfono utilizable' };
  if (!f.documento) return { tipo: 'sin_documento', texto: 'Reporte sin preparar' };
  if (f.desactualizado) return { tipo: 'desactualizado', texto: 'Las notas cambiaron desde que se preparó' };
  if (f.documento.whatsapp_abierto > 0) return { tipo: 'whatsapp_abierto', texto: 'WhatsApp abierto (no confirma el envío)' };
  return { tipo: 'preparado', texto: 'Reporte preparado' };
};

/** Índice de la siguiente familia con la que se puede abrir WhatsApp (cíclico), o -1. */
export const siguienteFamilia = (familias: FamiliaEstado[], actual: number): number => {
  const n = familias.length;
  for (let k = 1; k <= n; k++) {
    const i = (actual + k) % n;
    if (familias[i].documento?.url && familias[i].contactos.some(c => c.valido)) return i;
  }
  return -1;
};

/** Visitas: se presentan como lo que son (no prueban lectura). */
export const textoVisitas = (d: DocumentoResumen): string => {
  const total = d.visitas + d.descargas;
  if (!total) return 'El enlace aún no se ha abierto';
  return `Enlace abierto ${total} ${total === 1 ? 'vez' : 'veces'} (puede incluir reenvíos; no confirma que se haya leído)`;
};
