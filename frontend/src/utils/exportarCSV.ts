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

/**
 * Caracteres con los que Excel y LibreOffice deciden que una celda es una
 * FÓRMULA en vez de texto.
 */
const INICIOS_DE_FORMULA = new Set(['=', '+', '-', '@']);

/**
 * Neutraliza la inyección de fórmulas (CSV / Formula Injection).
 *
 * El contenido de estos CSV lo escriben las personas del colegio: el título y
 * la descripción de un reporte de conducta son texto libre. Si alguien guarda
 * un reporte titulado `=SUM(A1:A2)` —o algo mucho peor, como una fórmula que
 * llama a un comando externo— y Dirección abre el archivo exportado, la hoja
 * de cálculo lo EJECUTA. El riesgo no está en EducaOne sino en Excel, y por
 * eso hay que desactivarlo en el archivo, no en la pantalla.
 *
 * Se antepone un apóstrofo, que es la marca estándar de "esto es texto" en
 * Excel y LibreOffice. El apóstrofo no se ve al abrir la hoja: la celda
 * muestra el valor original tal cual.
 *
 * Se mira el primer carácter SIGNIFICATIVO, no el primero a secas: las hojas
 * de cálculo ignoran los espacios iniciales al decidir si algo es una fórmula,
 * así que `   =SUM(A1:A2)` se ejecuta igual que `=SUM(A1:A2)`. El regex
 * también descarta tabuladores, saltos de línea y espacios duros.
 *
 * Nota deliberada: un valor como `-5` también queda como texto. En estos
 * exportes ninguna columna es un número negativo (son fechas, nombres, cursos
 * y texto libre), así que preferimos proteger de más antes que de menos.
 */
export function neutralizarFormulaCSV(texto: string): string {
  const primerSignificativo = texto.replace(/^[\s﻿ ]+/, '').charAt(0);
  if (!primerSignificativo) return texto;
  return INICIOS_DE_FORMULA.has(primerSignificativo) ? `'${texto}` : texto;
}

/**
 * Convierte un valor en una celda CSV segura.
 *
 * Orden de las operaciones: primero se neutraliza la fórmula y después se
 * escapan las comillas. Al ir todo entre comillas dobles, las comas y los
 * saltos de línea del contenido quedan dentro del campo sin romper la
 * estructura del archivo (RFC 4180).
 *
 * Exportada aparte de `exportarCSV` para poder verificarla sin DOM.
 */
export function celdaCSV(valor: unknown): string {
  if (valor === null || valor === undefined) return '""';
  const texto = neutralizarFormulaCSV(String(valor));
  return `"${texto.replace(/"/g, '""')}"`;
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

  const encabezados = columnas.map((c) => celdaCSV(c.label)).join(',');
  const cuerpo = filas.map((fila) =>
    columnas.map((c) => celdaCSV(c.valor(fila))).join(',')
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
