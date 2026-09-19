/**
 * Recuperación pedagógica DEL PERÍODO — lógica pura.
 *
 * En 1ro y 2do la norma la registra de manera CUALITATIVA: aspectos no
 * logrados, estrategias y evidencias, y competencia lograda o no lograda.
 * En 3ro-6to es cuantitativa y se carga como RP en Calificaciones.
 *
 * Aquí no se decide la modalidad: el servidor ya la resolvió desde
 * Curso → Grado. Estas funciones solo traducen esa respuesta a la pantalla,
 * y existen aparte del componente para poder probarlas sin navegador.
 */

export type Modalidad = 'cualitativa' | 'cuantitativa';
export type ResultadoIntervencion = 'lograda' | 'no_lograda';

export interface Intervencion {
  id: number;
  estudiante_id: number;
  estudiante_nombre?: string | null;
  competencia_numero: number | null;
  periodo: number;
  aspectos_no_logrados: string;
  estrategias_evidencias: string | null;
  resultado: ResultadoIntervencion;
  observacion: string | null;
  registrado_por: number | null;
  fecha_registro: string | null;
  activo: boolean;
  motivo_retiro: string | null;
}

export interface BorradorIntervencion {
  estudiante_id: number | null;
  competencia_numero: number | null; // null = varias / el área entera
  periodo: number | null;
  aspectos_no_logrados: string;
  estrategias_evidencias: string;
  resultado: ResultadoIntervencion | null;
  observacion: string;
}

/** Número del grado leído de su nombre, o null si no se puede determinar.
 *  Espejo de `_numero_grado_estricto` del backend: ante la duda NO se adivina. */
export const numeroDeGrado = (nombre: string | null | undefined): number | null => {
  const m = /(\d+)/.exec(nombre || '');
  if (!m) return null;
  const n = parseInt(m[1], 10);
  return n >= 1 && n <= 6 ? n : null;
};

/** Solo 1ro y 2do registran la recuperación del período de forma cualitativa. */
export const esGradoCualitativo = (gradoNumero: number | null): boolean =>
  gradoNumero === 1 || gradoNumero === 2;

/** Qué explicarle al docente según la modalidad que devolvió el servidor. */
export const textoModalidad = (modalidad: Modalidad | null): string => {
  switch (modalidad) {
    case 'cualitativa':
      return 'En este grado la recuperación pedagógica del período se registra de forma cualitativa: no lleva nota.';
    case 'cuantitativa':
      return 'En este grado la recuperación pedagógica del período se carga como RP en Calificaciones.';
    default:
      return 'Seleccione un curso para ver qué tipo de recuperación le corresponde.';
  }
};

/** Valida el borrador antes de mandarlo. Devuelve el error o null. */
export const validarIntervencion = (b: BorradorIntervencion): string | null => {
  if (!b.estudiante_id) return 'Seleccione un estudiante.';
  if (!b.periodo || b.periodo < 1 || b.periodo > 4) return 'Seleccione el período.';
  if (!b.aspectos_no_logrados.trim()) {
    return 'Indique el aspecto o los aspectos de la competencia no logrados.';
  }
  if (b.resultado !== 'lograda' && b.resultado !== 'no_lograda') {
    return 'Marque si la competencia quedó lograda o no lograda.';
  }
  if (b.competencia_numero !== null && ![1, 2, 3].includes(b.competencia_numero)) {
    return 'La competencia debe ser C1, C2, C3 o «Varias».';
  }
  return null;
};

export const etiquetaResultado = (r: ResultadoIntervencion): string =>
  r === 'lograda' ? 'Lograda' : 'No lograda';

export const etiquetaCompetencia = (n: number | null): string =>
  n === null ? 'Varias' : `C${n}`;

/**
 * Historial por estudiante, en orden cronológico.
 *
 * Varias intervenciones sobre el mismo estudiante y período son lo normal
 * —«no lograda» en noviembre, «lograda» en diciembre—, así que aquí NO se
 * deduplica ni se conserva solo la última: se devuelven todas, y las
 * retiradas también, marcadas.
 */
export const historialPorEstudiante = (
  intervenciones: Intervencion[]
): Map<number, Intervencion[]> => {
  const orden = [...intervenciones].sort((a, b) => {
    const fa = a.fecha_registro || '';
    const fb = b.fecha_registro || '';
    if (fa !== fb) return fa < fb ? -1 : 1;
    return a.id - b.id;
  });
  const mapa = new Map<number, Intervencion[]>();
  for (const i of orden) {
    const lista = mapa.get(i.estudiante_id) || [];
    lista.push(i);
    mapa.set(i.estudiante_id, lista);
  }
  return mapa;
};

/** Un docente solo edita/retira lo que él registró. El resto lo ve. */
export const puedeModificar = (
  i: Intervencion,
  usuarioId: number | null | undefined,
  esProfesor: boolean
): boolean => Boolean(esProfesor && i.activo && usuarioId && i.registrado_por === usuarioId);

export const borradorVacio = (periodo: number | null): BorradorIntervencion => ({
  estudiante_id: null,
  competencia_numero: null,
  periodo,
  aspectos_no_logrados: '',
  estrategias_evidencias: '',
  resultado: null,
  observacion: '',
});
