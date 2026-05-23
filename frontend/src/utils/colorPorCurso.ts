// ════════════════════════════════════════════════════════════════════
// Paleta de colores consistentes por curso v2.13.2
// 
// Cada curso recibe un color determinístico de una paleta fija de 12.
// El color depende del ID del curso (no del orden), garantizando que
// el mismo curso siempre tenga el mismo color en TODOS los gráficos.
//
// Uso:
//   import { colorPorCurso } from '../../utils/colorPorCurso';
//   <Cell fill={colorPorCurso(curso.id)} />
// ════════════════════════════════════════════════════════════════════

// Paleta de 12 colores Tailwind-compatible (suficientemente distintos).
// Orden seleccionado para maximizar contraste visual entre vecinos.
const PALETA_CURSOS = [
  '#3B82F6', // blue-500
  '#10B981', // emerald-500
  '#F59E0B', // amber-500
  '#EF4444', // red-500
  '#8B5CF6', // violet-500
  '#EC4899', // pink-500
  '#14B8A6', // teal-500
  '#F97316', // orange-500
  '#6366F1', // indigo-500
  '#84CC16', // lime-500
  '#06B6D4', // cyan-500
  '#A855F7', // purple-500
];

/**
 * Devuelve un color consistente para un curso dado.
 * Mismo curso_id → mismo color siempre.
 * 
 * @param cursoId ID del curso (number o string convertible)
 * @returns hex color (ej "#3B82F6")
 */
export function colorPorCurso(cursoId: number | string | undefined | null): string {
  if (cursoId === null || cursoId === undefined) return '#9CA3AF'; // gray-400 para sin curso
  const id = typeof cursoId === 'string' ? parseInt(cursoId) || 0 : cursoId;
  return PALETA_CURSOS[Math.abs(id) % PALETA_CURSOS.length];
}

/**
 * Versión que toma el nombre del curso si no tiene id disponible.
 * Hash simple del nombre.
 */
export function colorPorNombreCurso(nombre: string | undefined | null): string {
  if (!nombre) return '#9CA3AF';
  let hash = 0;
  for (let i = 0; i < nombre.length; i++) {
    hash = ((hash << 5) - hash) + nombre.charCodeAt(i);
    hash = hash & hash;
  }
  return PALETA_CURSOS[Math.abs(hash) % PALETA_CURSOS.length];
}

export { PALETA_CURSOS };
