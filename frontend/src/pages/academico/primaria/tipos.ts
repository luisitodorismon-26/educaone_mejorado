// Tipos compartidos por las tabs de AcademicoPrimariaPage v2.13.45
// CARRIL SEPARADO de secundaria. Primaria: 3 competencias, corte 65.

export interface Curso {
  id: number;
  nombre_completo: string;
  grado?: string;
  nivel?: string;
  ciclo?: string;
  tanda?: string;
  nombre?: string;
}

export interface Asignatura {
  id: number;
  nombre: string;
}

export interface CompetenciaPrim {
  id: number | null;
  estudiante_id: number;
  asignatura_id: number;
  competencia_numero: number;
  competencia_nombre: string | null;
  p1: number | null; rp1: number | null;
  p2: number | null; rp2: number | null;
  p3: number | null; rp3: number | null;
  p4: number | null; rp4: number | null;
  // NE por periodo (R2). El backend manda ademas el estado ya resuelto.
  ne1?: boolean; ne2?: boolean; ne3?: boolean; ne4?: boolean;
  estados?: Record<number, EstadoPeriodo>;
  final_competencia: number | null;
  literal: string | null;
}

// Los tres estados de un periodo. PENDIENTE y NE no son lo mismo: el primero
// dice "todavia no", el segundo dice "no se evaluo, y esta justificado".
export type EstadoPeriodo = 'evaluado' | 'ne' | 'pendiente';

export function estadoPeriodoDe(comp: CompetenciaPrim | undefined, periodo: number): EstadoPeriodo {
  if (!comp) return 'pendiente';
  const dado = comp.estados?.[periodo];
  if (dado) return dado;                       // el backend es la autoridad
  if (comp[`ne${periodo}` as keyof CompetenciaPrim]) return 'ne';
  return valorPeriodoEfectivo(comp, periodo) != null ? 'evaluado' : 'pendiente';
}

export const ETIQUETA_ESTADO: Record<EstadoPeriodo, string> = {
  evaluado: 'Evaluado',
  ne: 'NE — No Evaluado',
  pendiente: 'Pendiente de evaluar',
};

export const AYUDA_NE_PRIMARIA =
  'NE = No Evaluado. Se marca cuando el estudiante no participo del periodo por ' +
  'una causa justificada. No es "todavia no hay nota": un periodo sin nota y sin ' +
  'NE queda PENDIENTE y bloquea la calificacion final. Marcar NE borra la nota ' +
  'de ese periodo; escribir una nota retira el NE.';

export interface EstudiantePrimData {
  estudiante: {
    id: number;
    nombre_completo: string;
    no_lista?: number | null;
    retirado?: boolean;
    fecha_retiro?: string | null;
    motivo_retiro?: string | null;
  };
  competencias: CompetenciaPrim[];
}

export type CampoEditable = 'p1' | 'rp1' | 'p2' | 'rp2' | 'p3' | 'rp3' | 'p4' | 'rp4';

export const CAMPOS_PERIODOS: Array<{ periodo: number; p: CampoEditable; rp: CampoEditable }> = [
  { periodo: 1, p: 'p1', rp: 'rp1' },
  { periodo: 2, p: 'p2', rp: 'rp2' },
  { periodo: 3, p: 'p3', rp: 'rp3' },
  { periodo: 4, p: 'p4', rp: 'rp4' },
];

// Corte de aprobación en primaria (oficial MINERD)
export const MINIMO_APROBATORIO_PRIMARIA = 65;

// Umbral para habilitar la recuperación (RP) de un período.
// Por defecto = mínimo aprobatorio (65). Si el colegio usa un umbral más
// exigente (ej. 70), cambiar SOLO este valor.
export const UMBRAL_RP_PRIMARIA = 65;

// ¿Debe habilitarse la casilla RP de un período?
// Solo si el P existe y está por debajo del umbral (el estudiante no aprobó
// ese período y necesita recuperar). Si ya aprobó, no hay nada que recuperar.
export function rpHabilitado(pValor: number | null): boolean {
  return pValor != null && pValor < UMBRAL_RP_PRIMARIA;
}

// P2A-R1: en 1ro y 2do la recuperación pedagógica del período es CUALITATIVA,
// así que la columna RP no existe para esos grados — ni en la pantalla ni en
// el Informe de Aprendizaje ni en el Registro. La modalidad llega resuelta
// desde el servidor; aquí no se deduce del nombre del grado.
export type ModalidadRecuperacion = 'cualitativa' | 'cuantitativa';

export function admiteRpNumerica(modalidad: ModalidadRecuperacion | null | undefined): boolean {
  return modalidad !== 'cualitativa';
}

// Qué se escribe en RP. El texto anterior —«se toma el mayor de los dos»—
// invitaba a escribir los puntos ganados; la norma dice que la columna
// guarda la calificación FINAL del período después de la recuperación.
export const AYUDA_RP_PRIMARIA =
  'RP = calificación final del período después de la recuperación pedagógica. ' +
  'No escriba los puntos ganados; escriba la nota final resultante del período.';

export const AVISO_RP_CUALITATIVA =
  'La recuperación pedagógica del período se registra de forma cualitativa desde ' +
  'Recuperación Primaria: aspectos no logrados, estrategias y evidencias, y si la ' +
  'competencia quedó lograda o no lograda. No lleva nota.';

// Nombres oficiales de las competencias fundamentales (primaria)
export const NOMBRES_COMPETENCIAS_PRIM: Record<number, string> = {
  1: 'Comunicativa',
  2: 'Pensamiento Lógico, Creativo y Crítico',
  3: 'Ética y Ciudadana',
};

// Valor efectivo del período: RP REEMPLAZA a P (R2-A2).
// La norma dice que la recuperación se asienta en su columna "siendo esta
// última la calificación final del período": RP no compite con P, lo
// sustituye. Antes era max(P, RP), que se desviaba en cuanto RP era menor.
// Espejo exacto de calculo_primaria.valor_periodo_primaria del backend.
export function valorPeriodoEfectivo(comp: CompetenciaPrim, periodo: number): number | null {
  const p = comp[`p${periodo}` as keyof CompetenciaPrim] as number | null;
  const rp = comp[`rp${periodo}` as keyof CompetenciaPrim] as number | null;
  if (rp != null) return rp;
  return p;
}

// Final de competencia = promedio de los períodos evaluados (regla NE)
export function finalCompetencia(comp: CompetenciaPrim): number | null {
  const vals: number[] = [];
  for (let per = 1; per <= 4; per++) {
    const v = valorPeriodoEfectivo(comp, per);
    if (v != null) vals.push(v);
  }
  if (vals.length === 0) return null;
  return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
}
