import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { NivelTabs } from '../../components/NivelTabs';
import { useNivelesActivos, Nivel } from '../../hooks/useNivelesActivos';

interface Estudiante {
  id: number;
  nombre_completo: string;
  no_lista: number;
  // Flags de retiro (vienen del backend en GET /asistencia/curso/{id})
  retirado?: boolean;
  fecha_retiro?: string | null;
  motivo_retiro?: string | null;
}

interface Asignatura {
  id: number;
  nombre: string;
}

interface AsistenciaItem {
  estudiante: Estudiante;
  asistencia: {
    estado: string | null;
    observacion: string | null;
    registrado_por?: string;
  } | null;
}

export const AsistenciaPage = () => {
  const { user } = useAuth();
  const [cursos, setCursos] = useState<any[]>([]);
  const [asignaturas, setAsignaturas] = useState<Asignatura[]>([]);
  const [cursoId, setCursoId] = useState<number>(0);
  const [asignaturaId, setAsignaturaId] = useState<number>(0);
  const [fecha, setFecha] = useState(new Date().toISOString().split('T')[0]);
  const [asistencias, setAsistencias] = useState<AsistenciaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingAsignaturas, setLoadingAsignaturas] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [buscarEstudiante, setBuscarEstudiante] = useState('');
  const niveles = useNivelesActivos();
  const [nivelFiltro, setNivelFiltro] = useState<Nivel | 'todos'>('todos');
  // Mantener siempre 'todos' por defecto al cargar — solo cambia si el usuario elige tab

  // Solo profesores pueden marcar asistencia
  const esProfesor = user?.role === 'profesor';
  const puedeEditar = esProfesor;

  // Cargar cursos según rol
  useEffect(() => {
    const cargarCursos = async () => {
      try {
        const cursosRes = await api.get('/cursos');
        if (esProfesor) {
          const res = await api.get('/dashboard/profesor');
          const cursosAsignadosIds = new Set(res.data.cursos_asignados?.map((c: any) => c.curso_id) || []);
          setCursos((cursosRes.data || []).filter((c: any) => cursosAsignadosIds.has(c.id)));
        } else {
          setCursos(cursosRes.data || []);
        }
      } catch (err) {
        console.error('Error cargando cursos:', err);
        setError('Error al cargar cursos');
      } finally {
        setLoading(false);
      }
    };
    cargarCursos();
  }, [esProfesor]);

  // Detectar si el curso actual es de primaria
  const cursoActual = cursos.find(c => c.id === cursoId);
  const esPrimaria = cursoActual?.nivel === 'primaria';

  // Cargar asignaturas cuando cambia el curso (solo si NO es primaria)
  useEffect(() => {
    if (cursoId > 0 && !esPrimaria) {
      cargarAsignaturas();
    } else {
      setAsignaturas([]);
      setAsignaturaId(0);
    }
  }, [cursoId, esPrimaria]);

  // Cargar asistencia cuando cambia curso, asignatura o fecha
  useEffect(() => {
    // Primaria: cargar cuando hay curso y fecha (sin asignatura)
    // Secundaria: cargar cuando hay curso, asignatura y fecha
    if (cursoId > 0 && (esPrimaria || asignaturaId > 0)) {
      cargarAsistencia();
    }
  }, [cursoId, asignaturaId, fecha, esPrimaria]);

  const cargarAsignaturas = async () => {
    setLoadingAsignaturas(true);
    try {
      const res = await api.get(`/mis-asignaturas/${cursoId}`);
      setAsignaturas(res.data || []);
      if (res.data && res.data.length === 1) {
        setAsignaturaId(res.data[0].id);
      } else {
        setAsignaturaId(0);
      }
    } catch (err) {
      console.error('Error cargando asignaturas:', err);
      setAsignaturas([]);
    } finally {
      setLoadingAsignaturas(false);
    }
  };

  const cargarAsistencia = async () => {
    setLoading(true);
    setError('');
    try {
      // Primaria: sin asignatura (asistencia diaria general)
      // Secundaria: con asignatura específica
      const url = esPrimaria
        ? `/asistencia/curso/${cursoId}?fecha=${fecha}`
        : `/asistencia/curso/${cursoId}?fecha=${fecha}&asignatura_id=${asignaturaId}`;
      const res = await api.get(url);
      setAsistencias(res.data.asistencias || []);
    } catch (err) {
      console.error('Error cargando asistencia:', err);
      setError('Error al cargar asistencia');
      setAsistencias([]);
    } finally {
      setLoading(false);
    }
  };

  const marcarAsistencia = async (estudianteId: number, estado: string) => {
    if (!puedeEditar) {
      setError('Solo profesores pueden registrar');
      return;
    }
    // Secundaria requiere asignatura, primaria no
    if (!esPrimaria && !asignaturaId) {
      setError('Seleccione una materia');
      return;
    }

    setError('');
    setSaving(true);
    
    try {
      // Si ya tiene ese estado, desmarcar
      const asistenciaActual = asistencias.find(a => a.estudiante.id === estudianteId);
      if (asistenciaActual?.asistencia?.estado === estado) {
        const delUrl = esPrimaria
          ? `/asistencia/${estudianteId}?fecha=${fecha}`
          : `/asistencia/${estudianteId}?fecha=${fecha}&asignatura_id=${asignaturaId}`;
        await api.delete(delUrl);
        setAsistencias(prev => prev.map(a => {
          if (a.estudiante.id === estudianteId) {
            return { ...a, asistencia: null };
          }
          return a;
        }));
        setSuccess('✓ Desmarcado');
        setTimeout(() => setSuccess(''), 1000);
        setSaving(false);
        return;
      }
      
      const payload: any = {
        estudiante_id: estudianteId,
        curso_id: cursoId,
        fecha: fecha,
        estado: estado
      };
      if (!esPrimaria) payload.asignatura_id = asignaturaId;
      
      await api.post('/asistencia', payload);
      
      setAsistencias(prev => prev.map(a => {
        if (a.estudiante.id === estudianteId) {
          return { ...a, asistencia: { estado, observacion: '', registrado_por: user?.nombre } };
        }
        return a;
      }));
      
      setSuccess('✓');
      setTimeout(() => setSuccess(''), 1000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const marcarTodos = async (estado: string) => {
    if (!puedeEditar) return;
    if (!esPrimaria && !asignaturaId) return;

    setSaving(true);
    setError('');
    
    try {
      const data = asistencias.map(a => ({
        estudiante_id: a.estudiante.id,
        curso_id: cursoId,
        estado: estado
      }));
      
      const payload: any = { fecha, asistencias: data };
      if (!esPrimaria) payload.asignatura_id = asignaturaId;
      
      await api.post('/asistencia/masivo', payload);
      
      setAsistencias(prev => prev.map(a => ({
        ...a,
        asistencia: { estado, observacion: '', registrado_por: user?.nombre }
      })));
      
      setSuccess(`✓ Todos ${estado}`);
      setTimeout(() => setSuccess(''), 2000);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  const estados = [
    { val: 'presente', emoji: '✅', color: 'bg-green-500', label: 'Presente' },
    { val: 'ausente', emoji: '❌', color: 'bg-red-500', label: 'Ausente' },
    { val: 'tardanza', emoji: '⏰', color: 'bg-yellow-500', label: 'Tardanza' },
    { val: 'excusa', emoji: '📋', color: 'bg-blue-500', label: 'Excusa' }
  ];

  const conteo = {
    presente: asistencias.filter(a => a.asistencia?.estado === 'presente').length,
    ausente: asistencias.filter(a => a.asistencia?.estado === 'ausente').length,
    tardanza: asistencias.filter(a => a.asistencia?.estado === 'tardanza').length,
    excusa: asistencias.filter(a => a.asistencia?.estado === 'excusa').length,
    sinMarcar: asistencias.filter(a => !a.asistencia?.estado).length
  };

  const asignaturaSeleccionada = asignaturas.find(a => a.id === asignaturaId);

  return (
    <div className="p-4 space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">✅ Asistencia por Materia</h1>
        {!puedeEditar && (
          <span className="px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-sm font-medium">
            👁️ Solo lectura
          </span>
        )}
      </div>
      
      {!puedeEditar && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-blue-800">
            <strong>ℹ️</strong> Solo los profesores pueden registrar asistencia.
          </p>
        </div>
      )}
      
      {error && (
        <div className="p-3 bg-red-100 border border-red-300 text-red-700 rounded-lg flex justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="font-bold">×</button>
        </div>
      )}
      {success && (
        <div className="p-3 bg-green-100 border border-green-300 text-green-700 rounded-lg">
          {success}
        </div>
      )}

      {/* Tabs nivel (solo si colegio tiene >1 nivel) */}
      <NivelTabs value={nivelFiltro} onChange={(n) => { setNivelFiltro(n); setCursoId(0); }} showAll />

      {/* Filtros */}
      <div className="bg-white p-4 rounded-lg border shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div>
            <label className="block text-sm font-medium mb-1">📚 Curso</label>
            <select 
              value={cursoId} 
              onChange={e => setCursoId(Number(e.target.value))}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value={0}>-- Seleccionar --</option>
              {(() => {
                // Filtrar por nivel si aplica
                const cursosFilt = nivelFiltro === 'todos'
                  ? cursos
                  : cursos.filter(c => (c.nivel || 'secundaria') === nivelFiltro);
                const tandas = [...new Set(cursosFilt.map(c => c.tanda || 'Sin tanda'))];
                return tandas.map(tanda => (
                  <optgroup key={tanda} label={tanda}>
                    {cursosFilt.filter(c => (c.tanda || 'Sin tanda') === tanda).map(c => (
                      <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo}</option>
                    ))}
                  </optgroup>
                ));
              })()}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-1">📖 Materia</label>
            {esPrimaria ? (
              <div className="w-full px-3 py-2 border rounded-lg bg-indigo-50 border-indigo-200 text-indigo-700 text-sm">
                Asistencia diaria (primaria)
              </div>
            ) : (
              <select 
                value={asignaturaId} 
                onChange={e => setAsignaturaId(Number(e.target.value))}
                disabled={cursoId === 0 || loadingAsignaturas}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value={0}>
                  {loadingAsignaturas ? 'Cargando...' : cursoId === 0 ? 'Primero seleccione curso' : '-- Seleccionar --'}
                </option>
                {asignaturas.map(a => (
                  <option key={a.id} value={a.id}>{a.nombre}</option>
                ))}
              </select>
            )}
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-1">📅 Fecha</label>
            <input 
              type="date" 
              value={fecha}
              onChange={e => setFecha(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-end gap-2">
            {cursoId > 0 && (esPrimaria || asignaturaId > 0) && asistencias.length > 0 && puedeEditar && (
              <button 
                onClick={() => marcarTodos('presente')}
                disabled={saving}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm"
              >
                ✅ Todos
              </button>
            )}
            {cursoId > 0 && (esPrimaria || asignaturaId > 0) && (
              <button 
                onClick={cargarAsistencia}
                className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
              >
                🔄
              </button>
            )}
          </div>
        </div>

        {cursoId > 0 && (esPrimaria || asignaturaId > 0) && (
          <div className="mt-3 pt-3 border-t">
            <p className="text-sm text-gray-600">
              📋 <strong>{asignaturaSeleccionada?.nombre}</strong> — {new Date(fecha + 'T12:00:00').toLocaleDateString('es-DO', { weekday: 'long', day: 'numeric', month: 'long' })}
            </p>
          </div>
        )}
      </div>

      {/* Resumen */}
      {cursoId > 0 && (esPrimaria || asignaturaId > 0) && asistencias.length > 0 && (
        <div className="overflow-x-auto -mx-4 px-4">
          <div className="flex gap-2 min-w-max">
            <div className="bg-green-100 p-2 sm:p-3 rounded-lg text-center min-w-[72px] sm:min-w-[90px]">
              <div className="text-xl sm:text-2xl font-bold text-green-600">{conteo.presente}</div>
              <div className="text-[10px] sm:text-xs text-green-700">Presentes</div>
            </div>
            <div className="bg-red-100 p-2 sm:p-3 rounded-lg text-center min-w-[72px] sm:min-w-[90px]">
              <div className="text-xl sm:text-2xl font-bold text-red-600">{conteo.ausente}</div>
              <div className="text-[10px] sm:text-xs text-red-700">Ausentes</div>
            </div>
            <div className="bg-yellow-100 p-2 sm:p-3 rounded-lg text-center min-w-[72px] sm:min-w-[90px]">
              <div className="text-xl sm:text-2xl font-bold text-yellow-600">{conteo.tardanza}</div>
              <div className="text-[10px] sm:text-xs text-yellow-700">Tardanzas</div>
            </div>
            <div className="bg-blue-100 p-2 sm:p-3 rounded-lg text-center min-w-[72px] sm:min-w-[90px]">
              <div className="text-xl sm:text-2xl font-bold text-blue-600">{conteo.excusa}</div>
              <div className="text-[10px] sm:text-xs text-blue-700">Excusas</div>
            </div>
            <div className="bg-gray-100 p-2 sm:p-3 rounded-lg text-center min-w-[72px] sm:min-w-[90px]">
              <div className="text-xl sm:text-2xl font-bold text-gray-600">{conteo.sinMarcar}</div>
              <div className="text-[10px] sm:text-xs text-gray-700">Sin marcar</div>
            </div>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && cursoId > 0 && (esPrimaria || asignaturaId > 0) && (
        <div className="text-center py-8">
          <div className="inline-block animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
        </div>
      )}

      {/* Tabla */}
      {cursoId > 0 && (esPrimaria || asignaturaId > 0) && !loading && (
        <div className="bg-white rounded-lg border overflow-hidden shadow-sm">
          {asistencias.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <div className="text-4xl mb-2">📋</div>
              No hay estudiantes
            </div>
          ) : (<>
            {/* Búsqueda de estudiante */}
            <div className="p-3 bg-slate-50 border-b">
              <input
                type="text" placeholder="Buscar estudiante por nombre..." value={buscarEstudiante}
                onChange={e => setBuscarEstudiante(e.target.value)}
                className="w-full sm:w-72 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-400 focus:border-blue-400"
              />
            </div>
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-2 sm:px-4 py-2 text-left text-xs font-medium text-gray-600 w-8">#</th>
                  <th className="px-2 sm:px-4 py-2 text-left text-xs font-medium text-gray-600">Estudiante</th>
                  <th className="px-1 sm:px-4 py-2 text-center text-xs font-medium text-gray-600 whitespace-nowrap">Asistencia</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {asistencias.filter(a => !buscarEstudiante || a.estudiante.nombre_completo.toLowerCase().includes(buscarEstudiante.toLowerCase())).map((a, idx) => {
                  const esRetirado = !!a.estudiante.retirado;
                  return (
                  <tr key={a.estudiante.id} className={esRetirado ? 'bg-gray-50' : 'hover:bg-gray-50'}>
                    <td className={`px-2 sm:px-4 py-2 font-medium text-xs ${esRetirado ? 'text-gray-400 line-through' : 'text-gray-500'}`}>
                      {a.estudiante.no_lista || idx + 1}
                    </td>
                    <td className="px-2 sm:px-4 py-2 max-w-[120px] sm:max-w-none">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`font-medium text-xs sm:text-sm block truncate sm:whitespace-normal ${esRetirado ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
                          {a.estudiante.nombre_completo}
                        </span>
                        {esRetirado && (
                          <span
                            title={a.estudiante.motivo_retiro || 'Estudiante retirado'}
                            className="inline-block px-2 py-0.5 bg-gray-700 text-white text-[10px] font-medium rounded uppercase tracking-wide"
                          >
                            RETIRADO {a.estudiante.fecha_retiro ? a.estudiante.fecha_retiro.slice(5).replace('-','/') : ''}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-1 sm:px-4 py-2">
                      <div className="flex justify-center gap-1 sm:gap-2">
                        {estados.map(e => (
                          <button
                            key={e.val}
                            onClick={() => !esRetirado && puedeEditar && marcarAsistencia(a.estudiante.id, e.val)}
                            disabled={saving || !puedeEditar || esRetirado}
                            title={esRetirado ? 'Estudiante retirado' : e.label}
                            className={`w-8 h-8 sm:w-10 sm:h-10 rounded-lg text-base sm:text-xl transition-all border-2 ${
                              esRetirado
                                ? 'bg-gray-100 border-gray-200 cursor-not-allowed opacity-40'
                                : a.asistencia?.estado === e.val
                                  ? `${e.color} text-white border-transparent scale-110 shadow-md`
                                  : puedeEditar
                                    ? 'bg-gray-100 border-gray-200 hover:border-gray-400 hover:scale-105'
                                    : 'bg-gray-50 border-gray-100 cursor-not-allowed opacity-60'
                            }`}
                          >
                            {esRetirado ? '—' : e.emoji}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </>)}
        </div>
      )}

      {/* Mensaje inicial */}
      {(cursoId === 0 || asignaturaId === 0) && !loading && (
        <div className="bg-gray-50 border-2 border-dashed border-gray-200 rounded-lg p-12 text-center">
          <div className="text-5xl mb-4">📋</div>
          <h3 className="text-lg font-semibold text-gray-700">
            {cursoId === 0 ? 'Selecciona un curso' : 'Selecciona una materia'}
          </h3>
          <p className="text-gray-500 mt-2">
            Cada profesor registra la asistencia de sus materias asignadas.
          </p>
        </div>
      )}
    </div>
  );
};

export default AsistenciaPage;
