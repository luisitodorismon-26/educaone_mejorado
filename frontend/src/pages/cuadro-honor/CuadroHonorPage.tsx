import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Award, Download, Search, Medal, Trophy } from 'lucide-react';
import { Select, Button, Alert } from '../../components/ui';

// ═══════════════════════════════════════════════════════════════
// CUADRO DE HONOR — v2.13.41
// Reconocimientos anuales: promedio de los CF de todas las
// asignaturas completas. Excelencia (95+) y Honor (90+).
// ═══════════════════════════════════════════════════════════════

interface EstudianteHonor {
  posicion: number;
  estudiante_id: number;
  nombre: string;
  curso: string;
  promedio: number;
  nivel: 'excelencia' | 'honor';
  asignaturas_con_cf: number;
  oficial: boolean;
}

interface CuadroHonorData {
  ano_escolar: string;
  modo: 'oficial' | 'proyeccion';
  total: number;
  excelencia: number;
  honor: number;
  estudiantes: EstudianteHonor[];
}

interface Curso {
  id: number;
  nombre_completo?: string;
  nombre: string;
}

export const CuadroHonorPage: React.FC = () => {
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [cursoId, setCursoId] = useState<string>('');
  const [data, setData] = useState<CuadroHonorData | null>(null);
  const [loading, setLoading] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    api.get('/cursos').then(r => setCursos(r.data || [])).catch(() => {});
  }, []);

  const cargar = async () => {
    setLoading(true); setError(''); setData(null);
    try {
      const q = cursoId ? `?curso_id=${cursoId}` : '';
      const res = await api.get(`/estadisticas/cuadro-honor${q}`);
      setData(res.data);
    } catch (e: any) {
      setError(e.response?.data?.error || 'Error al cargar el cuadro de honor');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); /* carga inicial: todo el colegio */ // eslint-disable-next-line
  }, []);

  const descargarPDF = async () => {
    setDescargando(true); setError('');
    try {
      const q = cursoId ? `?curso_id=${cursoId}` : '';
      const response = await api.get(`/estadisticas/cuadro-honor/pdf${q}`, { responseType: 'blob' });
      if (response.data.type === 'application/json' || response.data.size < 300) {
        const texto = await response.data.text();
        try { const j = JSON.parse(texto); throw new Error(j.error || 'Error'); }
        catch (e: any) { throw new Error(e?.message || 'El servidor no devolvió un PDF'); }
      }
      const dlUrl = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = dlUrl;
      link.setAttribute('download', 'Cuadro_de_Honor.pdf');
      document.body.appendChild(link); link.click(); link.remove();
      window.URL.revokeObjectURL(dlUrl);
    } catch (e: any) {
      setError(e?.message || 'Error al descargar el PDF');
    } finally {
      setDescargando(false);
    }
  };

  const BadgeNivel = ({ nivel }: { nivel: 'excelencia' | 'honor' }) =>
    nivel === 'excelencia' ? (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
        <Trophy size={12} /> EXCELENCIA (95+)
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-green-100 text-green-800 border border-green-300">
        <Medal size={12} /> HONOR (90+)
      </span>
    );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Award className="text-amber-500" /> Cuadro de Honor
        </h1>
        {data && (
          <Button onClick={descargarPDF} variant="primary" loading={descargando} icon={<Download size={16} />}>
            PDF para el acto
          </Button>
        )}
      </div>
      <p className="text-sm text-gray-500 -mt-2">
        Reconocimientos del año{data ? ` ${data.ano_escolar}` : ''}: promedio general de las Calificaciones Finales (solo asignaturas con las 4 competencias completas).
      </p>

      {error && <Alert variant="error" onClose={() => setError('')}>{error}</Alert>}

      {data && (
        data.modo === 'proyeccion' ? (
          <div className="bg-amber-50 border border-amber-300 rounded-lg px-4 py-2.5 flex items-center gap-2">
            <span className="text-lg">⏳</span>
            <p className="text-sm text-amber-800">
              <strong>PROYECCIÓN EN CURSO</strong> — calculada con las notas cargadas hasta hoy. Al completarse los CF del año, pasa automáticamente a modo OFICIAL.
            </p>
          </div>
        ) : (
          <div className="bg-green-50 border border-green-300 rounded-lg px-4 py-2.5 flex items-center gap-2">
            <span className="text-lg">✅</span>
            <p className="text-sm text-green-800">
              <strong>OFICIAL</strong> — promedios calculados con las Calificaciones Finales completas del año. Listo para el acto de reconocimiento.
            </p>
          </div>
        )
      )}

      {/* Filtro */}
      <div className="bg-white rounded-xl shadow-sm border p-4 flex items-end gap-3 flex-wrap">
        <div className="min-w-[220px]">
          <label className="block text-xs text-gray-500 mb-1">Curso</label>
          <Select value={cursoId} onChange={e => setCursoId(e.target.value)}>
            <option value="">Todo el colegio</option>
            {cursos.map(c => <option key={c.id} value={c.id}>{c.nombre_completo || c.nombre}</option>)}
          </Select>
        </div>
        <Button onClick={cargar} variant="primary" loading={loading} icon={<Search size={16} />}>Ver</Button>
      </div>

      {/* Resumen */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
            <p className="text-3xl font-bold text-blue-700">{data.total}</p>
            <p className="text-xs text-gray-500 uppercase mt-1">En el cuadro de honor</p>
          </div>
          <div className="bg-amber-50 rounded-xl shadow-sm border border-amber-200 p-4 text-center">
            <p className="text-3xl font-bold text-amber-600">{data.excelencia}</p>
            <p className="text-xs text-amber-700 uppercase mt-1 flex items-center justify-center gap-1"><Trophy size={12} /> Excelencia (95+)</p>
          </div>
          <div className="bg-green-50 rounded-xl shadow-sm border border-green-200 p-4 text-center">
            <p className="text-3xl font-bold text-green-600">{data.honor}</p>
            <p className="text-xs text-green-700 uppercase mt-1 flex items-center justify-center gap-1"><Medal size={12} /> Honor (90-94)</p>
          </div>
        </div>
      )}

      {/* Tabla */}
      {data && data.estudiantes.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-center font-medium text-gray-600 w-16">Pos.</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Estudiante</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Curso</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Promedio</th>
                  <th className="px-3 py-2 text-center font-medium text-gray-600">Nivel</th>
                </tr>
              </thead>
              <tbody>
                {data.estudiantes.map(e => (
                  <tr key={e.estudiante_id} className="border-b hover:bg-gray-50">
                    <td className="px-3 py-2 text-center font-bold text-gray-700">
                      {e.posicion <= 3 ? ['🥇', '🥈', '🥉'][e.posicion - 1] : e.posicion}
                    </td>
                    <td className="px-3 py-2 font-medium text-gray-800">{e.nombre}</td>
                    <td className="px-3 py-2 text-gray-600">{e.curso}</td>
                    <td className={`px-3 py-2 text-center font-bold text-lg ${e.nivel === 'excelencia' ? 'text-amber-600' : 'text-green-600'}`}>
                      {e.promedio}
                      {!e.oficial && <span className="block text-[9px] font-normal text-amber-600">proyección</span>}
                    </td>
                    <td className="px-3 py-2 text-center"><BadgeNivel nivel={e.nivel} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data && data.estudiantes.length === 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
          <Award size={48} className="mx-auto text-gray-200 mb-3" />
          <p className="text-gray-600 font-medium">Aún no hay estudiantes con promedio de 90 o más</p>
          <p className="text-sm text-gray-400 mt-1">
            El promedio anual requiere asignaturas con las 4 competencias completas (CF calculado).
          </p>
        </div>
      )}
    </div>
  );
};
