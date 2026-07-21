import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { BookOpen, AlertTriangle, CalendarCheck, FileText } from 'lucide-react';
import { Button, Spinner } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import { EstudianteData, Curso, Asignatura } from './secundaria/tipos';
import { TabNotasRegulares } from './secundaria/TabNotasRegulares';
import { TabNotasPorPeriodo } from './secundaria/TabNotasPorPeriodo';
import { TabEvaluacionesExtra } from './secundaria/TabEvaluacionesExtra';
import { TabAsistencia } from './secundaria/TabAsistencia';
import { TabBoletin } from './secundaria/TabBoletin';

// ════════════════════════════════════════════════════════════════════
// AcademicoSecundariaPage v2.13 — Shell con tabs (Opción A)
// ════════════════════════════════════════════════════════════════════

interface Props {
  cursoId: number;
  asignaturaId: number;
  curso: Curso | null;
  asignatura: Asignatura | null;
  onVolver: () => void;
}

type TabId = 'notas' | 'extra' | 'asistencia' | 'boletin';

export const AcademicoSecundariaPage: React.FC<Props> = ({ cursoId, asignaturaId, curso, asignatura, onVolver }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const esProfesor = user?.role === 'profesor';
  const puedeEditar = esProfesor;

  const [estudiantes, setEstudiantes] = useState<EstudianteData[]>([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<TabId>('notas');
  // Modo de carga de notas: 'competencia' (por competencia) o 'periodo' (por período)
  const [modoNotas, setModoNotas] = useState<'competencia' | 'periodo'>('competencia');
  // Estado de cierre de períodos (para bloquear casillas de períodos cerrados)
  const [periodosCerrados, setPeriodosCerrados] = useState<Record<string, boolean>>({ p1: false, p2: false, p3: false, p4: false });

  useEffect(() => {
    if (cursoId && asignaturaId) cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoId, asignaturaId]);

  const cargar = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/calificaciones-secundaria/curso/${cursoId}/asignatura/${asignaturaId}`);
      setEstudiantes(res.data.calificaciones || []);
      if (res.data.periodos_cerrados) {
        setPeriodosCerrados(res.data.periodos_cerrados);
      }
    } catch (err: any) {
      console.error('Error cargando calificaciones', err);
    } finally {
      setLoading(false);
    }
  };

  const pendientesExtra = useMemo(
    () => estudiantes.filter(e => e.evaluacion_extra?.fase_pendiente && !e.estudiante.retirado).length,
    [estudiantes]
  );

  const conCF = estudiantes.filter(e => e.cf !== null && !e.estudiante.retirado).length;

  const abrirFicha = (estudianteId: number) => {
    navigate(`/academico/estudiante/${estudianteId}/asignatura/${asignaturaId}`);
  };

  if (loading) return <div className="flex justify-center py-10"><Spinner /></div>;

  const tabs: Array<{ id: TabId; label: string; icon: React.ReactNode; badge?: number; badgeColor?: string }> = [
    { id: 'notas', label: 'Notas regulares', icon: <BookOpen size={16} /> },
    {
      id: 'extra',
      label: 'Evaluaciones extra',
      icon: <AlertTriangle size={16} />,
      badge: pendientesExtra > 0 ? pendientesExtra : undefined,
      badgeColor: 'bg-red-500',
    },
    { id: 'asistencia', label: 'Asistencia', icon: <CalendarCheck size={16} /> },
    {
      id: 'boletin',
      label: 'Ver boletín',
      icon: <FileText size={16} />,
      badge: conCF > 0 ? conCF : undefined,
      badgeColor: 'bg-blue-500',
    },
  ];

  // v2.16: planilla de calificaciones imprimible (llena o en blanco según lo cargado)
  const imprimirPlanilla = () => {
    const token = localStorage.getItem('token');
    const url = `${(import.meta as any).env.VITE_API_URL || ''}/api/imprimir/planilla-calificaciones/${cursoId}/${asignaturaId}`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => (r.ok ? r.blob() : Promise.reject(r)))
      .then(blob => {
        const u = URL.createObjectURL(blob);
        window.open(u, '_blank');
      })
      .catch(() => alert('No se pudo generar la planilla'));
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="text-blue-600" />
            Calificaciones Secundaria
          </h2>
          <p className="text-sm text-gray-500">{curso?.nombre_completo} — {asignatura?.nombre}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            icon={<span>🖨️</span>}
            onClick={imprimirPlanilla}
            title="Planilla imprimible: con las notas cargadas, o en blanco para trabajar a lápiz"
          >
            Planilla
          </Button>
          <Button variant="secondary" onClick={onVolver}>Volver</Button>
        </div>
      </div>

      <div className="border-b flex gap-1 overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors whitespace-nowrap ${
              tab === t.id
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-300'
            }`}
          >
            {t.icon}
            {t.label}
            {t.badge !== undefined && (
              <span className={`${t.badgeColor || 'bg-gray-500'} text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center`}>
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      <div>
        {tab === 'notas' && (
          <div className="space-y-4">
            {/* Selector de modo de carga: Por Competencia / Por Período */}
            <div className="flex gap-2 bg-gray-100 p-1 rounded-lg w-fit">
              <button
                onClick={() => setModoNotas('competencia')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition ${
                  modoNotas === 'competencia'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                Por Competencia
              </button>
              <button
                onClick={() => setModoNotas('periodo')}
                className={`px-4 py-2 rounded-md text-sm font-medium transition ${
                  modoNotas === 'periodo'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                Por Período
              </button>
            </div>

            {modoNotas === 'competencia' ? (
              <TabNotasRegulares
                estudiantes={estudiantes}
                asignaturaId={asignaturaId}
                puedeEditar={puedeEditar}
                onReload={cargar}
                onAbrirFicha={abrirFicha}
                periodosCerrados={periodosCerrados}
              />
            ) : (
              <TabNotasPorPeriodo
                estudiantes={estudiantes}
                asignaturaId={asignaturaId}
                puedeEditar={puedeEditar}
                onReload={cargar}
                periodosCerrados={periodosCerrados}
              />
            )}
          </div>
        )}
        {tab === 'extra' && (
          <TabEvaluacionesExtra
            estudiantes={estudiantes}
            asignaturaId={asignaturaId}
            puedeEditar={puedeEditar}
            onReload={cargar}
            onAbrirFicha={abrirFicha}
          />
        )}
        {tab === 'asistencia' && (
          <TabAsistencia cursoId={cursoId} onAbrirFicha={abrirFicha} />
        )}
        {tab === 'boletin' && (
          <TabBoletin
            estudiantes={estudiantes}
            cursoId={cursoId}
            nombreCurso={curso?.nombre_completo || asignatura?.nombre || 'Curso'}
          />
        )}
      </div>
    </div>
  );
};

export default AcademicoSecundariaPage;
