import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { Select, Button, Alert, Spinner } from '../../components/ui';
import { Target, Save, Eraser, Search, ChevronDown, ChevronRight, Info } from 'lucide-react';

const MAX_CHARS = 4000;
const PERIODOS = [1, 2, 3, 4];

/** Un indicador oficial del catálogo MINERD. El texto NO se escribe a mano. */
interface IndicadorCatalogo {
  catalogo_clave: string;
  il_codigo: string;
  il_texto: string;
  orden_il: number;
}

interface CompetenciaEspecifica {
  ce_codigo: string;
  ce_texto: string;
  orden_ce: number;
  indicadores: IndicadorCatalogo[];
}

interface CompetenciaFundamental {
  competencia_fundamental_codigo: string;
  competencia_fundamental_nombre: string;
  competencias_especificas: CompetenciaEspecifica[];
}

interface Catalogo {
  grado_numero: number;
  area_codigo: string;
  area_nombre: string;
  version: string;
  competencias: CompetenciaFundamental[];
  usado_en_periodos: Record<string, number[]>;
}

interface Seleccion {
  catalogo_clave: string;
  il_codigo?: string;
  ce_codigo?: string;
}

interface Periodo {
  id: number;
  periodo: number;
  contenidos_claves: string | null;
  selecciones: Seleccion[];
  estado: 'pendiente' | 'parcial' | 'completo';
  profesor: string | null;
  actualizado_en: string | null;
}

interface Curso { id: number; nombre_completo?: string; nombre?: string; grado?: string }
interface Asignatura { id: number; nombre: string }
interface Asignacion { curso_id: number; asignatura_id: number; activo: boolean }

const ETIQUETA_ESTADO: Record<string, { texto: string; clase: string }> = {
  pendiente: { texto: 'Pendiente', clase: 'bg-gray-100 text-gray-600' },
  parcial: { texto: 'Parcial', clase: 'bg-amber-100 text-amber-700' },
  completo: { texto: 'Completo', clase: 'bg-green-100 text-green-700' },
};

