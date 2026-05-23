import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Card, Select, Spinner, Badge, Alert } from '../../components/ui';
import { BarChart3, Users, GraduationCap, TrendingUp, BookOpen, CalendarCheck } from 'lucide-react';
import { NivelTabs } from '../../components/NivelTabs';
import { useNivelesActivos, Nivel } from '../../hooks/useNivelesActivos';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  LineChart,
  Line
} from 'recharts';
import { colorPorCurso } from '../../utils/colorPorCurso';

interface EstadisticasGenerales {
  total_estudiantes: number;
  total_profesores: number;
  total_cursos: number;
  promedio_general: number;
  asistencia_promedio: number;
  reportes_pendientes: number;
  casos_psicologia: number;
}

interface EstadisticaCurso {
  id: number;
  nombre: string;
  tanda?: string;
  estudiantes: number;
  promedio: number;
  aprobados: number;
  reprobados: number;
  sin_calificar?: number;
}

interface EstadisticaAsignatura {
  id: number;
  nombre: string;
  promedio: number;
  aprobados: number;
  reprobados: number;
}

export const EstadisticasPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [periodo, setPeriodo] = useState<number>(0);
  
  const [generales, setGenerales] = useState<EstadisticasGenerales | null>(null);
  const [estadisticasCursos, setEstadisticasCursos] = useState<EstadisticaCurso[]>([]);
  const [estadisticasAsignaturas, setEstadisticasAsignaturas] = useState<EstadisticaAsignatura[]>([]);
  const [estadoEstudiantes, setEstadoEstudiantes] = useState<any[]>([]);
  const niveles = useNivelesActivos();
  const [nivelFiltro, setNivelFiltro] = useState<Nivel | 'todos'>('todos');

  useEffect(() => {
    loadData();
  }, [periodo, nivelFiltro]);

  const loadData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (periodo > 0) params.append('periodo', String(periodo));
      if (nivelFiltro !== 'todos') params.append('nivel', nivelFiltro);
      const qs = params.toString() ? `?${params.toString()}` : '';
      const [statsRes, graficosRes, cursosRes, asignaturasRes] = await Promise.all([
        api.get('/dashboard/stats'),
        api.get('/dashboard/graficos'),
        api.get(`/estadisticas/cursos${qs}`).catch(() => ({ data: [] })),
        api.get(`/estadisticas/asignaturas${qs}`).catch(() => ({ data: [] }))
      ]);

      setGenerales({
        total_estudiantes: statsRes.data.estudiantes || 0,
        total_profesores: statsRes.data.profesores || 0,
        total_cursos: statsRes.data.cursos || 0,
        promedio_general: graficosRes.data.promedios_por_grado?.length > 0
          ? graficosRes.data.promedios_por_grado.reduce((a: number, b: any) => a + b.promedio, 0) / graficosRes.data.promedios_por_grado.length
          : 0,
        asistencia_promedio: graficosRes.data.asistencia_resumen?.porcentaje_asistencia || 0,
        reportes_pendientes: statsRes.data.reportes_pendientes || 0,
        casos_psicologia: statsRes.data.casos_psicologia || 0
      });

      setEstadoEstudiantes(graficosRes.data.estado_estudiantes || []);
      setEstadisticasCursos(cursosRes.data || []);
      setEstadisticasAsignaturas(asignaturasRes.data || []);

    } catch (e) {
      console.error('Error cargando estadísticas:', e);
      setError('Error al cargar las estadísticas');
    } finally {
      setLoading(false);
    }
  };

  const getColorByValue = (value: number, type: 'promedio' | 'asistencia' = 'promedio') => {
    const threshold = type === 'promedio' ? { high: 85, mid: 70 } : { high: 90, mid: 80 };
    if (value >= threshold.high) return 'text-emerald-600';
    if (value >= threshold.mid) return 'text-amber-600';
    return 'text-red-600';
  };

  const getBgColorByValue = (value: number) => {
    if (value >= 85) return 'bg-emerald-500';
    if (value >= 70) return 'bg-amber-500';
    return 'bg-red-500';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BarChart3 className="text-blue-600" />
            Estadísticas y Reportes
          </h1>
          <p className="text-gray-500">Análisis del rendimiento académico</p>
        </div>
        <Select
          value={periodo.toString()}
          onChange={e => setPeriodo(parseInt(e.target.value))}
          options={[
            { value: '0', label: 'Año Completo' },
            { value: '1', label: 'P1 - Comunicativa' },
            { value: '2', label: 'P2 - Pensamiento Lógico' },
            { value: '3', label: 'P3 - Científica y Tecnológica' },
            { value: '4', label: 'P4 - Desarrollo Personal' },
          ]}
        />
      </div>

      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Tabs por nivel educativo */}
      <NivelTabs value={nivelFiltro} onChange={setNivelFiltro} showAll hint="Las estadísticas de primaria usan calificaciones por competencias (C1, C2, C3)." />

      {/* KPIs Principales */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
          <GraduationCap size={32} className="mx-auto text-blue-500 mb-2" />
          <div className="text-3xl font-bold text-blue-600">{generales?.total_estudiantes || 0}</div>
          <p className="text-gray-500 text-sm">Estudiantes</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
          <TrendingUp size={32} className="mx-auto text-emerald-500 mb-2" />
          <div className={`text-3xl font-bold ${getColorByValue(generales?.promedio_general || 0)}`}>
            {(generales?.promedio_general || 0).toFixed(1)}%
          </div>
          <p className="text-gray-500 text-sm">Promedio General</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
          <CalendarCheck size={32} className="mx-auto text-purple-500 mb-2" />
          <div className={`text-3xl font-bold ${getColorByValue(generales?.asistencia_promedio || 0, 'asistencia')}`}>
            {(generales?.asistencia_promedio || 0).toFixed(1)}%
          </div>
          <p className="text-gray-500 text-sm">Asistencia</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-4 text-center">
          <Users size={32} className="mx-auto text-amber-500 mb-2" />
          <div className="text-3xl font-bold text-amber-600">{generales?.total_profesores || 0}</div>
          <p className="text-gray-500 text-sm">Profesores</p>
        </div>
      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Estado de Estudiantes */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Users className="text-blue-600" />
            Estado de Estudiantes
          </h3>
          {estadoEstudiantes.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={estadoEstudiantes}
                  dataKey="cantidad"
                  nameKey="nombre"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ nombre, cantidad }) => `${nombre}: ${cantidad}`}
                >
                  {estadoEstudiantes.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Pie>
                <Legend layout="horizontal" verticalAlign="bottom" align="center" />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-400">
              No hay datos de estudiantes
            </div>
          )}
        </div>

        {/* Rendimiento por Curso (Gráfico) */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
            <BookOpen className="text-emerald-600" />
            Promedio por Curso
          </h3>
          {estadisticasCursos.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={estadisticasCursos}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="nombre" tick={{ fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(value: number) => [`${value.toFixed(1)}%`, 'Promedio']} />
                <Bar dataKey="promedio" radius={[4, 4, 0, 0]}>
                  {estadisticasCursos.map((curso) => (
                    <Cell key={`bar-${curso.id}`} fill={colorPorCurso(curso.id)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[250px] flex items-center justify-center text-gray-400">
              No hay datos de cursos
            </div>
          )}
        </div>
      </div>

      {/* Tablas Detalladas */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Rendimiento por Curso */}
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="p-4 border-b">
            <h3 className="font-bold text-gray-800">Rendimiento por Curso</h3>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {estadisticasCursos.length > 0 ? (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-gray-600">Curso</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Est.</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Prom.</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Apr.</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Rep.</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Pend.</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {estadisticasCursos.map((curso) => (
                    <tr key={curso.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2 font-medium">
                        {curso.nombre}
                        {curso.tanda && (
                          <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${curso.tanda.includes('Matutina') ? 'bg-amber-100 text-amber-700' : 'bg-purple-100 text-purple-700'}`}>
                            {curso.tanda.includes('Matutina') ? '☀️' : '🌙'}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-center">{curso.estudiantes}</td>
                      <td className="px-4 py-2 text-center">
                        <span className={`font-bold ${getColorByValue(curso.promedio)}`}>
                          {curso.promedio.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-center text-emerald-600 font-medium">{curso.aprobados}</td>
                      <td className="px-4 py-2 text-center text-red-600 font-medium">{curso.reprobados}</td>
                      <td className="px-4 py-2 text-center text-gray-400">
                        {(curso.sin_calificar ?? 0) > 0 ? curso.sin_calificar : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-8 text-center text-gray-400">
                No hay datos disponibles
              </div>
            )}
          </div>
        </div>

        {/* Rendimiento por Asignatura */}
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="p-4 border-b">
            <h3 className="font-bold text-gray-800">Rendimiento por Asignatura</h3>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {estadisticasAsignaturas.length > 0 ? (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-gray-600">Asignatura</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Prom.</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Apr.</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-600">Rep.</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {estadisticasAsignaturas.map((asig) => (
                    <tr key={asig.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2 font-medium">{asig.nombre}</td>
                      <td className="px-4 py-2 text-center">
                        <span className={`font-bold ${getColorByValue(asig.promedio)}`}>
                          {asig.promedio.toFixed(1)}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-center text-emerald-600">{asig.aprobados}%</td>
                      <td className="px-4 py-2 text-center text-red-600">{asig.reprobados}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-8 text-center text-gray-400">
                No hay datos disponibles
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Indicadores adicionales */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h4 className="font-medium text-gray-600 mb-2">Reportes Pendientes</h4>
          <p className="text-3xl font-bold text-amber-600">{generales?.reportes_pendientes || 0}</p>
          <p className="text-xs text-gray-400 mt-1">Conducta por revisar</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h4 className="font-medium text-gray-600 mb-2">Casos Psicología</h4>
          <p className="text-3xl font-bold text-purple-600">{generales?.casos_psicologia || 0}</p>
          <p className="text-xs text-gray-400 mt-1">En seguimiento</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h4 className="font-medium text-gray-600 mb-2">Total Cursos</h4>
          <p className="text-3xl font-bold text-blue-600">{generales?.total_cursos || 0}</p>
          <p className="text-xs text-gray-400 mt-1">Activos</p>
        </div>
      </div>
    </div>
  );
};

export default EstadisticasPage;
