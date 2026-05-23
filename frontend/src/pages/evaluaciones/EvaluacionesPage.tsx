import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { ClipboardCheck, Star, TrendingUp, ChevronDown, ChevronUp, Eye, Plus, X, Save, Users } from 'lucide-react';
import { Modal, Button, Select, Textarea, Alert, Spinner } from '../../components/ui';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts';

interface Evaluacion {
  id: number;
  profesor_id: number;
  profesor: string;
  evaluador: string;
  periodo: number;
  fecha: string;
  puntualidad: number;
  planificacion: number;
  dominio_tema: number;
  metodologia: number;
  manejo_aula: number;
  uso_recursos: number;
  evaluacion_estudiantes: number;
  relacion_estudiantes: number;
  relacion_colegas: number;
  compromiso: number;
  promedio: number;
  nivel: string;
  fortalezas: string;
  areas_mejora: string;
  observaciones: string;
  plan_accion: string;
}

interface Resumen {
  profesor_id: number;
  profesor: string;
  total_evaluaciones: number;
  promedio: number;
  nivel: string;
  ultima_fecha: string | null;
}

interface Profesor {
  id: number;
  nombre_completo: string;
}

const CRITERIOS = [
  { key: 'puntualidad', label: 'Puntualidad y Asistencia', desc: 'Llega a tiempo y cumple su horario' },
  { key: 'planificacion', label: 'Planificación', desc: 'Planifica clases alineadas al currículo' },
  { key: 'dominio_tema', label: 'Dominio del Contenido', desc: 'Conocimiento profundo de la asignatura' },
  { key: 'metodologia', label: 'Metodología', desc: 'Estrategias de enseñanza efectivas' },
  { key: 'manejo_aula', label: 'Manejo del Aula', desc: 'Control y ambiente de aprendizaje' },
  { key: 'uso_recursos', label: 'Uso de Recursos', desc: 'Aprovecha recursos didácticos y tecnológicos' },
  { key: 'evaluacion_estudiantes', label: 'Evaluación', desc: 'Aplica evaluaciones justas y formativas' },
  { key: 'relacion_estudiantes', label: 'Relación con Estudiantes', desc: 'Trato respetuoso y motivador' },
  { key: 'relacion_colegas', label: 'Trabajo en Equipo', desc: 'Colabora con colegas' },
  { key: 'compromiso', label: 'Compromiso Institucional', desc: 'Participa en actividades del centro' },
];

const getNivelColor = (nivel: string | null) => {
  if (!nivel) return 'bg-gray-100 text-gray-600';
  const c: Record<string, string> = {
    'Excelente': 'bg-emerald-100 text-emerald-700 border-emerald-200',
    'Bueno': 'bg-blue-100 text-blue-700 border-blue-200',
    'Aceptable': 'bg-amber-100 text-amber-700 border-amber-200',
    'En Mejora': 'bg-orange-100 text-orange-700 border-orange-200',
    'Deficiente': 'bg-red-100 text-red-700 border-red-200',
  };
  return c[nivel] || 'bg-gray-100 text-gray-600';
};

const getStarColor = (val: number) => {
  if (val >= 4.5) return 'text-emerald-500';
  if (val >= 3.5) return 'text-blue-500';
  if (val >= 2.5) return 'text-amber-500';
  return 'text-red-500';
};

