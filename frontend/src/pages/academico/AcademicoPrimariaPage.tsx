import { useState, useEffect } from 'react';
import api from '../../services/api';
import { BookOpen, Backpack, Download } from 'lucide-react';
import { Button, Spinner, Alert } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import { EstudiantePrimData, Curso, Asignatura } from './primaria/tipos';
import { TabNotasPorCompetencia } from './primaria/TabNotasPorCompetencia';
import { TabNotasPorPeriodo } from './primaria/TabNotasPorPeriodo';

// ════════════════════════════════════════════════════════════════════
// AcademicoPrimariaPage v2.13.45 — Shell con dos vistas (espejo secundaria)
// Carril SEPARADO de secundaria. 3 competencias, corte 65, badge PRIMARIA.
// ════════════════════════════════════════════════════════════════════

interface Props {
  cursoId: number;
  asignaturaId: number;
  curso: Curso | null;
  asignatura: Asignatura | null;
  onVolver: () => void;
}

export const AcademicoPrimariaPage: React.FC<Props> = ({ cursoId, asignaturaId, curso, asignatura, onVolver }) => {
  const { user } = useAuth();
  const puedeEditar = user?.role === 'profesor';

  const [estudiantes, setEstudiantes] = useState<EstudiantePrimData[]>([]);
  const [numCompetencias, setNumCompetencias] = useState(3);
  const [loading, setLoading] = useState(false);
  const [modoNotas, setModoNotas] = useState<'competencia' | 'periodo'>('competencia');
  const [descargando, setDescargando] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);

  // Informes de Aprendizaje (boletín oficial de primaria) de todo el curso
  const descargarBoletines = async () => {
    setDescargando(true);
    setMensaje(null);
    try {
      const res = await api.get(`/boletines-primaria/curso/${cursoId}/pdf`, { responseType: 'blob' });
      if (res.data.type === 'application/json' || res.data.size < 300) {
        const texto = await res.data.text();
        try {
          const j = JSON.parse(texto);
          setMensaje(j.error || 'No se pudo generar el PDF');
          return;
        } catch { /* no era JSON */ }
      }
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Informes_Aprendizaje_${(curso?.nombre_completo || 'curso').replace(/ /g, '_')}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setMensaje(e?.response?.data?.error || 'Error al descargar los Informes de Aprendizaje');
    } finally {
      setDescargando(false);
    }
  };

  useEffect(() => {
    if (cursoId && asignaturaId) cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoId, asignaturaId]);

  const cargar = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/calificaciones-primaria/curso/${cursoId}/asignatura/${asignaturaId}`);
      setEstudiantes(res.data.calificaciones || []);
      setNumCompetencias(res.data.num_competencias || 3);
    } catch (err: any) {
      console.error('Error cargando calificaciones de primaria', err);
    } finally {
      setLoading(false);
    }
  };

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

  if (loading) return <div className="flex justify-center py-10"><Spinner /></div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="text-blue-600" />
            Calificaciones Primaria
            <span className="inline-flex items-center gap-1 bg-blue-100 text-blue-700 text-xs font-semibold px-2.5 py-1 rounded-full">
              <Backpack size={13} /> PRIMARIA
            </span>
          </h2>
          <p className="text-sm text-gray-500">
            {curso?.nombre_completo} — {asignatura?.nombre}
            <span className="text-gray-400"> · Nivel primario · {numCompetencias} competencias · aprueba con 65</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            icon={<Download size={16} />}
            loading={descargando}
            onClick={descargarBoletines}
            title="Informes de Aprendizaje de todo el curso"
          >
            Informes de Aprendizaje
          </Button>
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

      {mensaje && <Alert variant="error" onClose={() => setMensaje(null)}>{mensaje}</Alert>}

      {/* Selector de modo de carga: Por Competencia / Por Período */}
      <div className="flex gap-2 bg-gray-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setModoNotas('competencia')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition ${
            modoNotas === 'competencia' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          Por Competencia
        </button>
        <button
          onClick={() => setModoNotas('periodo')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition ${
            modoNotas === 'periodo' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          Por Período
        </button>
      </div>

      {modoNotas === 'competencia' ? (
        <TabNotasPorCompetencia
          estudiantes={estudiantes}
          asignaturaId={asignaturaId}
          numCompetencias={numCompetencias}
          puedeEditar={puedeEditar}
          onReload={cargar}
        />
      ) : (
        <TabNotasPorPeriodo
          estudiantes={estudiantes}
          asignaturaId={asignaturaId}
          numCompetencias={numCompetencias}
          puedeEditar={puedeEditar}
          onReload={cargar}
        />
      )}
    </div>
  );
};

export default AcademicoPrimariaPage;
