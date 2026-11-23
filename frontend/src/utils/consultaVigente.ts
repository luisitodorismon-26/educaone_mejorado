/**
 * Consultas de solo lectura cuyo resultado solo vale mientras siguen VIGENTES.
 *
 * Lo usa AvisoEnvio para «Consultar lista»: si mientras la consulta está en
 * vuelo cambia el aviso, cambia el formulario, el componente se desmonta o
 * empieza otra consulta, la respuesta (o el error) de la anterior se ignora y
 * su petición se cancela. Así una respuesta vieja nunca actualiza el aviso
 * actual ni la lista de la página, y nunca pisa una consulta posterior.
 *
 * Sin dependencias de React: se prueba en Node.
 */

export type ResultadoEjecucion<T> = { ok: true; valor: T } | { ok: false; error: unknown };

export interface ControlConsultas {
  /** Invalida (y cancela) la consulta en vuelo, si la hay. */
  invalidar(): void;
  /**
   * Ejecuta `fn` como la consulta vigente (invalida la anterior). Llama a
   * `alTerminar` SOLO si al terminar sigue siendo la vigente. Devuelve si se aplicó.
   */
  ejecutar<T>(fn: (signal: AbortSignal) => Promise<T>, alTerminar: (r: ResultadoEjecucion<T>) => void): Promise<boolean>;
}

export function crearControlConsultas(): ControlConsultas {
  let generacion = 0;
  let enVuelo: AbortController | null = null;

  const invalidar = () => {
    generacion++;
    if (enVuelo) { enVuelo.abort(); enVuelo = null; }
  };

  return {
    invalidar,
    async ejecutar(fn, alTerminar) {
      invalidar();
      const mia = generacion;
      const ctl = new AbortController();
      enVuelo = ctl;
      const vigente = () => mia === generacion && !ctl.signal.aborted;
      let resultado: ResultadoEjecucion<any>;
      try {
        resultado = { ok: true, valor: await fn(ctl.signal) };
      } catch (error) {
        resultado = { ok: false, error };
      }
      if (enVuelo === ctl) enVuelo = null;
      if (!vigente()) return false;
      alTerminar(resultado);
      return true;
    },
  };
}

/** Respuesta de la lista con un formato que no se puede interpretar. */
export class ConsultaInvalida extends Error {
  constructor(motivo: string) {
    super(`Respuesta de la lista con formato inesperado: ${motivo}`);
    this.name = 'ConsultaInvalida';
  }
}

/**
 * Exige que `datos` sea una LISTA de objetos con los campos indicados. Si no lo
 * es, lanza ConsultaInvalida: un formato inesperado es un fallo de la consulta,
 * nunca una lista vacía. Una lista vacía `[]` es válida.
 */
export function exigirLista<T>(datos: unknown, camposObligatorios: string[]): T[] {
  if (!Array.isArray(datos)) throw new ConsultaInvalida('no es una lista');
  datos.forEach((d, i) => {
    if (!d || typeof d !== 'object' || Array.isArray(d)) throw new ConsultaInvalida(`el elemento ${i} no es un objeto`);
    for (const c of camposObligatorios) {
      if (!(c in (d as Record<string, unknown>))) throw new ConsultaInvalida(`al elemento ${i} le falta «${c}»`);
    }
  });
  return datos as T[];
}
