/**
 * Por qué la pantalla de asistencia está en solo lectura.
 *
 * En Primaria la asistencia diaria la registra el TITULAR del curso. Los demás
 * profesores del curso —Inglés, Educación Física, Artística— la VEN, porque
 * necesitan saber quién está presente para dar su clase, pero no la tocan.
 *
 * Aquí no se decide nada: el servidor ya resolvió si el usuario puede editar y
 * por qué no. Esto solo traduce ese motivo a una frase. El frontend nunca
 * deduce la titularidad por su cuenta, y menos aún mirando el horario.
 */
export const textoSoloLectura = (
  esProfesor: boolean,
  motivo: string | null | undefined
): string => {
  if (!esProfesor) return 'Solo los profesores pueden registrar asistencia.';
  switch (motivo) {
    case 'no_titular':
      return 'Asistencia registrada por el titular del curso. Vista de solo lectura.';
    case 'sin_titular':
      return 'Este curso no tiene un profesor titular asignado. Dirección debe asignar uno antes de registrar asistencia.';
    case 'titularidad_inconsistente':
      return 'El curso tiene una titularidad inconsistente. Dirección debe corregirla.';
    default:
      return 'Solo los profesores pueden registrar asistencia.';
  }
};
