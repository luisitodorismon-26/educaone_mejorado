import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { ClipboardList, Save, Settings, ChevronDown, ChevronUp, Check } from 'lucide-react';
import { Select, Button, Alert, Spinner } from '../../components/ui';

interface Curso { id: number; nombre_completo: string; }
interface Asignatura { id: number; nombre: string; }
interface AsignacionProf { curso_id: number; curso: string; asignatura_id: number; asignatura: string; }
interface ConfigPesos {
  id?: number; asignatura_id: number; asignatura?: string;
  peso_conducta: number; peso_cuaderno: number; peso_participacion: number;
  peso_trabajo: number; peso_asistencia: number; peso_exposicion: number; total_pesos?: number;
}
interface EvalEstudiante {
  estudiante_id: number; nombre: string; no_lista: number;
  conducta: number | null; cuaderno: number | null; participacion: number | null;
  trabajo: number | null; asistencia_eval: number | null; exposicion: number | null;
  nota_final: number | null; observacion: string;
}

const CRITERIOS = [
  { key: 'conducta', label: 'Conducta', icon: '🎯', peso_key: 'peso_conducta' },
  { key: 'cuaderno', label: 'Cuaderno', icon: '📓', peso_key: 'peso_cuaderno' },
  { key: 'participacion', label: 'Participación', icon: '🙋', peso_key: 'peso_participacion' },
  { key: 'trabajo', label: 'Trabajo', icon: '📝', peso_key: 'peso_trabajo' },
  { key: 'asistencia_eval', label: 'Asistencia', icon: '📅', peso_key: 'peso_asistencia' },
  { key: 'exposicion', label: 'Exposición', icon: '🎤', peso_key: 'peso_exposicion' },
];

const getColorNota = (n: number | null) => {
  if (n === null) return 'text-gray-400';
  if (n >= 90) return 'text-emerald-600 font-bold';
  if (n >= 80) return 'text-blue-600';
  if (n >= 70) return 'text-amber-600';
  return 'text-red-600 font-bold';
};

