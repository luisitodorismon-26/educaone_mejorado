import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { Spinner, Button } from '../../components/ui';
import { ExternalLink, BookOpen, AlertTriangle, CalendarCheck, GraduationCap } from 'lucide-react';

// ════════════════════════════════════════════════════════════════════
// EstudianteKPIs v2.13.2
// Sub-componente del modal de detalle de estudiante.
// Carga KPIs académicos al montarse y los muestra como cards + listado
// de asignaturas con botón "Ver ficha completa" en cada una.
//
// Comportamiento por nivel:
//   - Secundaria: muestra CF por asignatura + asistencia + cascada extra
//   - Primaria/legacy: muestra solo nota promedio + asistencia (modelo viejo)
//   - Sin curso/sin notas: muestra mensaje informativo
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudianteId: number;
  cursoId?: number | null;
  esSecundaria?: boolean;
}

interface CalifSec {
  asignatura_id: number;
  asignatura_nombre: string;
  cf: number | null;
  literal: string | null;
  evaluacion_extra: {
    fase_pendiente: string | null;
    nota_final: number | null;
  } | null;
}

export const EstudianteKPIs: React.FC<Props> = ({ estudianteId, cursoId, esSecundaria }) => {
  const [loading, setLoading] = useState(false);
  const [calificaciones, setCalificaciones] = useState<CalifSec[]>([]);
  const [pctAsistencia, setPctAsistencia] = useState<number | null>(null);
  const [pctAsistenciaMes, setPctAsistenciaMes] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cursoId) cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estudianteId, cursoId]);

  const cargar = async () => {
    if (!cursoId) return;
    setLoading(true);
    setError(null);
    try {
      // Asistencia del estudiante
      try {
        const asistRes = await api.get(`/asistencia/resumen-periodos/curso/${cursoId}`);
        const miAsist = (asistRes.data || []).find((a: any) => a.estudiante_id === estudianteId);
        if (miAsist) {
          setPctAsistencia(miAsist.pct_asistencia_anual ?? null);
          setPctAsistenciaMes(miAsist.pct_asistencia_mes ?? null);
        }
      } catch {
        // Asistencia no es crítica, seguimos
      }

      // Solo intentamos cargar CFs si es secundaria
      if (esSecundaria) {
        try {
          // Necesitamos todas las asignaturas del curso
          const asigsRes = await api.get('/asignaturas');
          const asignaturas: { id: number; nombre: string }[] = (asigsRes.data || []).filter((a: any) => a.activo !== false);
          
          const cfsPromises = asignaturas.map(async (asig) => {
            try {
              const res = await api.get(`/calificaciones-secundaria/curso/${cursoId}/asignatura/${asig.id}`);
              const todosEst = res.data.calificaciones || [];
              const miData = todosEst.find((d: any) => d.estudiante.id === estudianteId);
              if (!miData) return null;
              return {
                asignatura_id: asig.id,
                asignatura_nombre: asig.nombre,
                cf: miData.cf,
                literal: miData.literal,
                evaluacion_extra: miData.evaluacion_extra,
              } as CalifSec;
            } catch {
              return null;
            }
          });
          
          const cfs = (await Promise.all(cfsPromises)).filter((c): c is CalifSec => c !== null);
          setCalificaciones(cfs);
        } catch {
          // No se pudieron cargar CFs
        }
      }
    } catch (err: any) {
      setError('Error cargando información académica');
    } finally {
      setLoading(false);
    }
  };

  if (!cursoId) {
    return (
      <div className="border-t pt-3">
        <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide">Resumen académico</h4>
        <p className="text-sm text-gray-500 italic">Sin curso asignado</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="border-t pt-3 flex justify-center py-4">
        <Spinner />
      </div>
    );
  }

  // Calcular KPIs
  const conCF = calificaciones.filter(c => c.cf !== null);
  const cfPromedio = conCF.length > 0
    ? Math.round(conCF.reduce((acc, c) => acc + (c.cf ?? 0), 0) / conCF.length)
    : null;
  const aprobadas = conCF.filter(c => (c.cf ?? 0) >= 70).length;
  const reprobadas = conCF.length - aprobadas;
  const pendientesExtra = calificaciones.filter(c => c.evaluacion_extra?.fase_pendiente).length;

  const colorPct = (pct: number | null) => {
    if (pct === null) return 'text-gray-400';
    if (pct >= 95) return 'text-green-600';
    if (pct >= 85) return 'text-amber-600';
    return 'text-red-600';
  };

  const colorCF = (cf: number | null) => {
    if (cf === null) return 'text-gray-400';
    if (cf >= 90) return 'text-green-600';
    if (cf >= 80) return 'text-blue-600';
    if (cf >= 70) return 'text-amber-600';
    return 'text-red-600';
  };

  return (
    <div className="border-t pt-3">
      <h4 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wide flex items-center gap-2">
        <GraduationCap size={16} />
        Resumen académico
      </h4>

      {error && <p className="text-sm text-red-500 mb-2">{error}</p>}

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <div className="bg-gray-50 rounded-lg p-2.5 text-center">
          <p className={`text-xl font-bold ${colorCF(cfPromedio)}`}>
            {cfPromedio !== null ? cfPromedio : '—'}
          </p>
          <p className="text-[10px] text-gray-500 uppercase">CF Promedio</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-2.5 text-center">
          <p className="text-xl font-bold text-gray-700">
            <span className="text-green-600">{aprobadas}</span>
            <span className="text-gray-300 mx-1">/</span>
            <span className="text-red-600">{reprobadas}</span>
          </p>
          <p className="text-[10px] text-gray-500 uppercase">Aprob/Reprob</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-2.5 text-center">
          <p className={`text-xl font-bold ${colorPct(pctAsistenciaMes)}`}>
            {pctAsistenciaMes !== null ? `${pctAsistenciaMes}%` : '—'}
          </p>
          <p className="text-[10px] text-gray-500 uppercase">Asist. mes</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-2.5 text-center">
          <p className={`text-xl font-bold ${pendientesExtra > 0 ? 'text-amber-600' : 'text-gray-300'}`}>
            {pendientesExtra}
          </p>
          <p className="text-[10px] text-gray-500 uppercase">Cascada pend.</p>
        </div>
      </div>

      {/* Asignaturas con botón "Ver ficha" */}
      {esSecundaria && calificaciones.length > 0 && (
        <div className="bg-gray-50 rounded-lg p-2">
          <p className="text-[10px] text-gray-500 uppercase mb-2 px-1">Asignaturas</p>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {calificaciones.map(c => (
              <Link
                key={c.asignatura_id}
                to={`/academico/estudiante/${estudianteId}/asignatura/${c.asignatura_id}`}
                className="flex items-center gap-2 px-2 py-1.5 bg-white rounded hover:bg-blue-50 group transition-colors"
              >
                <BookOpen size={14} className="text-gray-400 group-hover:text-blue-600 flex-shrink-0" />
                <span className="text-xs font-medium flex-1 truncate">{c.asignatura_nombre}</span>
                {c.evaluacion_extra?.fase_pendiente && (
                  <AlertTriangle size={12} className="text-amber-500" />
                )}
                <span className={`text-xs font-bold w-8 text-right ${colorCF(c.cf)}`}>
                  {c.cf !== null ? c.cf : '—'}
                </span>
                <ExternalLink size={11} className="text-gray-300 group-hover:text-blue-600" />
              </Link>
            ))}
          </div>
        </div>
      )}

      {!esSecundaria && (
        <p className="text-xs text-gray-500 italic">
          Vista detallada disponible solo para estudiantes de secundaria. Para primaria use la pantalla Calificaciones.
        </p>
      )}
    </div>
  );
};
