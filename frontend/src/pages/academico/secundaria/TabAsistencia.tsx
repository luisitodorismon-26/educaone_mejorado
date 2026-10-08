import { useState, useEffect, Fragment } from 'react';
import api from '../../../services/api';
import { CalendarCheck, ExternalLink } from 'lucide-react';
import { Spinner, Alert, Button } from '../../../components/ui';
import { Link } from 'react-router-dom';

// ════════════════════════════════════════════════════════════════════
// TAB ASISTENCIA
// Resumen P1-P4 por estudiante con totales anuales.
// Solo lectura. Para registrar asistencia el profesor va a /asistencia.
// ════════════════════════════════════════════════════════════════════

interface ResumenAsistencia {
  estudiante_id: number;
  estudiante: string;
  periodos: {
    p1?: { asistencia: number; ausencia: number; pct_asistencia_anual: number | null; pct_ausencia_anual: number | null };
    p2?: { asistencia: number; ausencia: number; pct_asistencia_anual: number | null; pct_ausencia_anual: number | null };
    p3?: { asistencia: number; ausencia: number; pct_asistencia_anual: number | null; pct_ausencia_anual: number | null };
    p4?: { asistencia: number; ausencia: number; pct_asistencia_anual: number | null; pct_ausencia_anual: number | null };
  };
  total_asistencia: number;
  total_ausencia: number;
  pct_asistencia_anual: number | null;
  // v2.13.1 mensual
  mes?: number;
  ano_calendario?: number;
  asistencia_mes?: number;
  ausencia_mes?: number;
  tardanza_mes?: number;
  pct_asistencia_mes?: number | null;
  // Asistencia canónica: misma fuente que el boletín y el motor.
  // El % solo existe con cobertura completa; si no, viene null (N/D).
  dias_lectivos?: number;
  dias_computados?: number;
  sin_dato?: number;
  cobertura_completa?: boolean;
  dias_lectivos_mes?: number;
  dias_computados_mes?: number;
  sin_dato_mes?: number;
}

interface Props {
  cursoId: number;
  onAbrirFicha?: (estudianteId: number) => void;
}

