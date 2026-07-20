import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Button, Alert } from '../../components/ui';

interface Curso {
  id: number;
  nombre_completo: string;
  tanda?: string;
  grado?: string;
  nivel?: string; // 'primaria' | 'secundaria' | 'inicial' (normalizado por el backend)
}

interface Profesor {
  id: number;
  nombre_completo: string;
}

interface AsignacionCurso {
  asignatura_id: number;
  asignatura: string;
  profesor_id: number | null;
  profesor: string | null;
  es_titular: boolean;
}

// v2.14.1: áreas oficiales del Nivel Primario (espejo del normalizador del
// boletín). El botón "Maestro titular" solo marca estas — así en un curso de
// primaria no se asignan materias de secundaria (Física, Química, etc.).
const _quitar_acentos = (s: string) =>
  (s || '').toLowerCase().trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

const AREAS_PRIMARIA_BASE: string[][] = [
  ['lengua espanola', 'espanol'],
  ['matematica', 'matematicas'],
  ['ciencias sociales', 'sociales'],
  ['ciencias de la naturaleza', 'ciencias naturales', 'naturales'],
  // OJO: sin alias corto 'fisica' — colisionaría con la asignatura "Física"
  // (ciencia de secundaria) que vive en la misma lista global del colegio.
  ['educacion fisica'],
  ['formacion integral humana y religiosa', 'formacion integral', 'religion'],
  ['educacion artistica', 'artistica'],
];
const AREA_INGLES: string[] = ['lenguas extranjeras (ingles)', 'ingles'];

const esAreaPrimaria = (nombreAsignatura: string, conIngles: boolean): boolean => {
  const n = _quitar_acentos(nombreAsignatura);
  for (const sinonimos of AREAS_PRIMARIA_BASE) {
    if (sinonimos.includes(n)) return true;
  }
  if (conIngles && AREA_INGLES.includes(n)) return true;
  return false;
};

const gradoTieneIngles = (gradoNombre: string): boolean => {
  const g = _quitar_acentos(gradoNombre);
  return ['4', 'cuarto', '5', 'quinto', '6', 'sexto'].some(k => g.includes(k));
};