export const EvaluacionesPage = () => {
  const { user } = useAuth();
  const [resumen, setResumen] = useState<Resumen[]>([]);
  const [evaluaciones, setEvaluaciones] = useState<Evaluacion[]>([]);
  const [profesores, setProfesores] = useState<Profesor[]>([]);
  const [selectedProf, setSelectedProf] = useState<number | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [showDetalle, setShowDetalle] = useState<Evaluacion | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [vista, setVista] = useState<'resumen' | 'evaluaciones'>('resumen');

  const [form, setForm] = useState({
    profesor_id: 0, periodo: 1,
    puntualidad: 0, planificacion: 0, dominio_tema: 0, metodologia: 0,
    manejo_aula: 0, uso_recursos: 0, evaluacion_estudiantes: 0,
    relacion_estudiantes: 0, relacion_colegas: 0, compromiso: 0,
    fortalezas: '', areas_mejora: '', observaciones: '', plan_accion: ''
  });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [res, prof] = await Promise.all([
        api.get('/evaluaciones-profesor/resumen'),
        api.get('/usuarios?role=profesor')
      ]);
      setResumen(res.data || []);
      setProfesores(prof.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const loadEvaluacionesProf = async (profId: number) => {
    setSelectedProf(profId);
    setVista('evaluaciones');
    try {
      const res = await api.get(`/evaluaciones-profesor?profesor_id=${profId}`);
      setEvaluaciones(res.data || []);
    } catch (e) { console.error(e); }
  };

  const handleGuardar = async () => {
    if (!form.profesor_id) { setMessage({ type: 'error', text: 'Seleccione un profesor' }); return; }
    const criteriosLlenos = CRITERIOS.every(c => (form as any)[c.key] > 0);
    if (!criteriosLlenos) { setMessage({ type: 'error', text: 'Complete todos los criterios (1-5)' }); return; }
    try {
      await api.post('/evaluaciones-profesor', form);
      setMessage({ type: 'success', text: 'Evaluación guardada exitosamente' });
      setShowModal(false);
      setForm({ profesor_id: 0, periodo: 1, puntualidad: 0, planificacion: 0, dominio_tema: 0, metodologia: 0, manejo_aula: 0, uso_recursos: 0, evaluacion_estudiantes: 0, relacion_estudiantes: 0, relacion_colegas: 0, compromiso: 0, fortalezas: '', areas_mejora: '', observaciones: '', plan_accion: '' });
      loadData();
    } catch (e: any) { setMessage({ type: 'error', text: e.response?.data?.error || 'Error al guardar' }); }
  };

  const getRadarData = (ev: Evaluacion) => CRITERIOS.map(c => ({
    criterio: c.label.split(' ')[0],
    valor: (ev as any)[c.key] || 0,
    fullMark: 5
  }));

  if (loading) return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <ClipboardCheck className="text-indigo-600" size={28} />
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Evaluación de Profesores</h1>
            <p className="text-sm text-gray-500">Evaluación interna de desempeño docente</p>
          </div>
        </div>
        <Button onClick={() => setShowModal(true)} className="bg-indigo-600 hover:bg-indigo-700">
          <Plus size={18} className="mr-1" /> Nueva Evaluación
        </Button>
      </div>

      {message && <Alert variant={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>}

      {/* Tabs */}
      <div className="flex gap-2 border-b">
        <button onClick={() => setVista('resumen')} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${vista === 'resumen' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
          Resumen General
        </button>
        {selectedProf && (
          <button onClick={() => setVista('evaluaciones')} className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${vista === 'evaluaciones' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            Historial de {profesores.find(p => p.id === selectedProf)?.nombre_completo?.split(' ')[0] || 'Profesor'}
          </button>
        )}
      </div>

      {/* VISTA RESUMEN */}
      {vista === 'resumen' && (
        <>
          {/* Ranking / Grid */}
          <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            <div className="p-4 border-b bg-gray-50">
              <h2 className="font-bold text-gray-800 flex items-center gap-2"><Users size={20} /> Resumen por Profesor</h2>
            </div>
            {resumen.length > 0 ? (
              <div className="divide-y">
                {resumen.map((r, idx) => (
                  <div key={r.profesor_id} className="flex items-center gap-4 p-4 hover:bg-gray-50 cursor-pointer" onClick={() => loadEvaluacionesProf(r.profesor_id)}>
                    <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-sm flex-shrink-0">
                      {idx + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-gray-800 truncate">{r.profesor}</p>
                      <p className="text-xs text-gray-500">{r.total_evaluaciones} evaluación(es) • Última: {r.ultima_fecha ? new Date(r.ultima_fecha).toLocaleDateString('es-DO', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Sin evaluar'}</p>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {r.promedio > 0 && (
                        <div className="flex items-center gap-1">
                          <Star size={16} className={getStarColor(r.promedio)} fill="currentColor" />
                          <span className={`font-bold ${getStarColor(r.promedio)}`}>{r.promedio.toFixed(1)}</span>
                        </div>
                      )}
                      <span className={`px-2 py-1 text-xs font-medium rounded-full border ${getNivelColor(r.nivel)}`}>
                        {r.nivel || 'Sin evaluar'}
                      </span>
                      <Eye size={16} className="text-gray-400" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-12 text-center">
                <ClipboardCheck size={48} className="mx-auto text-gray-300 mb-4" />
                <p className="text-gray-500">No hay evaluaciones registradas aún</p>
                <p className="text-sm text-gray-400 mt-1">Haga clic en "Nueva Evaluación" para comenzar</p>
              </div>
            )}
          </div>
        </>
      )}

      {/* VISTA EVALUACIONES DE UN PROFESOR */}
      {vista === 'evaluaciones' && selectedProf && (
        <>
          <button onClick={() => { setVista('resumen'); setSelectedProf(null); }} className="text-sm text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
            ← Volver al resumen
          </button>

          {evaluaciones.length > 0 ? (
            <div className="space-y-4">
              {evaluaciones.map(ev => (
                <div key={ev.id} className="bg-white rounded-xl shadow-sm border overflow-hidden">
                  <div className="flex items-center justify-between p-4 border-b bg-gray-50 cursor-pointer" onClick={() => setShowDetalle(showDetalle?.id === ev.id ? null : ev)}>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1">
                        <Star size={18} className={getStarColor(ev.promedio)} fill="currentColor" />
                        <span className={`text-lg font-bold ${getStarColor(ev.promedio)}`}>{ev.promedio?.toFixed(1)}</span>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-800">Período {ev.periodo}</p>
                        <p className="text-xs text-gray-500">{new Date(ev.fecha).toLocaleDateString('es-DO', { day: 'numeric', month: 'long', year: 'numeric' })} • Evaluador: {ev.evaluador}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full border ${getNivelColor(ev.nivel)}`}>{ev.nivel}</span>
                      {showDetalle?.id === ev.id ? <ChevronUp size={20} className="text-gray-400" /> : <ChevronDown size={20} className="text-gray-400" />}
                    </div>
                  </div>
                  {showDetalle?.id === ev.id && (
                    <div className="p-4 space-y-4">
                      {/* Radar Chart */}
                      <div className="flex justify-center">
                        <div style={{ width: 350, height: 280 }}>
                          <ResponsiveContainer>
                            <RadarChart data={getRadarData(ev)}>
                              <PolarGrid />
                              <PolarAngleAxis dataKey="criterio" tick={{ fontSize: 10 }} />
                              <PolarRadiusAxis angle={90} domain={[0, 5]} tick={{ fontSize: 10 }} />
                              <Radar name="Puntaje" dataKey="valor" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
                            </RadarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                      {/* Criterios Grid */}
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                        {CRITERIOS.map(c => {
                          const val = (ev as any)[c.key] || 0;
                          return (
                            <div key={c.key} className="text-center p-2 rounded-lg bg-gray-50 border">
                              <p className="text-xs text-gray-500 truncate">{c.label}</p>
                              <p className={`text-lg font-bold ${getStarColor(val)}`}>{val}</p>
                            </div>
                          );
                        })}
                      </div>
                      {/* Texto */}
                      {ev.fortalezas && <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200"><p className="text-xs font-medium text-emerald-700 mb-1">Fortalezas</p><p className="text-sm text-gray-700">{ev.fortalezas}</p></div>}
                      {ev.areas_mejora && <div className="p-3 bg-amber-50 rounded-lg border border-amber-200"><p className="text-xs font-medium text-amber-700 mb-1">Áreas de Mejora</p><p className="text-sm text-gray-700">{ev.areas_mejora}</p></div>}
                      {ev.observaciones && <div className="p-3 bg-blue-50 rounded-lg border border-blue-200"><p className="text-xs font-medium text-blue-700 mb-1">Observaciones</p><p className="text-sm text-gray-700">{ev.observaciones}</p></div>}
                      {ev.plan_accion && <div className="p-3 bg-purple-50 rounded-lg border border-purple-200"><p className="text-xs font-medium text-purple-700 mb-1">Plan de Acción</p><p className="text-sm text-gray-700">{ev.plan_accion}</p></div>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border p-12 text-center">
              <ClipboardCheck size={48} className="mx-auto text-gray-300 mb-4" />
              <p className="text-gray-500">Este profesor aún no tiene evaluaciones</p>
            </div>
          )}
        </>
      )}

      {/* MODAL NUEVA EVALUACIÓN */}
      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Nueva Evaluación de Profesor" size="lg"
        footer={<><Button variant="secondary" onClick={() => setShowModal(false)}>Cancelar</Button><Button onClick={handleGuardar} className="bg-indigo-600 hover:bg-indigo-700"><Save size={16} className="mr-1" /> Guardar Evaluación</Button></>}>
        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-4">
            <Select label="Profesor" value={form.profesor_id} onChange={e => setForm({ ...form, profesor_id: parseInt(e.target.value) })}
              options={profesores.map(p => ({ value: p.id, label: p.nombre_completo }))} placeholder="Seleccionar..." />
            <Select label="Período" value={form.periodo} onChange={e => setForm({ ...form, periodo: parseInt(e.target.value) })}
              options={[{ value: 1, label: 'Período 1' }, { value: 2, label: 'Período 2' }, { value: 3, label: 'Período 3' }, { value: 4, label: 'Período 4' }]} />
          </div>

          <div className="border rounded-lg overflow-hidden">
            <div className="bg-indigo-50 px-4 py-2 border-b"><p className="text-sm font-bold text-indigo-800">Criterios de Evaluación (1-5)</p></div>
            <div className="divide-y">
              {CRITERIOS.map(c => (
                <div key={c.key} className="flex items-center justify-between px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-800">{c.label}</p>
                    <p className="text-xs text-gray-500">{c.desc}</p>
                  </div>
                  <div className="flex gap-1 flex-shrink-0 ml-4">
                    {[1, 2, 3, 4, 5].map(n => (
                      <button key={n} onClick={() => setForm({ ...form, [c.key]: n })}
                        className={`w-9 h-9 rounded-lg text-sm font-bold transition-all ${(form as any)[c.key] === n
                          ? 'bg-indigo-600 text-white shadow-md scale-110'
                          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Promedio preview */}
          {(() => {
            const vals = CRITERIOS.map(c => (form as any)[c.key]).filter((v: number) => v > 0);
            if (vals.length === 0) return null;
            const avg = vals.reduce((a: number, b: number) => a + b, 0) / vals.length;
            return (
              <div className="bg-indigo-50 rounded-lg p-3 flex items-center justify-between border border-indigo-200">
                <span className="text-sm font-medium text-indigo-800">Promedio parcial ({vals.length}/{CRITERIOS.length} criterios)</span>
                <span className={`text-xl font-bold ${getStarColor(avg)}`}>{avg.toFixed(2)}</span>
              </div>
            );
          })()}

          <Textarea label="Fortalezas" value={form.fortalezas} onChange={e => setForm({ ...form, fortalezas: e.target.value })} placeholder="¿Qué hace bien este profesor?" rows={2} />
          <Textarea label="Áreas de Mejora" value={form.areas_mejora} onChange={e => setForm({ ...form, areas_mejora: e.target.value })} placeholder="¿En qué puede mejorar?" rows={2} />
          <Textarea label="Observaciones" value={form.observaciones} onChange={e => setForm({ ...form, observaciones: e.target.value })} placeholder="Notas adicionales..." rows={2} />
          <Textarea label="Plan de Acción" value={form.plan_accion} onChange={e => setForm({ ...form, plan_accion: e.target.value })} placeholder="¿Qué acciones de mejora se acordaron?" rows={2} />
        </div>
      </Modal>
    </div>
  );
};

export default EvaluacionesPage;
