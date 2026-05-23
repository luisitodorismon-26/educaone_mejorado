// Tipos compartidos por las tabs de AcademicoSecundariaPage v2.13

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

export interface CompetenciaSec {
  competencia_numero: number;
  p1: number | null; rp1: number | null;
  p2: number | null; rp2: number | null;
  p3: number | null; rp3: number | null;
  p4: number | null; rp4: number | null;
  promedio_competencia: number | null;
}

export interface ARPeriodo {
  a: number;
  r: number;
  pendientes: number;
}

export interface EvaluacionExtra {
  id?: number;
  cf_original: number | null;
  cec: number | null;
  completiva_final: number | null;
  ceex: number | null;
  extraordinaria_final: number | null;
  ce: number | null;
  especial_final: number | null;
  condicion_final: string | null;
  nota_final: number | null;
  fase_pendiente: 'completiva' | 'extraordinaria' | 'especial' | null;
}

export interface EstudianteData {
  estudiante: {
    id: number;
    nombre_completo: string;
    retirado?: boolean;
    fecha_retiro?: string | null;
    motivo_retiro?: string | null;
  };
  competencias: Record<number, CompetenciaSec>;
  pc_por_periodo: { pc1: number | null; pc2: number | null; pc3: number | null; pc4: number | null };
  a_r_por_periodo: { p1: ARPeriodo; p2: ARPeriodo; p3: ARPeriodo; p4: ARPeriodo };
  cf: number | null;
  literal: string | null;
  evaluacion_extra: EvaluacionExtra | null;
}

export type CampoEditable = 'p1' | 'rp1' | 'p2' | 'rp2' | 'p3' | 'rp3' | 'p4' | 'rp4';

export const CAMPOS_PERIODOS: Array<{ periodo: number; p: CampoEditable; rp: CampoEditable }> = [
  { periodo: 1, p: 'p1', rp: 'rp1' },
  { periodo: 2, p: 'p2', rp: 'rp2' },
  { periodo: 3, p: 'p3', rp: 'rp3' },
  { periodo: 4, p: 'p4', rp: 'rp4' },
];

export const NOMBRES_COMPETENCIAS: Record<number, string> = {
  1: 'Competencia 1',
  2: 'Competencia 2',
  3: 'Competencia 3',
  4: 'Competencia 4',
};

// Helpers compartidos
export const getLiteral = (n: number | null): string => {
  if (n === null) return '—';
  if (n >= 90) return 'A';
  if (n >= 80) return 'B';
  if (n >= 70) return 'C';
  return 'F';
};

export const getNotaClass = (n: number | null) => {
  if (n === null) return '';
  if (n >= 90) return 'text-green-600';
  if (n >= 80) return 'text-blue-600';
  if (n >= 70) return 'text-amber-600';
  return 'text-red-600';
};
