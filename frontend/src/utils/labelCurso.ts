/**
 * Etiqueta visible de un curso: SIEMPRE con su tanda.
 *
 * POR QUÉ EXISTE
 * --------------
 * EducaOne es multi-tanda: el mismo grado puede existir legítimamente en
 * Matutina y en Vespertina, y son cursos distintos e independientes —cada uno
 * con sus estudiantes, sus profesores, sus notas y su Salida Optativa—.
 *
 * Hasta ahora una veintena de selectores construían la etiqueta así:
 *
 *     c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo
 *
 * El fallback estaba invertido: como `grado` siempre viene, `nombre_completo`
 * —que SÍ trae la tanda— no se usaba nunca, y los dos 4to de Secundaria se
 * mostraban con la misma cadena literal. Elegir uno u otro era cuestión de
 * suerte, y una configuración podía aterrizar en el curso equivocado.
 *
 * FORMATO
 * -------
 *     4to Secundaria A · Matutina     (con sección)
 *     4to Secundaria · Vespertina     (sección vacía)
 *
 * El backend ya devuelve `grado`, `nombre` (sección), `tanda` y
 * `nombre_completo`; aquí no se pide ningún dato nuevo. Si el payload no trae
 * `tanda` se cae a `nombre_completo`, que puede traerla por su cuenta
 * (`Curso.nombre_completo` la incluye), antes que a una etiqueta sin tanda.
 */

export interface CursoEtiquetable {
  id?: number | string | null;
  /** Nombre del grado, p. ej. "4to Secundaria". */
  grado?: string | null;
  /** Sección del curso, p. ej. "A". Puede venir vacía. */
  nombre?: string | null;
  /** Nombre de la tanda, p. ej. "Matutina". */
  tanda?: string | null;
  /** Compuesto por el backend; incluye la tanda cuando el curso la tiene. */
  nombre_completo?: string | null;
}

/** Separador entre el curso y su tanda. */
export const SEPARADOR_TANDA = ' · ';

export function labelCurso(curso: CursoEtiquetable | null | undefined): string {
  const grado = (curso?.grado ?? '').trim();
  const seccion = (curso?.nombre ?? '').trim();
  const tanda = (curso?.tanda ?? '').trim();
  const completo = (curso?.nombre_completo ?? '').trim();

  const base = [grado, seccion].filter(Boolean).join(' ');

  // Caso normal: se compone desde las partes, que es lo que da el formato
  // pedido y garantiza que la tanda nunca se pierda.
  if (base && tanda) return base + SEPARADOR_TANDA + tanda;

  // Sin tanda en el payload, `nombre_completo` es mejor que `base`: el backend
  // la incluye cuando el curso la tiene.
  if (completo) return completo;
  if (base) return base;

  // Último recurso: nunca devolver cadena vacía, que dejaría una opción muda.
  const id = curso?.id;
  return id === null || id === undefined || id === '' ? 'Curso' : `Curso ${id}`;
}

export default labelCurso;
