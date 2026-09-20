import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Save, RefreshCw, Trash2, BookOpen } from 'lucide-react';
import { Button, Alert, Spinner } from '../../components/ui';
import { useAuth } from '../../context/AuthContext';
import {
  Intervencion, BorradorIntervencion, Modalidad,
  validarIntervencion, etiquetaResultado, etiquetaCompetencia,
  historialPorEstudiante, puedeModificar, puedeRetirarAdministrativamente,
  borradorVacio, textoModalidad,
} from './recuperacionCualitativa';

// ═══════════════════════════════════════════════════════════════
// RECUPERACIÓN PEDAGÓGICA DEL PERÍODO — 1ro y 2do (CUALITATIVA)
//
// Reproduce el formulario del Registro oficial: área, aspectos no logrados y
// período, estrategias y evidencias, y competencia lograda o no lograda.
// No hay casilla de nota, y guardar «Lograda» no cambia ninguna calificación.
// ═══════════════════════════════════════════════════════════════

interface Curso { id: number; nombre: string; nombre_completo?: string; grado_nombre?: string }
interface Asignatura { id: number; nombre: string }

export const TabRecuperacionCualitativa: React.FC = () => {
  const { user } = useAuth();
  const esProfesor = user?.role === 'profesor';
  // Secretaria lee pero no retira; psicologia ni siquiera entra aqui.
  const puedeRetiroAdmin = puedeRetirarAdministrativamente(user?.role);

  const [cursos, setCursos] = useState<Curso[]>([]);
  const [asignaturas, setAsignaturas] = useState<Asignatura[]>([]);
  const [cursoId, setCursoId] = useState<number | null>(null);
  const [asignaturaId, setAsignaturaId] = useState<number | null>(null);
  const [periodo, setPeriodo] = useState<number>(1);

  const [modalidad, setModalidad] = useState<Modalidad | null>(null);
  const [gradoNombre, setGradoNombre] = useState<string>('');
  const [estudiantes, setEstudiantes] = useState<{ id: number; nombre_completo: string; retirado: boolean }[]>([]);
  const [intervenciones, setIntervenciones] = useState<Intervencion[]>([]);

  const [borrador, setBorrador] = useState<BorradorIntervencion>(borradorVacio(1));
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  useEffect(() => {
    api.get('/cursos')
      .then(r => setCursos(r.data || []))
      .catch(() => setCursos([]));
  }, []);

  // La modalidad la decide el SERVIDOR desde el curso. Aquí no se calcula.
  useEffect(() => {
    if (!cursoId) { setModalidad(null); setAsignaturas([]); return; }
    setAsignaturaId(null);
    api.get(`/recuperacion-primaria/contexto/${cursoId}`)
      .then(r => { setModalidad(r.data.modalidad); setGradoNombre(r.data.grado || ''); })
      .catch(e => {
        setModalidad(null);
        setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo leer el curso' });
      });
    api.get(`/mis-asignaturas/${cursoId}`)
      .then(r => setAsignaturas(r.data || []))
      .catch(() => setAsignaturas([]));
  }, [cursoId]);

  const cargar = async () => {
    if (!cursoId || !asignaturaId || modalidad !== 'cualitativa') return;
    setLoading(true);
    try {
      const r = await api.get(
        `/recuperacion-primaria/cualitativa/${cursoId}/${asignaturaId}?periodo=${periodo}`);
      setEstudiantes(r.data.estudiantes || []);
      setIntervenciones(r.data.intervenciones || []);
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al cargar' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); /* eslint-disable-next-line */ }, [cursoId, asignaturaId, periodo, modalidad]);
  useEffect(() => { setBorrador(b => ({ ...b, periodo })); }, [periodo]);

  const guardar = async () => {
    const err = validarIntervencion(borrador);
    if (err) { setMensaje({ tipo: 'error', texto: err }); return; }
    setGuardando(true);
    setMensaje(null);
    try {
      const cuerpo = { ...borrador, asignatura_id: asignaturaId };
      if (editandoId) {
        await api.put(`/recuperacion-primaria/cualitativa/${editandoId}`, cuerpo);
      } else {
        await api.post('/recuperacion-primaria/cualitativa', cuerpo);
      }
      setMensaje({ tipo: 'success', texto: 'Intervención registrada' });
      setBorrador(borradorVacio(periodo));
      setEditandoId(null);
      await cargar();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setGuardando(false);
    }
  };

  const retirar = async (i: Intervencion) => {
    const motivo = puedeRetiroAdmin ? (window.prompt('Motivo del retiro administrativo:') || '') : '';
    if (puedeRetiroAdmin && !motivo.trim()) return;
    try {
      await api.post(`/recuperacion-primaria/cualitativa/${i.id}/retirar`, { motivo_retiro: motivo });
      await cargar();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo retirar' });
    }
  };

  const editar = (i: Intervencion) => {
    setEditandoId(i.id);
    setBorrador({
      estudiante_id: i.estudiante_id,
      competencia_numero: i.competencia_numero,
      periodo: i.periodo,
      aspectos_no_logrados: i.aspectos_no_logrados,
      estrategias_evidencias: i.estrategias_evidencias || '',
      resultado: i.resultado,
      observacion: i.observacion || '',
    });
  };

  const historial = historialPorEstudiante(intervenciones);
  const set = (p: Partial<BorradorIntervencion>) => setBorrador(b => ({ ...b, ...p }));

  return (
    <div className="bg-white rounded-xl shadow-sm border p-4 space-y-4">
      <div className="flex items-center gap-2">
        <BookOpen className="text-blue-600" size={20} />
        <h3 className="font-bold text-lg">Recuperación pedagógica del período</h3>
      </div>

      <div className="flex flex-wrap gap-2">
        <select className="border rounded px-2 py-1.5 text-sm"
                value={cursoId ?? ''} onChange={e => setCursoId(Number(e.target.value) || null)}>
          <option value="">Curso…</option>
          {cursos.map(c => (
            <option key={c.id} value={c.id}>{c.nombre_completo || c.nombre}</option>
          ))}
        </select>
        <select className="border rounded px-2 py-1.5 text-sm" disabled={!cursoId}
                value={asignaturaId ?? ''} onChange={e => setAsignaturaId(Number(e.target.value) || null)}>
          <option value="">Asignatura…</option>
          {asignaturas.map(a => <option key={a.id} value={a.id}>{a.nombre}</option>)}
        </select>
        <select className="border rounded px-2 py-1.5 text-sm"
                value={periodo} onChange={e => setPeriodo(Number(e.target.value))}>
          {[1, 2, 3, 4].map(p => <option key={p} value={p}>P{p}</option>)}
        </select>
        <Button variant="secondary" size="sm" onClick={cargar} icon={<RefreshCw size={14} />}>
          Refrescar
        </Button>
      </div>

      <p className="text-xs text-gray-500">
        {gradoNombre && <strong>{gradoNombre} · </strong>}{textoModalidad(modalidad)}
      </p>

      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {modalidad === 'cuantitativa' && (
        <Alert variant="info">
          En {gradoNombre || 'este grado'} la recuperación del período es <strong>cuantitativa</strong>:
          se carga como RP junto a la nota del período, en Calificaciones.
        </Alert>
      )}

      {modalidad === 'cualitativa' && asignaturaId && (
        <>
          {esProfesor && (
            <div className="border rounded-lg p-3 bg-blue-50/40 space-y-2">
              <div className="flex flex-wrap gap-2">
                <select className="border rounded px-2 py-1.5 text-sm"
                        value={borrador.estudiante_id ?? ''}
                        onChange={e => set({ estudiante_id: Number(e.target.value) || null })}>
                  <option value="">Estudiante…</option>
                  {estudiantes.filter(e => !e.retirado).map(e => (
                    <option key={e.id} value={e.id}>{e.nombre_completo}</option>
                  ))}
                </select>
                <select className="border rounded px-2 py-1.5 text-sm"
                        value={borrador.competencia_numero ?? ''}
                        onChange={e => set({ competencia_numero: e.target.value === '' ? null : Number(e.target.value) })}>
                  <option value="">Varias / el área</option>
                  <option value={1}>C1</option>
                  <option value={2}>C2</option>
                  <option value={3}>C3</option>
                </select>
              </div>

              <label className="block text-xs font-medium text-gray-700">
                Aspecto(s) de la(s) competencia(s) no logrado(s)
                <textarea className="mt-1 w-full border rounded px-2 py-1.5 text-sm" rows={2}
                          value={borrador.aspectos_no_logrados}
                          onChange={e => set({ aspectos_no_logrados: e.target.value })} />
              </label>

              <label className="block text-xs font-medium text-gray-700">
                Estrategias utilizadas y evidencias de aprendizaje
                <textarea className="mt-1 w-full border rounded px-2 py-1.5 text-sm" rows={2}
                          value={borrador.estrategias_evidencias}
                          onChange={e => set({ estrategias_evidencias: e.target.value })} />
              </label>

              <div className="flex items-center gap-4 text-sm">
                <span className="font-medium text-gray-700">Competencia:</span>
                {(['lograda', 'no_lograda'] as const).map(r => (
                  <label key={r} className="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" name="resultado" checked={borrador.resultado === r}
                           onChange={() => set({ resultado: r })} />
                    {etiquetaResultado(r)}
                  </label>
                ))}
              </div>

              <label className="block text-xs font-medium text-gray-700">
                Observación (opcional)
                <input className="mt-1 w-full border rounded px-2 py-1.5 text-sm"
                       value={borrador.observacion}
                       onChange={e => set({ observacion: e.target.value })} />
              </label>

              <div className="flex gap-2">
                <Button variant="success" size="sm" loading={guardando}
                        onClick={guardar} icon={<Save size={14} />}>
                  {editandoId ? 'Guardar cambios' : 'Registrar intervención'}
                </Button>
                {editandoId && (
                  <Button variant="secondary" size="sm"
                          onClick={() => { setEditandoId(null); setBorrador(borradorVacio(periodo)); }}>
                    Cancelar
                  </Button>
                )}
              </div>
            </div>
          )}

          {loading ? <div className="flex justify-center py-6"><Spinner /></div> : (
            <div className="space-y-3">
              {estudiantes.length === 0 && (
                <p className="text-sm text-gray-500">Este curso no tiene estudiantes.</p>
              )}
              {estudiantes.map(e => {
                const filas = historial.get(e.id) || [];
                if (filas.length === 0) return null;
                return (
                  <div key={e.id} className="border rounded-lg p-3">
                    <p className="font-medium text-gray-800 text-sm">{e.nombre_completo}</p>
                    <ul className="mt-1 space-y-1">
                      {filas.map(i => (
                        <li key={i.id}
                            className={`text-xs border-l-2 pl-2 ${i.activo ? 'border-blue-300' : 'border-gray-300 opacity-60 line-through'}`}>
                          <span className="font-medium">
                            P{i.periodo} · {etiquetaCompetencia(i.competencia_numero)} ·{' '}
                            <span className={i.resultado === 'lograda' ? 'text-green-700' : 'text-amber-700'}>
                              {etiquetaResultado(i.resultado)}
                            </span>
                          </span>
                          <span className="text-gray-500"> — {i.aspectos_no_logrados}</span>
                          {!i.activo && i.motivo_retiro && (
                            <span className="text-gray-400"> (retirada: {i.motivo_retiro})</span>
                          )}
                          {puedeModificar(i, user?.id, esProfesor) && (
                            <span className="ml-2 inline-flex gap-2">
                              <button className="text-blue-600 hover:underline"
                                      onClick={() => editar(i)}>Editar</button>
                              <button className="text-red-600 hover:underline inline-flex items-center gap-0.5"
                                      onClick={() => retirar(i)}>
                                <Trash2 size={11} /> Retirar
                              </button>
                            </span>
                          )}
                          {puedeRetiroAdmin && i.activo && (
                            <button className="ml-2 text-red-600 hover:underline"
                                    onClick={() => retirar(i)}>Retirar</button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};