export const IndicadoresLogroPage = () => {
  const { user } = useAuth();
  // R2.1E: la ruta ya es profesor-only, pero el filtro de cursos se conserva
  // por defensa en profundidad. `esDireccion` desapareció con el mensaje que
  // remitía a Configuración: esa pantalla no es del profesor.
  const esProfesor = user?.role === 'profesor';

  const [cursos, setCursos] = useState<Curso[]>([]);
  const [asignaturas, setAsignaturas] = useState<Asignatura[]>([]);
  const [asignaciones, setAsignaciones] = useState<Asignacion[]>([]);
  const [periodos, setPeriodos] = useState<Periodo[]>([]);
  const [catalogo, setCatalogo] = useState<Catalogo | null>(null);
  const [sinVinculo, setSinVinculo] = useState<string | null>(null);

  const [cursoId, setCursoId] = useState<number | ''>('');
  const [asignaturaId, setAsignaturaId] = useState<number | ''>('');
  const [periodo, setPeriodo] = useState<number>(1);

  // Borrador local del período en edición
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [contenidos, setContenidos] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());

  const [loading, setLoading] = useState(true);
  const [cargando, setCargando] = useState(false);
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

  const cursosDisponibles = useMemo(() => {
    if (!esProfesor) return cursos;
    const ids = new Set(asignaciones.map((a) => a.curso_id));
    return cursos.filter((c) => ids.has(c.id));
  }, [esProfesor, cursos, asignaciones]);

  // Solo las asignaturas ACADÉMICAS del curso (con asignación activa): la misma
  // fuente que valida el backend, para todos los roles.
  const asignaturasDisponibles = useMemo(() => {
    if (!cursoId) return [];
    const ids = new Set(asignaciones.filter((a) => a.curso_id === cursoId).map((a) => a.asignatura_id));
    return asignaturas.filter((a) => ids.has(a.id));
  }, [cursoId, asignaturas, asignaciones]);

  // ── estado del par + catálogo ────────────────────────────────────────
  const cargarTodo = useCallback(async () => {
    if (!cursoId || !asignaturaId) {
      setPeriodos([]); setCatalogo(null); setSinVinculo(null);
      return;
    }
    setCargando(true);
    setSinVinculo(null);
    try {
      const estadoRes = await api.get(`/indicadores-logro?curso_id=${cursoId}&asignatura_id=${asignaturaId}`);
      setPeriodos(estadoRes.data || []);
    } catch (e: any) {
      setPeriodos([]);
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo cargar el estado' });
    }
    try {
      const catRes = await api.get(`/indicadores-logro/catalogo?curso_id=${cursoId}&asignatura_id=${asignaturaId}`);
      setCatalogo(catRes.data);
      // Abrir la primera competencia para no dejar la pantalla "muerta".
      const primera = catRes.data?.competencias?.[0]?.competencia_fundamental_codigo;
      setAbiertas(primera ? new Set([primera]) : new Set());
    } catch (e: any) {
      setCatalogo(null);
      if (e.response?.status === 409 && e.response?.data?.motivo === 'sin_vinculo_curricular') {
        setSinVinculo(e.response.data.error);
      } else {
        setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo cargar el catálogo' });
      }
    } finally {
      setCargando(false);
    }
  }, [cursoId, asignaturaId]);

  useEffect(() => { cargarTodo(); }, [cargarTodo]);

  const actual = useMemo(() => periodos.find((p) => p.periodo === periodo) || null, [periodos, periodo]);

  // Sincroniza el borrador con el período cargado
  useEffect(() => {
    setMarcadas(new Set((actual?.selecciones || []).map((s) => s.catalogo_clave)));
    setContenidos(actual?.contenidos_claves || '');
  }, [actual, periodo]);

  // ── cambios sin guardar ──────────────────────────────────────────────
  const guardadas = useMemo(
    () => new Set((actual?.selecciones || []).map((s) => s.catalogo_clave)),
    [actual]
  );
  const hayCambios = useMemo(() => {
    if ((actual?.contenidos_claves || '') !== contenidos) return true;
    if (guardadas.size !== marcadas.size) return true;
    for (const k of marcadas) if (!guardadas.has(k)) return true;
    return false;
  }, [actual, contenidos, guardadas, marcadas]);

  useEffect(() => {
    if (!hayCambios) return;
    const aviso = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', aviso);
    return () => window.removeEventListener('beforeunload', aviso);
  }, [hayCambios]);

  /** Pide confirmación antes de descartar el borrador. */
  const confirmarDescartar = () =>
    !hayCambios || window.confirm('Tienes cambios sin guardar en este período. ¿Descartarlos?');

  const cambiarCurso = (v: number | '') => { if (confirmarDescartar()) { setCursoId(v); setAsignaturaId(''); } };
  const cambiarAsignatura = (v: number | '') => { if (confirmarDescartar()) setAsignaturaId(v); };
  const cambiarPeriodo = (p: number) => { if (confirmarDescartar()) setPeriodo(p); };

  // ── selección ────────────────────────────────────────────────────────
  const alternar = (clave: string) => {
    setMarcadas((prev) => {
      const s = new Set(prev);
      if (s.has(clave)) s.delete(clave); else s.add(clave);
      return s;
    });
  };

  const alternarGrupo = (codigo: string) => {
    setAbiertas((prev) => {
      const s = new Set(prev);
      if (s.has(codigo)) s.delete(codigo); else s.add(codigo);
      return s;
    });
  };

  // Filtrado local por código o texto: instantáneo y sin ida al servidor.
  const competenciasVisibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    const comps = catalogo?.competencias || [];
    if (!q) return comps;
    const norm = (t: string) => t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    const nq = norm(q);
    return comps
      .map((cf) => ({
        ...cf,
        competencias_especificas: cf.competencias_especificas
          .map((ce) => ({
            ...ce,
            indicadores: ce.indicadores.filter(
              (il) => norm(il.il_codigo).includes(nq) || norm(il.il_texto).includes(nq)
            ),
          }))
          .filter((ce) => ce.indicadores.length > 0),
      }))
      .filter((cf) => cf.competencias_especificas.length > 0);
  }, [catalogo, busqueda]);

  // Con búsqueda activa se abre todo: si no, los resultados quedarían ocultos.
  const grupoAbierto = (codigo: string) => !!busqueda.trim() || abiertas.has(codigo);

  const marcadasEnCF = (cf: CompetenciaFundamental) =>
    cf.competencias_especificas.reduce(
      (n, ce) => n + ce.indicadores.filter((il) => marcadas.has(il.catalogo_clave)).length, 0);

  const marcadasEnCE = (ce: CompetenciaEspecifica) =>
    ce.indicadores.filter((il) => marcadas.has(il.catalogo_clave)).length;

  const usadoEn = (clave: string) =>
    (catalogo?.usado_en_periodos?.[clave] || []).filter((p) => p !== periodo);

  const lineasContenidos = contenidos.split('\n').filter((l) => l.trim()).length;

  const estadoBorrador: 'pendiente' | 'parcial' | 'completo' =
    marcadas.size && lineasContenidos ? 'completo'
      : (marcadas.size || lineasContenidos) ? 'parcial' : 'pendiente';

  // ── guardar / limpiar ────────────────────────────────────────────────
  const guardar = async () => {
    if (!cursoId || !asignaturaId) return;
    setSaving(true);
    setMensaje(null);
    try {
      await api.post('/indicadores-logro/periodo', {
        curso_id: cursoId,
        asignatura_id: asignaturaId,
        periodo,
        catalogo_claves: Array.from(marcadas),
        contenidos_claves: contenidos,
      });
      setMensaje({ tipo: 'success', texto: `Período ${periodo} guardado` });
      await cargarTodo();
    } catch (e: any) {
      const d = e.response?.data;
      setMensaje({
        tipo: 'error',
        texto: [d?.error, ...(d?.detalles || [])].filter(Boolean).join(' ') || 'No se pudo guardar',
      });
    } finally {
      setSaving(false);
    }
  };

  const limpiar = async () => {
    if (!cursoId || !asignaturaId) return;
    if (!window.confirm(
      `Se borrarán los indicadores seleccionados y los contenidos claves del período ${periodo}. ` +
      'Los demás períodos no se tocan. ¿Continuar?'
    )) return;
    setSaving(true);
    try {
      await api.delete(
        `/indicadores-logro/periodo?curso_id=${cursoId}&asignatura_id=${asignaturaId}&periodo=${periodo}`
      );
      setMensaje({ tipo: 'success', texto: `Período ${periodo} limpiado` });
      await cargarTodo();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'No se pudo limpiar el período' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="flex justify-center py-16"><Spinner /></div>;

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <Target className="w-6 h-6 text-blue-600 shrink-0" />
        <h1 className="text-xl sm:text-2xl font-bold">Indicadores de Logro</h1>
      </div>

      {mensaje && (
        <div className="mb-4">
          <Alert variant={mensaje.tipo === 'success' ? 'success' : 'error'}>{mensaje.texto}</Alert>
        </div>
      )}

      {/* Selectores: apilados en móvil */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        <Select
          label="Curso"
          value={cursoId}
          onChange={(e) => cambiarCurso(e.target.value ? parseInt(e.target.value) : '')}
          options={cursosDisponibles.map((c) => ({ value: c.id, label: c.nombre_completo || c.nombre || `Curso ${c.id}` }))}
          placeholder="Seleccionar curso"
        />
        <Select
          label="Asignatura"
          value={asignaturaId}
          onChange={(e) => cambiarAsignatura(e.target.value ? parseInt(e.target.value) : '')}
          options={asignaturasDisponibles.map((a) => ({ value: a.id, label: a.nombre }))}
          placeholder={cursoId ? 'Seleccionar asignatura' : 'Elige un curso primero'}
        />
      </div>

      {cursoId && asignaturaId && (
        <>
          {/* Períodos */}
          <div className="flex flex-wrap gap-2 mb-4">
            {PERIODOS.map((p) => {
              const est = periodos.find((x) => x.periodo === p)?.estado || 'pendiente';
              const et = ETIQUETA_ESTADO[p === periodo ? estadoBorrador : est];
              return (
                <button
                  key={p}
                  onClick={() => cambiarPeriodo(p)}
                  className={`px-3 py-2 rounded-lg border text-sm font-medium transition ${
                    p === periodo ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  P{p}
                  <span className={`ml-2 px-2 py-0.5 rounded-full text-[11px] ${et.clase}`}>{et.texto}</span>
                </button>
              );
            })}
          </div>

          {cargando && <div className="flex justify-center py-10"><Spinner /></div>}

          {/* Asignatura sin bloque oficial en el Registro: NO es un error.
              R2.1E: esta pantalla es del profesor, así que el mensaje no lo
              manda a Configuración —no es su pantalla— sino a Dirección. */}
          {!cargando && sinVinculo && (
            <Alert variant="info">
              <div className="flex gap-2">
                <Info className="w-5 h-5 shrink-0 mt-0.5" />
                <div>
                  <p>
                    Esta asignatura no forma parte de un bloque curricular del Registro
                    Escolar de Secundaria. Si consideras que debería estar vinculada,
                    comunícalo a Dirección.
                  </p>
                </div>
              </div>
            </Alert>
          )}

          {!cargando && catalogo && (
            <>
              <p className="text-sm text-gray-500 mb-3">
                {catalogo.area_nombre} · {catalogo.grado_numero}.º de Secundaria · catálogo {catalogo.version}
              </p>

              {/* Buscador */}
              <div className="relative mb-3">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                  placeholder="Buscar por código o texto… (ej. IL-19, argumentativas)"
                  className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm"
                />
              </div>

              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold text-gray-800">Competencias e Indicadores de Logro</h2>
                <span className="text-sm text-gray-600">
                  {marcadas.size} {marcadas.size === 1 ? 'indicador seleccionado' : 'indicadores seleccionados'}
                </span>
              </div>

              {competenciasVisibles.length === 0 && (
                <p className="text-sm text-gray-500 py-6 text-center">Sin coincidencias para esa búsqueda.</p>
              )}

              <div className="space-y-2 mb-6">
                {competenciasVisibles.map((cf) => {
                  const abierto = grupoAbierto(cf.competencia_fundamental_codigo);
                  const nCF = marcadasEnCF(cf);
                  return (
                    <div key={cf.competencia_fundamental_codigo} className="border border-gray-200 rounded-lg overflow-hidden">
                      <button
                        onClick={() => alternarGrupo(cf.competencia_fundamental_codigo)}
                        className="w-full flex items-center gap-2 px-3 py-3 bg-gray-50 hover:bg-gray-100 text-left"
                      >
                        {abierto ? <ChevronDown className="w-4 h-4 shrink-0" /> : <ChevronRight className="w-4 h-4 shrink-0" />}
                        <span className="font-medium text-sm flex-1 break-words">
                          {cf.competencia_fundamental_nombre}
                        </span>
                        {nCF > 0 && (
                          <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 text-[11px] shrink-0">
                            {nCF} seleccionado{nCF === 1 ? '' : 's'}
                          </span>
                        )}
                      </button>

                      {abierto && (
                        <div className="p-3 space-y-4">
                          {cf.competencias_especificas.map((ce) => (
                            <div key={`${ce.orden_ce}-${ce.ce_codigo}`}>
                              <div className="mb-2">
                                <div className="flex items-baseline gap-2 flex-wrap">
                                  <span className="font-mono text-xs font-semibold text-gray-700">{ce.ce_codigo}</span>
                                  {marcadasEnCE(ce) > 0 && (
                                    <span className="text-[11px] text-blue-700">{marcadasEnCE(ce)} seleccionado{marcadasEnCE(ce) === 1 ? '' : 's'}</span>
                                  )}
                                </div>
                                <p className="text-xs text-gray-600 break-words">{ce.ce_texto}</p>
                              </div>
                              <ul className="space-y-2">
                                {ce.indicadores.map((il) => {
                                  const otros = usadoEn(il.catalogo_clave);
                                  return (
                                    <li key={il.catalogo_clave}>
                                      <label className="flex gap-3 items-start cursor-pointer p-2 rounded hover:bg-gray-50">
                                        <input
                                          type="checkbox"
                                          checked={marcadas.has(il.catalogo_clave)}
                                          onChange={() => alternar(il.catalogo_clave)}
                                          className="mt-0.5 w-5 h-5 shrink-0 accent-blue-600"
                                        />
                                        <span className="text-sm break-words">
                                          <span className="font-mono font-semibold mr-1">{il.il_codigo}</span>
                                          {il.il_texto}
                                          {otros.length > 0 && (
                                            <span className="ml-2 px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-[11px] whitespace-nowrap">
                                              Usado en {otros.map((p) => `P${p}`).join(', ')}
                                            </span>
                                          )}
                                        </span>
                                      </label>
                                    </li>
                                  );
                                })}
                              </ul>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Contenidos Claves */}
              <div className="mb-4">
                <label className="block font-semibold text-gray-800 mb-1">Contenidos Claves trabajados</label>
                <p className="text-xs text-gray-500 mb-2">Escribe un contenido por línea.</p>
                <textarea
                  value={contenidos}
                  onChange={(e) => setContenidos(e.target.value.slice(0, MAX_CHARS))}
                  rows={6}
                  placeholder={'Personal pronouns\nPossessive pronouns\nPossessive adjectives\nSentences with possessive adjectives'}
                  className="w-full p-3 border border-gray-200 rounded-lg text-sm font-mono"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>{lineasContenidos} {lineasContenidos === 1 ? 'contenido' : 'contenidos'}</span>
                  <span>{contenidos.length}/{MAX_CHARS}</span>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-2 sm:items-center sticky bottom-0 bg-white py-3 border-t border-gray-100">
                <Button onClick={guardar} loading={saving} disabled={!hayCambios}>
                  <Save className="w-4 h-4 mr-2" /> Guardar período {periodo}
                </Button>
                <Button variant="secondary" onClick={limpiar} disabled={saving || !actual}>
                  <Eraser className="w-4 h-4 mr-2" /> Limpiar período
                </Button>
                {hayCambios && <span className="text-xs text-amber-700">Tienes cambios sin guardar</span>}
                {actual?.profesor && !hayCambios && (
                  <span className="text-xs text-gray-500 sm:ml-auto">Última edición: {actual.profesor}</span>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};

export default IndicadoresLogroPage;