export const EvalInternaPage = () => {
  const { user } = useAuth();
  const [asignaciones, setAsignaciones] = useState<AsignacionProf[]>([]);
  const [cursosCompletos, setCursosCompletos] = useState<any[]>([]);
  const [cursoId, setCursoId] = useState(0);
  const [asignaturaId, setAsignaturaId] = useState(0);
  const [periodo, setPeriodo] = useState(1);
  const [evaluaciones, setEvaluaciones] = useState<EvalEstudiante[]>([]);
  const [config, setConfig] = useState<ConfigPesos>({ asignatura_id: 0, peso_conducta: 15, peso_cuaderno: 15, peso_participacion: 20, peso_trabajo: 20, peso_asistencia: 15, peso_exposicion: 15 });
  const [showConfig, setShowConfig] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => { cargarAsignaciones(); }, []);

  const cargarAsignaciones = async () => {
    try {
      const [profRes, cursosRes] = await Promise.all([
        api.get('/dashboard/profesor'),
        api.get('/cursos')
      ]);
      if (profRes.data?.cursos_asignados) {
        const asigs = profRes.data.cursos_asignados.map((c: any) => ({
          curso_id: c.curso_id, curso: c.curso,
          asignatura_id: c.asignatura_id || 0, asignatura: c.asignatura
        }));
        setAsignaciones(asigs);
      }
      setCursosCompletos(cursosRes.data || []);
    } catch (e) {
      try {
        const res = await api.get('/cursos');
        setCursosCompletos(res.data || []);
      } catch { }
    }
  };

  const cargarEvaluaciones = async () => {
    if (!cursoId || !asignaturaId) return;
    setLoading(true);
    try {
      // Load config
      const confRes = await api.get(`/eval-interna/config?asignatura_id=${asignaturaId}`);
      if (confRes.data?.length > 0) {
        setConfig(confRes.data[0]);
      }
      // Load existing evals
      const evRes = await api.get(`/eval-interna?curso_id=${cursoId}&asignatura_id=${asignaturaId}&periodo=${periodo}`);
      const existingEvals = evRes.data || [];

      // Load students
      const estRes = await api.get(`/estudiantes?curso_id=${cursoId}`);
      const estudiantes = (estRes.data || []).sort((a: any, b: any) => (a.no_lista || 0) - (b.no_lista || 0));

      // Merge
      const merged: EvalEstudiante[] = estudiantes.map((est: any) => {
        const existing = existingEvals.find((e: any) => e.estudiante_id === est.id);
        return {
          estudiante_id: est.id,
          nombre: est.nombre_completo,
          no_lista: est.no_lista || 0,
          conducta: existing?.conducta ?? null,
          cuaderno: existing?.cuaderno ?? null,
          participacion: existing?.participacion ?? null,
          trabajo: existing?.trabajo ?? null,
          asistencia_eval: existing?.asistencia_eval ?? null,
          exposicion: existing?.exposicion ?? null,
          nota_final: existing?.nota_final ?? null,
          observacion: existing?.observacion || ''
        };
      });
      setEvaluaciones(merged);
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al cargar' });
    } finally { setLoading(false); }
  };

  const calcularNotaLocal = (ev: EvalEstudiante) => {
    const pesos: Record<string, number> = {
      conducta: config.peso_conducta, cuaderno: config.peso_cuaderno,
      participacion: config.peso_participacion, trabajo: config.peso_trabajo,
      asistencia_eval: config.peso_asistencia, exposicion: config.peso_exposicion
    };
    const totalPeso = Object.values(pesos).reduce((a, b) => a + b, 0);
    if (totalPeso === 0) return null;
    let suma = 0;
    for (const [campo, peso] of Object.entries(pesos)) {
      const val = (ev as any)[campo];
      if (val !== null && val !== undefined) suma += val * peso;
    }
    return Math.round(suma / totalPeso * 100) / 100;
  };

  const updateEval = (idx: number, field: string, value: string) => {
    const numVal = value === '' ? null : Math.min(100, Math.max(0, parseFloat(value)));
    const updated = [...evaluaciones];
    (updated[idx] as any)[field] = numVal;
    updated[idx].nota_final = calcularNotaLocal(updated[idx]);
    setEvaluaciones(updated);
  };

  const guardarTodo = async () => {
    setSaving(true);
    try {
      await api.post('/eval-interna/guardar', {
        curso_id: cursoId, asignatura_id: asignaturaId, periodo,
        evaluaciones: evaluaciones.map(e => ({
          estudiante_id: e.estudiante_id, conducta: e.conducta, cuaderno: e.cuaderno,
          participacion: e.participacion, trabajo: e.trabajo,
          asistencia_eval: e.asistencia_eval, exposicion: e.exposicion, observacion: e.observacion
        }))
      });
      setMessage({ type: 'success', text: 'Evaluaciones guardadas correctamente' });
      setTimeout(() => setMessage(null), 3000);
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' });
    } finally { setSaving(false); }
  };

  const guardarConfig = async () => {
    if (!asignaturaId) {
      setMessage({ type: 'error', text: 'Primero selecciona un curso y una asignatura antes de configurar los criterios' });
      return;
    }
    const total = config.peso_conducta + config.peso_cuaderno + config.peso_participacion + config.peso_trabajo + config.peso_asistencia + config.peso_exposicion;
    if (Math.abs(total - 100) > 0.01) {
      setMessage({ type: 'error', text: `Los pesos deben sumar 100. Actualmente suman ${total}` });
      return;
    }
    try {
      await api.post('/eval-interna/config', { asignatura_id: asignaturaId, ...config });
      setMessage({ type: 'success', text: 'Configuración de pesos guardada' });
      setShowConfig(false);
      setEvaluaciones(evaluaciones.map(e => ({ ...e, nota_final: calcularNotaLocal(e) })));
    } catch (e: any) {
      setMessage({ type: 'error', text: e.response?.data?.error || 'Error' });
    }
  };

  const totalPesos = config.peso_conducta + config.peso_cuaderno + config.peso_participacion + config.peso_trabajo + config.peso_asistencia + config.peso_exposicion;

  // Get unique cursos and asignaturas from asignaciones
  const cursosAsignadosIds = new Set(asignaciones.map(a => a.curso_id));
  const cursosUnicos = cursosCompletos.length > 0
    ? cursosCompletos.filter(c => asignaciones.length === 0 || cursosAsignadosIds.has(c.id))
    : [...new Map(asignaciones.map(a => [a.curso_id, { id: a.curso_id, nombre: a.curso }])).values()];
  const asignaturasDelCurso = asignaciones.filter(a => a.curso_id === cursoId);

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div className="flex items-center gap-3">
          <ClipboardList className="text-indigo-600" size={28} />
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Evaluación Interna</h1>
            <p className="text-sm text-gray-500">Evalúa a tus estudiantes por criterios</p>
          </div>
        </div>
        {evaluaciones.length > 0 && (
          <Button onClick={guardarTodo} loading={saving} className="bg-indigo-600 hover:bg-indigo-700">
            <Save size={16} className="mr-1" /> Guardar Todo
          </Button>
        )}
      </div>

      {message && <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>}

      {/* Selectores */}
      <div className="bg-white rounded-xl border shadow-sm p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Curso</label>
            <select value={cursoId} onChange={e => { setCursoId(Number(e.target.value)); setAsignaturaId(0); setEvaluaciones([]); }}
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500">
              <option value={0}>Seleccionar...</option>
              {(() => {
                const tandas = [...new Set(cursosUnicos.map((c: any) => c.tanda || 'Sin tanda'))];
                return tandas.length > 1 ? tandas.map(tanda => (
                  <optgroup key={tanda} label={tanda}>
                    {cursosUnicos.filter((c: any) => (c.tanda || 'Sin tanda') === tanda).map((c: any) => (
                      <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre}</option>
                    ))}
                  </optgroup>
                )) : cursosUnicos.map((c: any) => <option key={c.id} value={c.id}>{c.grado ? `${c.grado} ${c.nombre}` : c.nombre}</option>);
              })()}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Asignatura</label>
            <select value={asignaturaId} onChange={e => { setAsignaturaId(Number(e.target.value)); setEvaluaciones([]); }}
              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" disabled={!cursoId}>
              <option value={0}>Seleccionar...</option>
              {asignaturasDelCurso.map(a => <option key={a.asignatura_id} value={a.asignatura_id}>{a.asignatura}</option>)}
            </select>
          </div>
          <Select label="Período" value={periodo.toString()} onChange={e => { setPeriodo(Number(e.target.value)); setEvaluaciones([]); }}
            options={[{ value: 1, label: 'P1' }, { value: 2, label: 'P2' }, { value: 3, label: 'P3' }, { value: 4, label: 'P4' }]} />
          <div className="flex items-end gap-2">
            <Button onClick={cargarEvaluaciones} disabled={!cursoId || !asignaturaId} loading={loading} className="flex-1 bg-indigo-600 hover:bg-indigo-700">
              Cargar
            </Button>
            {asignaturaId > 0 && (
              <button onClick={() => setShowConfig(!showConfig)} className="p-2 border rounded-lg hover:bg-gray-100" title="Configurar pesos">
                <Settings size={20} className="text-gray-600" />
              </button>
            )}
          </div>
        </div>

        {/* Config pesos */}
        {showConfig && asignaturaId > 0 && (
          <div className="mt-4 p-4 bg-indigo-50 rounded-lg border border-indigo-200">
            <h3 className="font-bold text-indigo-800 mb-3 flex items-center gap-2">
              <Settings size={16} /> Configurar Pesos (deben sumar 100)
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {CRITERIOS.map(c => (
                <div key={c.key}>
                  <label className="block text-xs font-medium text-indigo-700 mb-1">{c.icon} {c.label}</label>
                  <input type="number" min={0} max={100} step={1}
                    value={(config as any)[c.peso_key] || 0}
                    onChange={e => setConfig({ ...config, [c.peso_key]: parseFloat(e.target.value) || 0 })}
                    className="w-full px-2 py-1.5 border rounded text-sm text-center focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className={`text-sm font-bold ${Math.abs(totalPesos - 100) < 0.01 ? 'text-emerald-600' : 'text-red-600'}`}>
                Total: {totalPesos} {Math.abs(totalPesos - 100) < 0.01 ? '✓' : '(debe ser 100)'}
              </span>
              <Button onClick={guardarConfig} disabled={Math.abs(totalPesos - 100) > 0.01} className="bg-indigo-600 hover:bg-indigo-700 text-sm px-4 py-1.5">
                <Check size={14} className="mr-1" /> Guardar Pesos
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Tabla de evaluaciones */}
      {evaluaciones.length > 0 && (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="p-3 bg-indigo-600 text-white flex items-center justify-between">
            <div>
              <p className="font-bold">{cursosUnicos.find(c => c.id === cursoId)?.nombre} — Período {periodo}</p>
              <p className="text-indigo-200 text-xs">{evaluaciones.length} estudiantes</p>
            </div>
            <div className="flex gap-1 text-xs">
              {CRITERIOS.map(c => (
                <span key={c.key} className="bg-indigo-500 px-2 py-0.5 rounded text-[10px]">
                  {c.icon} {(config as any)[c.peso_key]}%
                </span>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b">
                  <th className="text-left p-2 font-medium text-gray-600 w-8">#</th>
                  <th className="text-left p-2 font-medium text-gray-600 min-w-[150px]">Estudiante</th>
                  {CRITERIOS.map(c => (
                    <th key={c.key} className="text-center p-2 font-medium text-gray-600 whitespace-nowrap">
                      <span className="text-xs">{c.icon} {c.label}</span>
                      <br /><span className="text-[10px] text-gray-400">{(config as any)[c.peso_key]}%</span>
                    </th>
                  ))}
                  <th className="text-center p-2 font-bold text-gray-700 bg-indigo-50 whitespace-nowrap">Nota<br /><span className="text-[10px] font-normal text-gray-400">/100</span></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {evaluaciones.map((ev, idx) => (
                  <tr key={ev.estudiante_id} className="hover:bg-gray-50">
                    <td className="p-2 text-gray-400 text-center text-xs">{ev.no_lista}</td>
                    <td className="p-2 font-medium text-gray-800 truncate max-w-[180px]">{ev.nombre}</td>
                    {CRITERIOS.map(c => (
                      <td key={c.key} className="p-1 text-center">
                        <input type="number" min={0} max={100} step={1}
                          value={(ev as any)[c.key] ?? ''}
                          onChange={e => updateEval(idx, c.key, e.target.value)}
                          className="w-14 px-1 py-1 border rounded text-center text-sm focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400"
                          placeholder="-"
                        />
                      </td>
                    ))}
                    <td className="p-2 text-center bg-indigo-50">
                      <span className={`text-sm ${getColorNota(ev.nota_final)}`}>
                        {ev.nota_final !== null ? ev.nota_final.toFixed(1) : '-'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="p-3 border-t bg-gray-50 flex justify-end">
            <Button onClick={guardarTodo} loading={saving} className="bg-indigo-600 hover:bg-indigo-700">
              <Save size={16} className="mr-1" /> Guardar Evaluaciones
            </Button>
          </div>
        </div>
      )}

      {!evaluaciones.length && !loading && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-6">
          <h3 className="font-semibold text-indigo-800 mb-2">¿Cómo funciona?</h3>
          <p className="text-indigo-700 text-sm mb-3">Selecciona tu curso, asignatura y período. Luego evalúa cada estudiante del 0 al 100 en cada criterio. La nota final se calcula automáticamente según los pesos que configures.</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {CRITERIOS.map(c => (
              <div key={c.key} className="flex items-center gap-2 p-2 bg-white rounded border">
                <span className="text-lg">{c.icon}</span>
                <div><p className="text-sm font-medium">{c.label}</p><p className="text-xs text-gray-500">Peso configurable</p></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default EvalInternaPage;
