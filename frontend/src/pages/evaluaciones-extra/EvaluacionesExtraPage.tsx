import { useState, useEffect, useMemo } from 'react';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import {
  AlertTriangle, Filter, Save, RefreshCw, BookOpen, Users, CheckCircle,
  ChevronDown,
} from 'lucide-react';
import { Button, Alert, Spinner } from '../../components/ui';

// ═══════════════════════════════════════════════════════════════════════
// Evaluaciones Extra (Cross-curso)
//
// Una sola pantalla atiende dos casos de uso porque el backend ya filtra
// por rol automáticamente:
//
//   - PROFESOR: ve solo sus pendientes en cursos+asignaturas donde está
//     asignado. Puede cargar la nota directamente (cumple #2 del v2.13).
//   - DIRECCIÓN/COORDINADOR: ve TODO el colegio. NO puede cargar notas
//     (eso es trabajo del profesor), pero sí gestiona, filtra, exporta
//     y monitorea quién está atascado en qué fase (cumple #3 del v2.13).
//
// Endpoint: GET /api/calificaciones-secundaria/pendientes-evaluacion-extra
//   Query params (todos opcionales): curso_id, asignatura_id, tipo
//   Filtrado automático por profesor: backend solo devuelve cursos
//     donde el profesor tiene AsignacionProfesor.
// ═══════════════════════════════════════════════════════════════════════

interface PendienteExtra {
  evaluacion_id: number;
  estudiante_id: number;
  estudiante_nombre: string;
  curso: string | null;
  curso_id: number | null;
  asignatura_id: number;
  asignatura_nombre: string | null;
  cf_original: number | null;
  fase_pendiente: 'completiva' | 'extraordinaria' | 'especial';
  cec: number | null;
  completiva_final: number | null;
  ceex: number | null;
  extraordinaria_final: number | null;
  ce: number | null;
  especial_final: number | null;
}

// Estado de inputs de notas pendientes (key = `${estId}-${asigId}` por si
// el estudiante tiene varias materias reprobadas — son filas diferentes)
type DraftMap = Record<string, string>;

const FASE_LABEL: Record<string, { label: string; color: string; descripcion: string }> = {
  completiva: {
    label: 'Completiva',
    color: 'bg-amber-100 text-amber-800 border-amber-300',
    descripcion: '50% CF + 50% C.E.C.',
  },
  extraordinaria: {
    label: 'Extraordinaria',
    color: 'bg-orange-100 text-orange-800 border-orange-300',
    descripcion: '30% CF + 70% C.E.EX',
  },
  especial: {
    label: 'Especial',
    color: 'bg-red-100 text-red-800 border-red-300',
    descripcion: 'CF + C.E. (suma simple)',
  },
};

