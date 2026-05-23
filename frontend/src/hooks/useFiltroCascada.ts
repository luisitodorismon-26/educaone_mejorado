import { Nivel } from './useNivelesActivos';

interface WithNivel {
  nivel?: string | null;
  [key: string]: any;
}

/**
 * Filtra una lista por nivel. Los items sin `nivel` definido se asumen 'secundaria'.
 * Esto evita que datos viejos/incompletos desaparezcan accidentalmente.
 */
export function filterByNivel<T extends WithNivel>(items: T[], nivelFiltro: Nivel | 'todos'): T[] {
  if (nivelFiltro === 'todos') return items;
  return items.filter(item => (item.nivel || 'secundaria') === nivelFiltro);
}

/**
 * Extrae valores únicos (string) de una lista, opcionalmente aplicando filtro por nivel antes.
 * Útil para poblar dropdowns de Grado, Tanda, etc. que cascadean con la tab activa.
 */
export function uniqueFieldByNivel<T extends WithNivel>(
  items: T[],
  field: keyof T,
  nivelFiltro: Nivel | 'todos'
): string[] {
  const filtered = filterByNivel(items, nivelFiltro);
  return [...new Set(filtered.map(i => i[field] as string).filter(Boolean))];
}