export const TabAsistencia: React.FC<Props> = ({ cursoId, onAbrirFicha }) => {
  const [datos, setDatos] = useState<ResumenAsistencia[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoId]);

  const cargar = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/asistencia/resumen-periodos/curso/${cursoId}`);
      setDatos(res.data || []);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error cargando asistencia');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="flex justify-center py-10"><Spinner /></div>;
  if (error) return <Alert variant="error">{error}</Alert>;

  if (datos.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
        <CalendarCheck size={48} className="mx-auto text-gray-300 mb-3" />
        <p className="text-gray-700 font-medium">No hay datos de asistencia para este curso</p>
        <p className="text-sm text-gray-500 mt-1">
          Cuando los profesores registren asistencia diaria en /asistencia, los totales aparecerán aquí.
        </p>
      </div>
    );
  }

  // Totales del curso. El % del curso solo existe si TODOS sus estudiantes
  // tienen cobertura completa; si no, N/D (la misma regla que el boletín).
  const sumaAsis = datos.reduce((acc, d) => acc + d.total_asistencia, 0);
  const sumaAus = datos.reduce((acc, d) => acc + d.total_ausencia, 0);
  const sumaLect = datos.reduce((acc, d) => acc + (d.dias_lectivos || 0), 0);
  const sumaDato = datos.reduce((acc, d) => acc + (d.dias_computados || 0), 0);
  const pctCurso = datos.every(d => d.pct_asistencia_anual !== null) && sumaLect > 0
    ? Math.round((sumaAsis / sumaLect) * 100) : null;

  const sumaAsisMes = datos.reduce((acc, d) => acc + (d.asistencia_mes || 0), 0);
  const sumaLectMes = datos.reduce((acc, d) => acc + (d.dias_lectivos_mes || 0), 0);
  const pctMesCurso = datos.every(d => d.pct_asistencia_mes !== null && d.pct_asistencia_mes !== undefined) && sumaLectMes > 0
    ? Math.round((sumaAsisMes / sumaLectMes) * 100) : null;
  const pctTexto = (pct: number | null | undefined) =>
    pct !== null && pct !== undefined ? `${Math.round(pct)}%` : 'N/D';
  
  // Nombre del mes actual en español (o el que vino del backend)
  const mesActual = datos[0]?.mes || (new Date().getMonth() + 1);
  const nombresMeses = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const nombreMesActual = nombresMeses[mesActual - 1] || '—';

  const colorPct = (pct: number | null | undefined) => {
    if (pct === null || pct === undefined) return 'text-gray-400';
    if (pct >= 95) return 'text-green-600';
    if (pct >= 85) return 'text-amber-600';
    return 'text-red-600';
  };

  return (
    <div className="space-y-4">
      {/* Header con CTA a /asistencia */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-blue-800">
          Resumen P1-P4 + % mensual ({nombreMesActual}). Para registrar asistencia diaria ir a la pantalla principal.
        </p>
        <Link to="/asistencia">
          <Button variant="secondary" size="sm" icon={<ExternalLink size={14} />}>
            Registrar asistencia
          </Button>
        </Link>
      </div>

      {/* Cobertura: si faltan listas, el % no se puede calcular (N/D). */}
      {sumaLect > sumaDato && (
        <div className="bg-amber-50 border-l-4 border-amber-400 p-3 rounded">
          <p className="text-sm text-amber-900">
            <strong>Cobertura: {sumaDato} de {sumaLect} días-estudiante registrados.</strong>{' '}
            Mientras falten listas, el porcentaje aparece como <strong>N/D</strong>: un día sin lista no cuenta
            como asistencia ni como falta.
          </p>
        </div>
      )}

      {/* v2.13.4: Leyenda explicativa */}
      <details className="bg-gray-50 border border-gray-200 rounded-lg text-sm">
        <summary className="cursor-pointer px-4 py-2 font-medium text-gray-700 hover:bg-gray-100 rounded-lg">
          ¿Cómo se calculan estos números?
        </summary>
        <div className="px-4 pb-3 pt-1 text-gray-600 space-y-2">
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <p className="font-medium text-gray-700 mb-1">Columnas A y F</p>
              <ul className="list-disc list-inside text-xs space-y-0.5">
                <li><span className="text-green-700 font-semibold">A</span> = días que el estudiante asistió</li>
                <li><span className="text-red-700 font-semibold">F</span> = días que faltó (ausente)</li>
                <li>Hay 4 períodos (P1, P2, P3, P4) + total anual</li>
              </ul>
            </div>
            <div>
              <p className="font-medium text-gray-700 mb-1">Porcentajes</p>
              <ul className="list-disc list-inside text-xs space-y-0.5">
                <li>Días lectivos = días hábiles desde el inicio del año del colegio (o desde el alta del estudiante), sin feriados</li>
                <li><strong>% Anual</strong> = asistencias / días lectivos del año, solo si todos tienen lista</li>
                <li><strong>% Mes</strong> = lo mismo, solo del mes</li>
                <li>Si falta alguna lista → <strong>N/D</strong> (es el mismo cálculo del boletín)</li>
              </ul>
            </div>
          </div>
          <div className="text-xs text-gray-500">
            <span className="inline-block w-3 h-3 bg-green-500 rounded-full mr-1 align-middle"></span>
            <span className="mr-3">≥ 95% Excelente</span>
            <span className="inline-block w-3 h-3 bg-amber-500 rounded-full mr-1 align-middle"></span>
            <span className="mr-3">85-94% Aceptable</span>
            <span className="inline-block w-3 h-3 bg-red-500 rounded-full mr-1 align-middle"></span>
            <span>&lt; 85% Bajo</span>
          </div>
        </div>
      </details>

      {/* KPIs del curso */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-gray-800">{datos.length}</p>
          <p className="text-xs text-gray-500">Estudiantes</p>
        </div>
        <div className="bg-green-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-green-600">{sumaAsis}</p>
          <p className="text-xs text-green-600">Total asistencias</p>
        </div>
        <div className="bg-red-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-red-600">{sumaAus}</p>
          <p className="text-xs text-red-600">Total ausencias</p>
        </div>
        <div className="bg-blue-50 rounded-lg p-3 text-center">
          <p className={`text-2xl font-bold ${colorPct(pctCurso)}`}>
            {pctTexto(pctCurso)}
          </p>
          <p className="text-xs text-blue-600">% asistencia anual</p>
        </div>
        <div className="bg-indigo-50 rounded-lg p-3 text-center">
          <p className={`text-2xl font-bold ${colorPct(pctMesCurso)}`}>
            {pctTexto(pctMesCurso)}
          </p>
          <p className="text-xs text-indigo-600">% este mes ({nombreMesActual})</p>
        </div>
      </div>

      {/* Tabla con desglose P1-P4 */}
      <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-3 py-2 text-left font-medium text-gray-600">Estudiante</th>
                {[1, 2, 3, 4].map(p => (
                  <th key={p} className="px-3 py-2 text-center font-medium text-gray-600" colSpan={2}>
                    P{p}
                  </th>
                ))}
                <th className="px-3 py-2 text-center font-medium text-blue-700 bg-blue-50" colSpan={2}>
                  Año
                </th>
                <th className="px-3 py-2 text-center font-medium text-gray-600">% Anual</th>
                <th className="px-3 py-2 text-center font-medium text-indigo-700 bg-indigo-50">
                  % Mes ({nombreMesActual})
                </th>
              </tr>
              <tr className="bg-gray-50 text-xs">
                <th></th>
                {[1, 2, 3, 4].map(p => (
                  <Fragment key={p}>
                    <th className="px-1 py-1 text-center font-normal text-green-600">A</th>
                    <th className="px-1 py-1 text-center font-normal text-red-600">F</th>
                  </Fragment>
                ))}
                <th className="px-1 py-1 text-center font-normal text-green-700 bg-blue-50">A</th>
                <th className="px-1 py-1 text-center font-normal text-red-700 bg-blue-50">F</th>
                <th></th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {datos.map(d => (
                <tr key={d.estudiante_id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-2">
                    {onAbrirFicha ? (
                      <button
                        type="button"
                        onClick={() => onAbrirFicha(d.estudiante_id)}
                        className="font-medium text-blue-700 hover:text-blue-900 hover:underline text-left"
                      >
                        {d.estudiante}
                      </button>
                    ) : (
                      <span className="font-medium">{d.estudiante}</span>
                    )}
                  </td>
                  {(['p1', 'p2', 'p3', 'p4'] as const).map(pk => {
                    const p = d.periodos[pk];
                    return (
                      <Fragment key={pk}>
                        <td className="px-1 py-2 text-center text-gray-700">{p?.asistencia ?? '—'}</td>
                        <td className="px-1 py-2 text-center text-gray-500">{p?.ausencia ?? '—'}</td>
                      </Fragment>
                    );
                  })}
                  <td className="px-1 py-2 text-center font-medium text-green-700 bg-blue-50">{d.total_asistencia}</td>
                  <td className="px-1 py-2 text-center font-medium text-red-700 bg-blue-50">{d.total_ausencia}</td>
                  <td
                    className={`px-3 py-2 text-center font-bold ${colorPct(d.pct_asistencia_anual)}`}
                    title={`Cobertura: ${d.dias_computados ?? 0} de ${d.dias_lectivos ?? 0} días registrados`}
                  >
                    {pctTexto(d.pct_asistencia_anual)}
                  </td>
                  <td
                    className={`px-3 py-2 text-center font-bold bg-indigo-50 ${colorPct(d.pct_asistencia_mes)}`}
                    title={`Cobertura de ${nombreMesActual}: ${d.dias_computados_mes ?? 0} de ${d.dias_lectivos_mes ?? 0} días registrados`}
                  >
                    {pctTexto(d.pct_asistencia_mes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