export const EvaluacionesExtraPage = () => {
  const { user } = useAuth();
  const esProfesor = user?.role === 'profesor';
  const puedeEditar = esProfesor;

  const [pendientes, setPendientes] = useState<PendienteExtra[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning' | 'info'; texto: string } | null>(null);

  // Filtros (opcionales — el backend acepta query params)
  const [filtroFase, setFiltroFase] = useState<'todos' | 'completiva' | 'extraordinaria' | 'especial'>('todos');
  const [filtroCurso, setFiltroCurso] = useState<string>('');       // texto libre — filtra cliente-side por nombre de curso
  const [filtroAsignatura, setFiltroAsignatura] = useState<string>(''); // idem

  // Borradores de notas (uno por fila pendiente)
  const [drafts, setDrafts] = useState<DraftMap>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const keyFila = (p: PendienteExtra) => `${p.estudiante_id}-${p.asignatura_id}`;

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroFase]);

  const cargar = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filtroFase !== 'todos') params.tipo = filtroFase;
      const res = await api.get('/calificaciones-secundaria/pendientes-evaluacion-extra', { params });
      setPendientes(res.data.pendientes || []);
      setDrafts({});
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error cargando pendientes' });
    } finally {
      setLoading(false);
    }
  };

  const refrescar = async () => {
    setRefreshing(true);
    await cargar();
    setRefreshing(false);
  };

  const guardarNota = async (p: PendienteExtra) => {
    const k = keyFila(p);
    const valorStr = drafts[k];
    if (!valorStr) {
      setMensaje({ tipo: 'error', texto: 'Indique la nota' });
      return;
    }
    const nota = parseFloat(valorStr);
    if (Number.isNaN(nota) || nota < 0 || nota > 100) {
      setMensaje({ tipo: 'error', texto: 'La nota debe estar entre 0 y 100' });
      return;
    }
    setSavingKey(k);
    try {
      await api.post('/calificaciones-secundaria/evaluacion-extra', {
        estudiante_id: p.estudiante_id,
        asignatura_id: p.asignatura_id,
        tipo: p.fase_pendiente,
        nota,
      });
      setMensaje({
        tipo: 'success',
        texto: `${p.estudiante_nombre} — ${p.asignatura_nombre}: ${p.fase_pendiente} registrada`,
      });
      // Recargar pendientes (la fila puede desaparecer si aprobó, o cambiar de fase)
      await cargar();
    } catch (err: any) {
      setMensaje({
        tipo: 'error',
        texto: err.response?.data?.error || 'Error al guardar evaluación',
      });
    } finally {
      setSavingKey(null);
    }
  };

  // Filtros cliente-side (curso/asignatura por nombre)
  const pendientesFiltrados = useMemo(() => {
    return pendientes.filter(p => {
      if (filtroCurso) {
        const nombre = (p.curso || '').toLowerCase();
        if (!nombre.includes(filtroCurso.toLowerCase())) return false;
      }
      if (filtroAsignatura) {
        const nombre = (p.asignatura_nombre || '').toLowerCase();
        if (!nombre.includes(filtroAsignatura.toLowerCase())) return false;
      }
      return true;
    });
  }, [pendientes, filtroCurso, filtroAsignatura]);

  // KPIs por fase
  const kpisPorFase = useMemo(() => {
    const conteo = { completiva: 0, extraordinaria: 0, especial: 0 };
    for (const p of pendientesFiltrados) {
      conteo[p.fase_pendiente]++;
    }
    return conteo;
  }, [pendientesFiltrados]);

  // Agrupar por curso para la vista (más fácil de leer cuando son muchos)
  const agrupadoPorCurso = useMemo(() => {
    const grupos: Record<string, PendienteExtra[]> = {};
    for (const p of pendientesFiltrados) {
      const k = p.curso || 'Sin curso';
      if (!grupos[k]) grupos[k] = [];
      grupos[k].push(p);
    }
    // Ordenar cada grupo por fase (especial primero = más urgente) y luego por nombre
    const ordenFase = { especial: 0, extraordinaria: 1, completiva: 2 } as Record<string, number>;
    for (const k of Object.keys(grupos)) {
      grupos[k].sort((a, b) => {
        const diff = (ordenFase[a.fase_pendiente] ?? 99) - (ordenFase[b.fase_pendiente] ?? 99);
        if (diff !== 0) return diff;
        return a.estudiante_nombre.localeCompare(b.estudiante_nombre);
      });
    }
    return grupos;
  }, [pendientesFiltrados]);

  const cursosOrdenados = Object.keys(agrupadoPorCurso).sort();

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <AlertTriangle className="text-amber-600" />
            Evaluaciones Extra
          </h1>
          <p className="text-gray-500 mt-1 text-sm">
            {esProfesor
              ? 'Sus estudiantes con CF < 70 que necesitan completiva, extraordinaria o especial. Solo se permite la fase pendiente según la cascada MINERD.'
              : 'Estudiantes del colegio con evaluaciones extra pendientes (solo lectura). Los profesores asignados son quienes cargan las notas.'
            }
          </p>
        </div>
        <Button variant="secondary" onClick={refrescar} loading={refreshing} icon={<RefreshCw size={16} />}>
          Refrescar
        </Button>
      </div>

      {mensaje && (
        <Alert variant={mensaje.tipo === 'info' ? 'info' : mensaje.tipo} onClose={() => setMensaje(null)}>
          {mensaje.texto}
        </Alert>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <div className="flex items-center gap-3">
            <Users size={28} className="text-gray-400" />
            <div>
              <p className="text-2xl font-bold text-gray-800">{pendientesFiltrados.length}</p>
              <p className="text-xs text-gray-500">Total Pendientes</p>
            </div>
          </div>
        </div>
        <div className="bg-amber-50 rounded-xl shadow-sm border border-amber-200 p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle size={28} className="text-amber-600" />
            <div>
              <p className="text-2xl font-bold text-amber-700">{kpisPorFase.completiva}</p>
              <p className="text-xs text-amber-700">Completiva</p>
            </div>
          </div>
        </div>
        <div className="bg-orange-50 rounded-xl shadow-sm border border-orange-200 p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle size={28} className="text-orange-600" />
            <div>
              <p className="text-2xl font-bold text-orange-700">{kpisPorFase.extraordinaria}</p>
              <p className="text-xs text-orange-700">Extraordinaria</p>
            </div>
          </div>
        </div>
        <div className="bg-red-50 rounded-xl shadow-sm border border-red-200 p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle size={28} className="text-red-600" />
            <div>
              <p className="text-2xl font-bold text-red-700">{kpisPorFase.especial}</p>
              <p className="text-xs text-red-700">Especial</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter size={18} className="text-gray-400" />
          <span className="font-medium text-gray-700">Filtros</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Fase</label>
            <div className="relative">
              <select
                value={filtroFase}
                onChange={e => setFiltroFase(e.target.value as any)}
                className="w-full appearance-none pl-3 pr-9 py-2 border rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-400"
              >
                <option value="todos">Todas las fases</option>
                <option value="completiva">Completiva</option>
                <option value="extraordinaria">Extraordinaria</option>
                <option value="especial">Especial</option>
              </select>
              <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Curso</label>
            <input
              type="text"
              value={filtroCurso}
              onChange={e => setFiltroCurso(e.target.value)}
              placeholder="Filtrar por curso..."
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Asignatura</label>
            <input
              type="text"
              value={filtroAsignatura}
              onChange={e => setFiltroAsignatura(e.target.value)}
              placeholder="Filtrar por materia..."
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-400"
            />
          </div>
        </div>
      </div>

      {/* Tabla agrupada por curso */}
      {loading ? (
        <div className="flex justify-center py-10"><Spinner size="lg" /></div>
      ) : pendientesFiltrados.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
          <CheckCircle size={48} className="mx-auto text-green-300 mb-4" />
          <p className="text-gray-700 font-medium">No hay evaluaciones extra pendientes</p>
          <p className="text-gray-500 text-sm mt-1">
            {esProfesor
              ? 'Todos sus estudiantes con CF < 70 ya tienen sus evaluaciones registradas, o aún no hay reprobados.'
              : 'Todos los estudiantes con CF < 70 ya tienen sus evaluaciones registradas.'
            }
          </p>
        </div>
      ) : (
        cursosOrdenados.map(curso => {
          const filas = agrupadoPorCurso[curso];
          return (
            <div key={curso} className="bg-white rounded-xl shadow-sm border overflow-hidden">
              <div className="px-4 py-3 bg-gradient-to-r from-slate-50 to-slate-100 border-b flex items-center gap-2">
                <BookOpen size={18} className="text-slate-600" />
                <h3 className="font-bold text-slate-800">{curso}</h3>
                <span className="ml-auto text-xs text-slate-500">
                  {filas.length} estudiante{filas.length === 1 ? '' : 's'} pendiente{filas.length === 1 ? '' : 's'}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-xs">
                      <th rowSpan={2} className="px-2 py-1 text-left bg-gray-50 border font-medium text-gray-600 min-w-[160px]">Estudiante</th>
                      <th rowSpan={2} className="px-2 py-1 text-left bg-gray-50 border font-medium text-gray-600">Asignatura</th>
                      <th rowSpan={2} className="px-2 py-1 text-center bg-gray-100 border font-bold">C.F.</th>
                      <th rowSpan={2} className="px-2 py-1 text-center bg-gray-50 border font-medium text-gray-600">Fase</th>
                      <th colSpan={4} className="px-2 py-1 text-center bg-amber-50 text-amber-800 border font-bold">CALIF. COMPLETIVA</th>
                      <th colSpan={4} className="px-2 py-1 text-center bg-orange-50 text-orange-800 border font-bold">CALIF. EXTRAORDINARIA</th>
                      <th colSpan={3} className="px-2 py-1 text-center bg-red-50 text-red-800 border font-bold">EVAL. ESPECIAL</th>
                      {puedeEditar && <th rowSpan={2} className="px-2 py-1 text-center bg-gray-50 border font-medium text-gray-600 min-w-[160px]">Cargar nota</th>}
                    </tr>
                    <tr className="text-[11px] text-gray-600">
                      <th className="px-1 py-1 text-center bg-amber-50 border">50% C.F.</th>
                      <th className="px-1 py-1 text-center bg-amber-50 border">C.E.C.</th>
                      <th className="px-1 py-1 text-center bg-amber-50 border">50% C.E.C.</th>
                      <th className="px-1 py-1 text-center bg-amber-100 border font-bold">C.C.F.</th>
                      <th className="px-1 py-1 text-center bg-orange-50 border">30% C.F.</th>
                      <th className="px-1 py-1 text-center bg-orange-50 border">C.E.EX</th>
                      <th className="px-1 py-1 text-center bg-orange-50 border">70% C.E.EX</th>
                      <th className="px-1 py-1 text-center bg-orange-100 border font-bold">C.EX.F.</th>
                      <th className="px-1 py-1 text-center bg-red-50 border">C.F.</th>
                      <th className="px-1 py-1 text-center bg-red-50 border">C.E.</th>
                      <th className="px-1 py-1 text-center bg-red-100 border font-bold">Final</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filas.map(p => {
                      const k = keyFila(p);
                      const fase = p.fase_pendiente;
                      const faseInfo = FASE_LABEL[fase];
                      const cf = p.cf_original;
                      const pct = (v: number | null | undefined, f: number) =>
                        v == null ? '—' : (Math.round(v * f * 10) / 10).toFixed(1).replace(/\.0$/, '');
                      const cfRed = cf != null ? Math.round(cf) : null;
                      return (
                        <tr key={k} className="border-b hover:bg-gray-50">
                          <td className="px-2 py-1 border font-medium text-gray-800">{p.estudiante_nombre}</td>
                          <td className="px-2 py-1 border text-gray-700">{p.asignatura_nombre || '—'}</td>
                          <td className="px-2 py-1 border text-center font-bold text-red-600">
                            {cf != null ? Math.round(cf) : '—'}
                          </td>
                          <td className="px-2 py-1 border text-center">
                            <span
                              className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${faseInfo.color}`}
                              title={faseInfo.descripcion}
                            >
                              {faseInfo.label}
                            </span>
                          </td>
                          {/* COMPLETIVA: 50%CF | CEC | 50%CEC | CCF */}
                          <td className="px-1 py-1 border text-center bg-amber-50/40">{pct(cf, 0.5)}</td>
                          <td className="px-1 py-1 border text-center">{p.cec?.toFixed(0) ?? '—'}</td>
                          <td className="px-1 py-1 border text-center bg-amber-50/40">{pct(p.cec, 0.5)}</td>
                          <td className="px-1 py-1 border text-center bg-amber-100/50 font-bold">{p.completiva_final?.toFixed(0) ?? '—'}</td>
                          {/* EXTRAORDINARIA: 30%CF | CEEX | 70%CEEX | CEXF */}
                          <td className="px-1 py-1 border text-center bg-orange-50/40">{p.completiva_final != null ? pct(cf, 0.3) : '—'}</td>
                          <td className="px-1 py-1 border text-center">{p.ceex?.toFixed(0) ?? '—'}</td>
                          <td className="px-1 py-1 border text-center bg-orange-50/40">{pct(p.ceex, 0.7)}</td>
                          <td className="px-1 py-1 border text-center bg-orange-100/50 font-bold">{p.extraordinaria_final?.toFixed(0) ?? '—'}</td>
                          {/* ESPECIAL: CF + CE = Final */}
                          <td className="px-1 py-1 border text-center bg-red-50/40">{p.extraordinaria_final != null && cfRed != null ? cfRed : '—'}</td>
                          <td className="px-1 py-1 border text-center">{p.ce?.toFixed(0) ?? '—'}</td>
                          <td className="px-1 py-1 border text-center bg-red-100/50 font-bold">{p.especial_final?.toFixed(0) ?? '—'}</td>
                          {puedeEditar && (
                            <td className="px-2 py-1 border">
                              <div className="flex gap-1 items-center justify-center">
                                <input
                                  type="number"
                                  min={0}
                                  max={100}
                                  step={0.01}
                                  placeholder={fase === 'especial' && cfRed != null ? `máx ${100 - cfRed}` : `Nota ${fase}`}
                                  title={fase === 'especial' ? 'C.E. complementario: puntos que se SUMAN al C.F.' : undefined}
                                  value={drafts[k] || ''}
                                  onChange={e => setDrafts(prev => ({ ...prev, [k]: e.target.value }))}
                                  className="w-20 px-2 py-1 text-center border rounded text-sm focus:ring-1 focus:ring-blue-400"
                                />
                                <Button
                                  variant="success"
                                  size="sm"
                                  loading={savingKey === k}
                                  onClick={() => guardarNota(p)}
                                  icon={<Save size={14} />}
                                >
                                  Guardar
                                </Button>
                              </div>
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })
      )}

      {/* Leyenda al pie */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-900">
        <p className="font-semibold mb-2">Cascada MINERD oficial (orden estricto):</p>
        <ol className="list-decimal ml-5 space-y-1">
          <li><strong>Completiva</strong>: aplicable si CF &lt; 70. Final = ROUND(50% × CF + 50% × C.E.C., 0). Si ≥ 70, aprueba.</li>
          <li><strong>Extraordinaria</strong>: aplicable si Completiva &lt; 70. Final = ROUND(30% × CF + 70% × C.E.EX, 0). Si ≥ 70, aprueba.</li>
          <li><strong>Especial</strong>: aplicable si Extraordinaria &lt; 70. Final = CF + C.E. (suma simple). Si ≥ 70, aprueba; si no, reprueba el año.</li>
        </ol>
        <p className="mt-2 text-blue-700">No se puede saltar fases — el backend valida la cascada en cada guardado.</p>
      </div>
    </div>
  );
};

export default EvaluacionesExtraPage;