export const AsignacionesPage = () => {
  const [cursos, setCursos] = useState<Curso[]>([]);
  const [profesores, setProfesores] = useState<Profesor[]>([]);
  const [cursoSeleccionado, setCursoSeleccionado] = useState<number>(0);
  const [asignaciones, setAsignaciones] = useState<AsignacionCurso[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  // v2.14.1: maestro titular de primaria (botón "asignar todas las áreas")
  const [titularId, setTitularId] = useState<number>(0);

  useEffect(() => { loadInicial(); }, []);
  useEffect(() => { if (cursoSeleccionado) { loadAsignacionesCurso(); setTitularId(0); } }, [cursoSeleccionado]);

  const loadInicial = async () => {
    try {
      const [c, p] = await Promise.all([api.get('/cursos'), api.get('/profesores')]);
      setCursos(c.data);
      setProfesores(p.data);
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al cargar datos' });
    } finally {
      setLoading(false);
    }
  };

  const loadAsignacionesCurso = async () => {
    try {
      const res = await api.get(`/cursos/${cursoSeleccionado}/asignaciones`);
      setAsignaciones(res.data.asignaciones);
    } catch (e) {
      setMessage({ type: 'error', text: 'Error al cargar asignaciones' });
    }
  };

  const handleProfesorChange = (asignaturaId: number, profesorId: number) => {
    setAsignaciones(prev => prev.map(a => 
      a.asignatura_id === asignaturaId 
        ? { ...a, profesor_id: profesorId || null }
        : a
    ));
  };

  const handleTitularChange = (asignaturaId: number, esTitular: boolean) => {
    setAsignaciones(prev => prev.map(a => 
      a.asignatura_id === asignaturaId 
        ? { ...a, es_titular: esTitular }
        : a
    ));
  };

  const handleGuardar = async () => {
    // Contar cuántas asignaciones tienen profesor
    const conProfesor = asignaciones.filter(a => a.profesor_id).length;
    if (conProfesor === 0) {
      setMessage({ type: 'error', text: 'Debe asignar al menos un profesor a una asignatura' });
      return;
    }
    
    setSaving(true);
    try {
      await api.post(`/cursos/${cursoSeleccionado}/asignaciones`, { asignaciones });
      setMessage({ type: 'success', text: `✓ ${conProfesor} asignaciones guardadas correctamente` });
      loadAsignacionesCurso();
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setSaving(false);
    }
  };

  const cursoActual = cursos.find(c => c.id === cursoSeleccionado);
  const esPrimaria = cursoActual?.nivel === 'primaria';

  // v2.14.1: en primaria, un solo maestro titular suele dar TODAS las áreas.
  // Este botón marca de una vez las 7-8 áreas oficiales del grado con el
  // profesor elegido (y el check de titular). NO guarda: la dirección revisa
  // la tabla y presiona "Guardar Asignaciones" como siempre.
  const asignarTitularTodas = () => {
    if (!titularId) {
      setMessage({ type: 'error', text: 'Selecciona primero al maestro titular' });
      return;
    }
    const conIngles = gradoTieneIngles(cursoActual?.grado || cursoActual?.nombre_completo || '');
    const areas = asignaciones.filter(a => esAreaPrimaria(a.asignatura, conIngles));
    if (areas.length === 0) {
      setMessage({ type: 'error', text: 'No se encontraron áreas oficiales de primaria entre las asignaturas del colegio' });
      return;
    }
    const ids = new Set(areas.map(a => a.asignatura_id));
    setAsignaciones(prev => prev.map(a =>
      ids.has(a.asignatura_id) ? { ...a, profesor_id: titularId, es_titular: true } : a
    ));
    const prof = profesores.find(p => p.id === titularId);
    setMessage({
      type: 'success',
      text: `✓ ${areas.length} áreas marcadas para ${prof?.nombre_completo || 'el titular'}${conIngles ? ' (incluye Inglés)' : ''} — revisa la tabla y presiona "Guardar Asignaciones"`,
    });
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin h-8 w-8 border-2 border-blue-600 rounded-full border-t-transparent"></div></div>;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">📋 Asignaciones de Profesores</h1>
      </div>

      {message && <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>}

      {/* Selector de Curso */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
          <label className="font-medium text-gray-700 text-sm whitespace-nowrap">Seleccionar Curso:</label>
          <select 
            value={cursoSeleccionado} 
            onChange={e => setCursoSeleccionado(parseInt(e.target.value))}
            className="w-full sm:flex-1 sm:max-w-md px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option value={0}>-- Seleccione un curso --</option>
            {cursos.filter(c => c.tanda?.includes('Matutina')).length > 0 && (
              <optgroup label="☀️ Tanda Matutina">
                {cursos.filter(c => c.tanda?.includes('Matutina')).map(c => (
                  <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo}</option>
                ))}
              </optgroup>
            )}
            {cursos.filter(c => c.tanda?.includes('Vespertina')).length > 0 && (
              <optgroup label="🌙 Tanda Vespertina">
                {cursos.filter(c => c.tanda?.includes('Vespertina')).map(c => (
                  <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo}</option>
                ))}
              </optgroup>
            )}
            {cursos.filter(c => !c.tanda).map(c => (
              <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre_completo}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabla de Asignaciones */}
      {cursoSeleccionado > 0 && (
        <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
          <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
            <h2 className="font-semibold text-gray-800">
              Asignar Profesores - {cursoActual?.nombre_completo}
              {cursoActual?.tanda && (
                <span className={`ml-2 text-sm px-2 py-0.5 rounded ${cursoActual.tanda.includes('Matutina') ? 'bg-amber-100 text-amber-700' : 'bg-purple-100 text-purple-700'}`}>
                  {cursoActual.tanda}
                </span>
              )}
            </h2>
            <Button onClick={handleGuardar} loading={saving}>
              💾 Guardar Asignaciones
            </Button>
          </div>

          {esPrimaria && (
            <div className="p-3 border-b bg-blue-50 flex flex-col sm:flex-row sm:items-center gap-2">
              <span className="text-sm font-medium text-blue-800 whitespace-nowrap">🎒 Maestro titular (da todas las áreas):</span>
              <select
                value={titularId}
                onChange={e => setTitularId(parseInt(e.target.value) || 0)}
                className="flex-1 sm:max-w-xs px-3 py-1.5 border border-blue-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 bg-white"
              >
                <option value={0}>-- Seleccione al maestro --</option>
                {profesores.map(p => (
                  <option key={p.id} value={p.id}>{p.nombre_completo}</option>
                ))}
              </select>
              <button
                onClick={asignarTitularTodas}
                className="px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 whitespace-nowrap"
              >
                Asignar todas las áreas
              </button>
            </div>
          )}

          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Asignatura</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">Profesor</th>
                <th className="px-4 py-3 text-center text-sm font-medium text-gray-600">Titular</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {asignaciones.map(a => (
                <tr key={a.asignatura_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">{a.asignatura}</td>
                  <td className="px-4 py-3">
                    <select
                      value={a.profesor_id || ''}
                      onChange={e => handleProfesorChange(a.asignatura_id, parseInt(e.target.value))}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">-- Sin asignar --</option>
                      {profesores.map(p => (
                        <option key={p.id} value={p.id}>{p.nombre_completo}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <input
                      type="checkbox"
                      checked={a.es_titular}
                      onChange={e => handleTitularChange(a.asignatura_id, e.target.checked)}
                      disabled={!a.profesor_id}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {asignaciones.length === 0 && (
            <div className="p-8 text-center text-gray-500">
              No hay asignaturas configuradas
            </div>
          )}
        </div>
      )}

      {/* Mensaje inicial */}
      {cursoSeleccionado === 0 && (
        <div className="bg-white rounded-xl border p-12 text-center">
          <div className="text-6xl mb-4">📋</div>
          <h3 className="text-lg font-semibold text-gray-700 mb-2">Asignar Profesores a Cursos</h3>
          <p className="text-gray-500">Seleccione un curso para asignar profesores a cada asignatura</p>
        </div>
      )}
    </div>
  );
};

export default AsignacionesPage;
