import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { Select, Button, Alert, Spinner } from '../../components/ui';
import { Target, Save, Trash2, CheckCircle2, Circle } from 'lucide-react';

const MAX_CHARS = 4000;
const PERIODOS = [1, 2, 3, 4];

interface Indicador {
  id: number;
  curso_id: number;
  asignatura_id: number;
  asignatura: string | null;
  periodo: number;
  contenido: string | null;
  profesor: string | null;
  actualizado_en: string | null;
}

interface Curso {
  id: number;
  nombre_completo?: string;
  nombre?: string;
  grado?: string;
}

interface Asignatura {
  id: number;
  nombre: string;
}

interface Asignacion {
  curso_id: number;
  curso: string | null;
  asignatura_id: number;
  asignatura: string | null;
  activo: boolean;
}

export const IndicadoresLogroPage = () => {
  const { user } = useAuth();
  const esProfesor = user?.role === 'profesor';

  const [cursos, setCursos] = useState<Curso[]>([]);
  const [asignaturas, setAsignaturas] = useState<Asignatura[]>([]);
  const [asignaciones, setAsignaciones] = useState<Asignacion[]>([]);
  const [indicadores, setIndicadores] = useState<Indicador[]>([]);

  const [cursoId, setCursoId] = useState<number | ''>('');
  const [asignaturaId, setAsignaturaId] = useState<number | ''>('');
  const [periodo, setPeriodo] = useState<number>(1);
  const [texto, setTexto] = useState('');

  const [loading, setLoading] = useState(true);
  const [cargandoTabla, setCargandoTabla] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  // ── carga inicial ────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const [cursosRes, asigRes, asignacRes] = await Promise.all([
          api.get('/cursos'),
          api.get('/asignaturas'),
          api.get('/asignaciones'),
        ]);
        setCursos(cursosRes.data || []);
        setAsignaturas(asigRes.data || []);
        setAsignaciones((asignacRes.data || []).filter((a: Asignacion) => a.activo));
      } catch (e: any) {
        setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudieron cargar los datos' });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // El profesor solo puede elegir los cursos donde tiene asignación activa.
  // Dirección/coordinación ven los cursos de su colegio (ya filtrados por la
  // lente de nivel del backend en /cursos).
  const cursosDisponibles = useMemo(() => {
    if (!esProfesor) return cursos;
    const ids = new Set(asignaciones.map((a) => a.curso_id));
    return cursos.filter((c) => ids.has(c.id));
  }, [esProfesor, cursos, asignaciones]);

  // R2-final-guard: para TODOS los roles, al elegir un curso solo se ofrecen
  // las asignaturas ACADÉMICAS de ese curso (las que tienen asignación activa),
  // nunca el catálogo completo del colegio. Evita crear indicadores huérfanos.
  // Es la misma fuente que valida el backend.
  const asignaturasDisponibles = useMemo(() => {
    if (!cursoId) return [];
    // `/asignaciones` ya viene acotado por rol: al profesor le devuelve solo
    // las suyas; a dirección/coordinación, todas las del colegio. Por eso el
    // mismo filtro sirve para ambos.
    const ids = new Set(
      asignaciones.filter((a) => a.curso_id === cursoId).map((a) => a.asignatura_id)
    );
    return asignaturas.filter((a) => ids.has(a.id));
  }, [cursoId, asignaturas, asignaciones]);

  // ── indicadores del par seleccionado ─────────────────────────────────
  const cargarIndicadores = async () => {
    if (!cursoId || !asignaturaId) {
      setIndicadores([]);
      return;
    }
    setCargandoTabla(true);
    try {
      const res = await api.get(
        `/indicadores-logro?curso_id=${cursoId}&asignatura_id=${asignaturaId}`
      );
      setIndicadores(res.data || []);
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudieron cargar los indicadores' });
      setIndicadores([]);
    } finally {
      setCargandoTabla(false);
    }
  };

  useEffect(() => {
    cargarIndicadores();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursoId, asignaturaId]);

  const actual = useMemo(
    () => indicadores.find((i) => i.periodo === periodo) || null,
    [indicadores, periodo]
  );

  useEffect(() => {
    setTexto(actual?.contenido || '');
  }, [actual, periodo]);

  const cambioSinGuardar = (actual?.contenido || '') !== texto;
  // R2-hardening: vaciar la casilla NO se hace con Guardar (un POST vacío ya
  // nunca borra en el backend). La única vía es el botón Eliminar.
  const intentaVaciar = !!actual && texto.trim().length === 0;
  const puedeGuardar = cambioSinGuardar && !intentaVaciar && texto.trim().length > 0;

  // ── acciones ─────────────────────────────────────────────────────────
  const guardar = async () => {
    if (!cursoId || !asignaturaId) {
      setMensaje({ tipo: 'error', texto: 'Selecciona el curso y la asignatura' });
      return;
    }
    if (texto.length > MAX_CHARS) {
      setMensaje({ tipo: 'error', texto: `El texto supera ${MAX_CHARS} caracteres` });
      return;
    }
    if (!texto.trim()) {
      setMensaje({
        tipo: 'error',
        texto: actual
          ? 'El contenido está vacío. Usa Eliminar si deseas borrar este indicador.'
          : 'Escribe los indicadores antes de guardar.',
      });
      return;
    }
    setSaving(true);
    setMensaje(null);
    try {
      await api.post('/indicadores-logro', {
        curso_id: cursoId,
        asignatura_id: asignaturaId,
        periodo,
        contenido: texto.trim(),
      });
      setMensaje({ tipo: 'success', texto: `Indicadores del Período ${periodo} guardados` });
      await cargarIndicadores();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo guardar' });
    } finally {
      setSaving(false);
    }
  };

  const eliminar = async () => {
    if (!actual) return;
    if (!window.confirm(
      `¿Eliminar los indicadores del Período ${periodo}? Esta casilla quedará vacía en el Registro Escolar.`
    )) return;
    setSaving(true);
    try {
      await api.delete(`/indicadores-logro/${actual.id}`);
      setMensaje({ tipo: 'success', texto: `Indicadores del Período ${periodo} eliminados` });
      setTexto('');
      await cargarIndicadores();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo eliminar' });
    } finally {
      setSaving(false);
    }
  };

  const nombreCurso = (c: Curso) => c.nombre_completo || c.nombre || `Curso ${c.id}`;

  if (loading) {
    return (
      <div className="flex justify-center items-center py-20">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-blue-50 text-blue-600 shrink-0">
          <Target size={22} />
        </div>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-800">Indicadores de Logro</h1>
          <p className="text-sm text-gray-500">
            Lo que registres aquí se imprime en el Registro Escolar, en la tabla
            “Especificación curricular aplicada por período”, columna “Indicadores de Logro”.
          </p>
        </div>
      </div>

      {mensaje && (
        <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>
          {mensaje.texto}
        </Alert>
      )}

      {/* Selección de curso y asignatura */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Curso"
            value={cursoId}
            placeholder="Selecciona un curso…"
            options={cursosDisponibles.map((c) => ({ value: c.id, label: nombreCurso(c) }))}
            onChange={(e) => {
              setCursoId(e.target.value ? Number(e.target.value) : '');
              setAsignaturaId('');
            }}
          />

          <Select
            label="Asignatura"
            value={asignaturaId}
            disabled={!cursoId}
            placeholder={cursoId ? 'Selecciona una asignatura…' : 'Elige primero el curso'}
            options={asignaturasDisponibles.map((a) => ({ value: a.id, label: a.nombre }))}
            onChange={(e) => setAsignaturaId(e.target.value ? Number(e.target.value) : '')}
          />
        </div>

        {!!cursoId && asignaturasDisponibles.length === 0 && (
          <p className="mt-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            Este curso no tiene asignaturas con profesor asignado. Asigna primero
            las asignaturas del curso en <strong>Asignaciones</strong>.
          </p>
        )}

        {esProfesor && cursosDisponibles.length === 0 && (
          <p className="mt-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            No tienes cursos con asignación activa. Pide a Dirección que te asigne
            curso y asignatura.
          </p>
        )}
      </div>

      {/* Estado por período + editor */}
      {cursoId && asignaturaId ? (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 sm:p-5 space-y-4">
          {/* Estado P1-P4 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {PERIODOS.map((p) => {
              const lleno = indicadores.some(
                (i) => i.periodo === p && (i.contenido || '').trim().length > 0
              );
              const activo = p === periodo;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriodo(p)}
                  className={[
                    'flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition',
                    activo
                      ? 'border-blue-500 bg-blue-50 text-blue-700 ring-1 ring-blue-500'
                      : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50',
                  ].join(' ')}
                  aria-pressed={activo}
                >
                  {lleno ? (
                    <CheckCircle2 size={16} className="text-green-600 shrink-0" />
                  ) : (
                    <Circle size={16} className="text-gray-300 shrink-0" />
                  )}
                  <span className="truncate">
                    P{p} · {lleno ? 'completado' : 'pendiente'}
                  </span>
                </button>
              );
            })}
          </div>

          {cargandoTabla ? (
            <div className="flex justify-center py-10"><Spinner /></div>
          ) : (
            <>
              <div>
                <label
                  htmlFor="indicadores-texto"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Indicadores de logro trabajados — Período {periodo}
                </label>
                <textarea
                  id="indicadores-texto"
                  value={texto}
                  onChange={(e) => setTexto(e.target.value.slice(0, MAX_CHARS))}
                  rows={12}
                  maxLength={MAX_CHARS}
                  placeholder="Ej.: IL-1 Expresa sus ideas a través de textos, de manera oral y escrita…"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
                             resize-y min-h-[160px]"
                />
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className={texto.length > MAX_CHARS * 0.9 ? 'text-amber-600' : 'text-gray-400'}>
                    {texto.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} caracteres
                  </span>
                  {actual?.actualizado_en && (
                    <span className="text-gray-400">
                      Última edición: {new Date(actual.actualizado_en).toLocaleString()}
                      {actual.profesor ? ` · ${actual.profesor}` : ''}
                    </span>
                  )}
                </div>
              </div>

              {intentaVaciar && (
                <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  Dejar el texto en blanco no borra la casilla. Para vaciarla en el
                  Registro Escolar usa <strong>Eliminar período</strong>.
                </p>
              )}

              <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
                {actual && (
                  <Button variant="danger" onClick={eliminar} disabled={saving}>
                    <Trash2 size={16} className="mr-1" /> Eliminar período
                  </Button>
                )}
                <Button onClick={guardar} disabled={saving || !puedeGuardar}>
                  <Save size={16} className="mr-1" />
                  {saving ? 'Guardando…' : cambioSinGuardar ? 'Guardar' : 'Guardado'}
                </Button>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-dashed border-gray-200 p-10 text-center">
          <Target size={28} className="mx-auto text-gray-300 mb-2" />
          <p className="text-gray-500 text-sm">
            Selecciona un curso y una asignatura para registrar sus indicadores de logro.
          </p>
        </div>
      )}
    </div>
  );
};
