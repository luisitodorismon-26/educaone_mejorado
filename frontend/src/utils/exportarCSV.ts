/**
 * EducaOne — exportación a CSV desde el navegador (v2.19.4).
 *
 * El sistema ya exportaba CSV con esta misma técnica dentro de `DataTable`
 * (Blob + BOM UTF-8 + enlace de descarga), pero la lógica vivía encerrada en
 * ese componente y no era reutilizable desde una pantalla que no lo usa.
 * Acá queda como utilidad independiente y probada, sin tocar `DataTable`:
 * unificar ambas es un seguimiento posterior, no algo que convenga hacer
 * la víspera de una capacitación.
 *
 * No requiere backend: exporta exactamente lo que la persona está viendo,
 * respetando los filtros aplicados en pantalla.
 */

export interface ColumnaCSV<T> {
  /** Encabezado tal como debe aparecer en el archivo. */
  label: string;
  /** Cómo obtener el valor de esa columna para una fila. */
  valor: (fila: T) => unknown;
}

/** Escapa un valor según RFC 4180: comillas dobles duplicadas y todo entrecomillado. */
function celda(valor: unknown): string {
  if (valor === null || valor === undefined) return '""';
  return `"${String(valor).replace(/"/g, '""')}"`;
}

/**
 * Genera y descarga un CSV.
 *
 * El BOM (﻿) es deliberado: sin él, Excel en Windows —que es lo que usan
 * en la escuela— interpreta el archivo como ANSI y rompe todas las tildes y
 * las eñes. Es la misma precaución que ya tomaba DataTable.
 *
 * @returns true si había algo que exportar, false si la lista estaba vacía.
 */
export function exportarCSV<T>(
  filas: T[],
  columnas: ColumnaCSV<T>[],
  nombreArchivo: string
): boolean {
  if (!filas.length) return false;

  const encabezados = columnas.map((c) => celda(c.label)).join(',');
  const cuerpo = filas.map((fila) =>
    columnas.map((c) => celda(c.valor(fila))).join(',')
  );
  const csv = [encabezados, ...cuerpo].join('\n');

  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombreArchivo.endsWith('.csv') ? nombreArchivo : `${nombreArchivo}.csv`;
  document.body.appendChild(enlace);
  enlace.click();
  document.body.removeChild(enlace);
  URL.revokeObjectURL(url);
  return true;
}

export default exportarCSV;
