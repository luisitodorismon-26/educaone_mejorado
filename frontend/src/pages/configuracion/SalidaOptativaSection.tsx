import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Button, Select, Alert } from '../../components/ui';
import { labelCurso, CursoEtiquetable } from '../../utils/labelCurso';

/**
 * Salida Optativa de un curso de 4to-6to de Secundaria.
 *
 * Vive DENTRO del modal de edición del curso (Configuración → Cursos), no en
 * un item nuevo del menú.
 *
 * Dos zonas:
 *   1. ASIGNACIONES GUARDADAS — lo que confirmó el servidor: salida, componente,
 *      profesor y estado. Nada de lo que se pinta aquí sale de otra fuente.
 *   2. AÑADIR — «Seleccionar salida» solo sirve para EXPLORAR el catálogo del
 *      grado: muestra los componentes de esa salida, cada uno con su profesor y
 *      su botón «Guardar asignación». Cambiarlo NO guarda nada ni retira nada.
 *
 * Todo lo que se pinta sale del backend —las 4 salidas y los componentes del
 * grado llegan en la respuesta—, así que el frontend NO tiene ninguna copia
 * del catálogo MINERD que pueda quedar desincronizada.
 */

interface ComponenteEstado {
  componente_codigo: string;
  nombre_oficial: string;
  slot: number;
  horas_semana: number;
  asignatura_id: number | null;
  asignatura_nombre: string | null;
  tiene_historia: boolean;
  identidad_independiente: boolean;
  profesor_id: number | null;
  profesor_nombre: string | null;
  salida_codigo: string;
  salida_nombre: string;
  de_la_salida_del_curso: boolean;
  orden_impresion: number;
  candidatas: Candidata[];
}

// Asignatura que el curso ya usó para un componente y que hoy no está
// vinculada. Si existe, Dirección elige: el sistema no crea otra ni escoge.
interface Candidata {
  asignatura_id: number;
  nombre: string;
  activo: boolean;
  historia: { tabla: string; filas: number }[];
  historia_resumen: string;
  asignaciones: { profesor_id: number; profesor_nombre: string | null; activo: boolean }[];
}

interface ComponenteDisponible {
  componente_codigo: string;
  nombre_oficial: string;
  slot: number;
  horas_semana: number;
  salida_codigo: string;
  salida_nombre: string;
  candidatas: Candidata[];
}

interface Profesor {
  id: number;
  nombre_completo?: string;
  nombre?: string;
  apellido?: string;
  role?: string;
  activo?: boolean;
}

interface SalidaEstado {
  curso_id: number;
  aplica: boolean;
  grado_numero: number | null;
  salida_optativa_codigo: string | null;
  salida_optativa_nombre: string | null;
  salidas_disponibles: { codigo: string; nombre: string }[];
  componentes: ComponenteEstado[];
  faltantes: string[];
  configurada: boolean;
  modo: 'salida' | 'componentes';
  capacidad_registro: number;
  espacios_en_uso: number;
  excede_capacidad: boolean;
  mensaje_capacidad: string | null;
  componentes_disponibles: ComponenteDisponible[];
}

interface Asignatura {
  id: number;
  nombre: string;
}

// Componente del catálogo del grado, visto desde «Seleccionar salida».
interface FilaCatalogo {
  componente_codigo: string;
  nombre_oficial: string;
  salida_codigo: string;
  guardado: ComponenteEstado | null;      // si ya está en el curso con asignatura
  candidatas: Candidata[];
  slot: number;
}

// Lo que el servidor guarda como historia, dicho en lenguaje del colegio.
const TABLAS_LEGIBLES: Record<string, string> = {
  calificaciones_secundaria: 'notas',
  calificaciones: 'notas',
  evaluaciones_extra_secundaria: 'evaluaciones completivas o extraordinarias',
  asistencias: 'asistencias',
  indicadores_logro: 'indicadores de logro',
  items_completivos: 'evaluaciones completivas',
  eval_interna_estudiante: 'evaluaciones internas',
};

const describirCandidata = (c: Candidata) => {
  const datos = (c.historia || []).map(h => `${h.filas} ${TABLAS_LEGIBLES[h.tabla] || 'registros'}`);
  const profes = c.asignaciones.map(a =>
    `${a.profesor_nombre || 'profesor sin nombre'}${a.activo ? '' : ' (ya no asignado)'}`);
  return [
    datos.length ? `con ${datos.join(', ')}` : 'sin notas ni asistencias',
    profes.length ? `profesor anterior: ${profes.join(', ')}` : '',
    c.activo ? '' : 'asignatura desactivada: hay que reactivarla en Asignaturas para usarla',
  ].filter(Boolean).join(' · ');
};

// Elección explícita cuando el curso ya tiene asignaturas de ese componente
// sin vincular. Sin números internos: se describen por sus datos.
const ElegirAsignatura = ({ nombre, candidatas, valor, onChange }: {
  nombre: string;
  candidatas: Candidata[];
  valor: number | 'nueva' | null;
  onChange: (v: number | 'nueva') => void;
}) => (
  <div className="border rounded-md p-2 bg-amber-50 text-xs space-y-1 mt-2">
    <p className="text-amber-800">
      Este curso ya tuvo {candidatas.length === 1 ? 'una asignatura' : `${candidatas.length} asignaturas`} para
      este componente que hoy no están en uso. Elige cuál conservar para no duplicarla: el sistema no
      elige ni crea ninguna por su cuenta.
    </p>
    {candidatas.map((cand, i) => (
      <label key={cand.asignatura_id} className="flex gap-2 items-start" title={`ref. ${cand.asignatura_id}`}>
        <input type="radio" name={nombre}
          checked={valor === cand.asignatura_id}
          disabled={!cand.activo}
          onChange={() => onChange(cand.asignatura_id)} />
        <span>
          <strong>{candidatas.length > 1 ? `Opción ${String.fromCharCode(65 + i)}` : 'La existente'}</strong>
          {': '}{describirCandidata(cand)}
        </span>
      </label>
    ))}
    <label className="flex gap-2 items-start">
      <input type="radio" name={nombre} checked={valor === 'nueva'} onChange={() => onChange('nueva')} />
      <span>Ninguna: empezar con una asignatura nueva</span>
    </label>
  </div>
);

interface Eleccion {
  seleccionado: boolean;          // casilla marcada en «Componentes de esta salida»
  profesorId: number | null;
  identidad: number | 'nueva' | null;
}

const Punto = ({ color }: { color: string }) => (
  <span className={`inline-block w-2 h-2 rounded-full ${color}`} aria-hidden="true" />
);

export const SalidaOptativaSection = ({ cursoId, curso, onCambiosPendientes }: {
  cursoId: number;
  // Solo para rotular. La identidad sigue siendo `cursoId`.
  curso?: CursoEtiquetable;
  // Se mantiene en la firma por compatibilidad con el modal; esta pantalla ya
  // no ofrece el vínculo manual a una asignatura cualquiera.
  asignaturas?: Asignatura[];
  // Componentes con un profesor elegido y SIN guardar. El modal del curso lo
  // usa para avisar antes de cerrarse.
  onCambiosPendientes?: (n: number) => void;
}) => {
  // `estado` es SIEMPRE la última respuesta del servidor.
  const [estado, setEstado] = useState<SalidaEstado | null>(null);
  const [profesores, setProfesores] = useState<Profesor[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // Salida que se está EXPLORANDO. Es local: no es la salida del curso.
  const [explorar, setExplorar] = useState<string>('');
  // Elecciones locales por componente (casilla, profesor y, si hace falta, asignatura).
  const [elecciones, setElecciones] = useState<Record<string, Eleccion>>({});
  // Asignación guardada cuyo profesor se está cambiando desde arriba.
  const [cambiando, setCambiando] = useState<string | null>(null);

  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.get(`/cursos/${cursoId}/salida-optativa`);
      setEstado(r.data);
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo cargar la Salida Optativa');
    } finally {
      setCargando(false);
    }
  };

  const cargarProfesores = async () => {
    try {
      // El servidor solo devuelve usuarios del colegio de quien consulta.
      const r = await api.get('/usuarios');
      setProfesores((r.data || []).filter((u: Profesor) => u.role === 'profesor'));
    } catch {
      setProfesores([]);
    }
  };

  useEffect(() => { cargar(); cargarProfesores(); /* eslint-disable-next-line */ }, [cursoId]);

  const guardados = (estado?.componentes || []).filter(c => c.asignatura_id);
  const eleccionDe = (codigo: string): Eleccion =>
    elecciones[codigo] || { seleccionado: false, profesorId: null, identidad: null };
  const profeGuardado = (codigo: string) =>
    (estado?.componentes || []).find(c => c.componente_codigo === codigo)?.profesor_id ?? null;
  // Pendiente = profesor elegido (en una fila marcada o en «Cambiar profesor»)
  // distinto del que el servidor tiene guardado.
  const esPendiente = (codigo: string) => {
    const e = elecciones[codigo];
    if (!e || !e.profesorId) return false;
    if (!e.seleccionado && cambiando !== codigo) return false;
    return e.profesorId !== profeGuardado(codigo);
  };
  const pendientes = Object.keys(elecciones).filter(esPendiente).length;
  useEffect(() => { onCambiosPendientes?.(pendientes); /* eslint-disable-next-line */ }, [pendientes]);

  const elegir = (codigo: string, cambios: Partial<Eleccion>) =>
    setElecciones(prev => ({ ...prev, [codigo]: { ...(prev[codigo] || { seleccionado: false, profesorId: null, identidad: null }), ...cambios } }));
  const olvidar = (codigos: string[]) =>
    setElecciones(prev => {
      const r = { ...prev };
      codigos.forEach(k => delete r[k]);
      return r;
    });

  // Cambiar la salida que se explora: no envía nada al servidor. Si había
  // profesores elegidos sin guardar en la salida que se deja, se pregunta.
  const cambiarExploracion = (codigo: string) => {
    const enEsta = Object.keys(elecciones).filter(k => esPendiente(k) && k !== cambiando);
    if (enEsta.length && !window.confirm(
        (enEsta.length === 1 ? 'Hay un profesor elegido sin guardar' : `Hay ${enEsta.length} profesores elegidos sin guardar`) +
        ' en la salida que estás viendo. Si cambias de salida se descartarán. ¿Cambiar de todos modos?')) {
      return;
    }
    setElecciones(prev => (cambiando && prev[cambiando] ? { [cambiando]: prev[cambiando] } : {}));
    setExplorar(codigo);
  };

  // POST de UNA asignación; devuelve el estado del servidor o lanza el error.
  const enviar = async (codigo: string) => {
    const e = eleccionDe(codigo);
    const r = await api.post(`/cursos/${cursoId}/salida-optativa/componentes`, {
      componente_codigo: codigo,
      profesor_id: e.profesorId,
      ...(typeof e.identidad === 'number' ? { asignatura_id: e.identidad } : {}),
      ...(e.identidad === 'nueva' ? { crear_identidad_nueva: true } : {}),
    });
    return r.data as SalidaEstado;
  };

  // Guarda las asignaciones indicadas, una a una. Lo que se pinta después es la
  // respuesta del servidor; si una falla, las anteriores ya quedaron guardadas
  // y se dice cuál falló.
  const guardar = async (codigos: string[]) => {
    setError(null);
    setOk(null);
    setGuardando(true);
    const hechos: string[] = [];
    try {
      for (const codigo of codigos) {
        const d = await enviar(codigo);
        setEstado(d);
        const g = d.componentes.find(c => c.componente_codigo === codigo);
        hechos.push(g?.profesor_nombre ? `${g.profesor_nombre} imparte ${g.nombre_oficial}` : codigo);
      }
      setOk(`Asignación guardada: ${hechos.join('; ')}.`);
      if (cambiando && codigos.includes(cambiando)) setCambiando(null);
    } catch (err: any) {
      const d = err.response?.data;
      setError((hechos.length ? `Guardado: ${hechos.join('; ')}. ` : '') +
               (d?.error || 'No se pudo guardar la asignación'));
      // Hay asignaturas del curso que elegir: se recargan para mostrarlas.
      if (d?.motivo === 'identidad_por_elegir') cargar();
    } finally {
      olvidar(codigos.slice(0, hechos.length));
      setGuardando(false);
    }
  };

  const quitar = async (c: ComponenteEstado) => {
    if (!window.confirm(
        `¿Quitar ${c.nombre_oficial} de este curso? ` +
        'La asignatura, sus notas y sus asistencias no se borran; su profesor deja de tenerla asignada.')) {
      return;
    }
    setError(null);
    setOk(null);
    setGuardando(true);
    try {
      const r = await api.delete(`/cursos/${cursoId}/salida-optativa/componentes/${c.componente_codigo}`);
      setEstado(r.data);
      setOk('Componente retirado del curso.');
    } catch (err: any) {
      setError(err.response?.data?.error || 'No se pudo quitar el componente');
    } finally {
      setGuardando(false);
    }
  };

  if (cargando) return <div className="text-sm text-gray-500 py-2">Cargando Salida Optativa…</div>;
  // 1ro-3ro de Secundaria y toda Primaria: la sección NO existe.
  if (!estado || !estado.aplica) return null;

  const opcionesProfe = profesores.map(p => ({
    value: p.id,
    label: p.nombre_completo || `${p.nombre || ''} ${p.apellido || ''}`.trim(),
  }));
  const espaciosLibres = estado.capacidad_registro - guardados.length;
  const nombreSalida = (cod: string) => estado.salidas_disponibles.find(s => s.codigo === cod)?.nombre || cod;

  // Catálogo del grado para la salida que se explora, en el orden oficial.
  const catalogo: FilaCatalogo[] = !explorar ? [] : [
    ...estado.componentes.filter(c => c.salida_codigo === explorar).map(c => ({
      componente_codigo: c.componente_codigo, nombre_oficial: c.nombre_oficial, salida_codigo: c.salida_codigo,
      guardado: c.asignatura_id ? c : null, candidatas: c.candidatas || [], slot: c.slot,
    })),
    ...estado.componentes_disponibles.filter(d => d.salida_codigo === explorar).map(d => ({
      componente_codigo: d.componente_codigo, nombre_oficial: d.nombre_oficial, salida_codigo: d.salida_codigo,
      guardado: null, candidatas: d.candidatas || [], slot: d.slot,
    })),
  ].sort((a, b) => a.slot - b.slot);

  const marcados = catalogo.filter(f => !f.guardado && eleccionDe(f.componente_codigo).seleccionado);
  const listos = marcados.filter(f => {
    const e = eleccionDe(f.componente_codigo);
    return e.profesorId && !(f.candidatas.length > 0 && e.identidad === null);
  });
  const motivoNoGuardar =
    marcados.length === 0 ? 'Marca un componente y elige su profesor.'
      : marcados.length > espaciosLibres
        ? `Solo ${espaciosLibres === 1 ? 'queda 1 espacio' : `quedan ${espaciosLibres} espacios`}: el registro y el boletín admiten ${estado.capacidad_registro} componentes.`
        : listos.length < marcados.length ? 'Falta elegir el profesor (o la asignatura) de algún componente marcado.' : '';

  return (
    <div className="border-t pt-4 mt-2" data-testid="seccion-salidas">
      <h4 className="font-semibold text-gray-800 text-base">Salidas optativas</h4>
      {curso && <p className="text-xs text-gray-500 mb-2">{labelCurso(curso)}</p>}

      {error && <div className="mb-2"><Alert variant="error">{error}</Alert></div>}
      {ok && <div className="mb-2"><Alert variant="success">{ok}</Alert></div>}

      {/* 1. ASIGNACIONES GUARDADAS (confirmadas por el servidor) */}
      {guardados.length === 0 ? (
        <p className="text-sm text-gray-500 border rounded-md px-3 py-2" data-testid="sin-asignaciones">
          Ninguna asignación guardada todavía.
        </p>
      ) : (
        <div className="space-y-2" data-testid="lista-guardadas">
          {guardados.map(c => (
            <div key={c.componente_codigo} data-guardado={c.componente_codigo}
                 className={`rounded-md border px-3 py-2 ${c.profesor_id ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'}`}>
              <div className="flex gap-3">
                <span className={`mt-0.5 flex-none w-5 h-5 rounded-full text-white text-xs flex items-center justify-center ${c.profesor_id ? 'bg-green-600' : 'bg-amber-500'}`}
                      aria-hidden="true">{c.profesor_id ? '✓' : '!'}</span>
                <div className="min-w-0 flex-1">
                  <p className={`text-xs font-medium ${c.profesor_id ? 'text-green-700' : 'text-amber-800'}`} data-testid="estado">
                    {c.profesor_id ? 'Asignación guardada' : 'Guardada sin profesor'}
                  </p>
                  <p className="text-sm font-semibold text-gray-900" data-testid="profesor">
                    {c.profesor_nombre || 'Sin profesor'}
                  </p>
                  <p className="text-sm text-gray-800">{c.nombre_oficial}</p>
                  <p className="text-xs text-gray-500">{c.salida_nombre}</p>
                  {cambiando === c.componente_codigo ? (
                    <div className="mt-2 space-y-2">
                      <Select label="Profesor responsable" value={eleccionDe(c.componente_codigo).profesorId || 0}
                        disabled={guardando}
                        onChange={ev => elegir(c.componente_codigo, { profesorId: parseInt(ev.target.value) || null })}
                        options={opcionesProfe} placeholder="Elegir profesor" />
                      {esPendiente(c.componente_codigo) && (
                        <p className="text-xs text-blue-700 flex items-center gap-1"><Punto color="bg-blue-600" /> Pendiente de guardar</p>
                      )}
                      <div className="flex gap-2">
                        <Button size="sm" loading={guardando} disabled={!esPendiente(c.componente_codigo)}
                          onClick={() => guardar([c.componente_codigo])}>Guardar asignación</Button>
                        <Button size="sm" variant="secondary" disabled={guardando}
                          onClick={() => { olvidar([c.componente_codigo]); setCambiando(null); }}>Cancelar</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-3 mt-1 text-xs">
                      <button type="button" className="text-blue-700 hover:underline disabled:opacity-50" disabled={guardando}
                        onClick={() => { setCambiando(c.componente_codigo);
                          elegir(c.componente_codigo, { profesorId: c.profesor_id, identidad: null }); }}>
                        Cambiar profesor
                      </button>
                      <button type="button" className="text-red-700 hover:underline disabled:opacity-50" disabled={guardando}
                        onClick={() => quitar(c)}>
                        Quitar del curso
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {estado.excede_capacidad && estado.mensaje_capacidad && (
        <div className="mt-2"><Alert variant="error">{estado.mensaje_capacidad}</Alert></div>
      )}

      <hr className="my-4" />

      {/* 2. SELECCIONAR SALIDA: explorar y añadir. No cambia lo guardado. */}
      <p className="text-sm font-semibold text-gray-800 mb-1">Seleccionar salida</p>
      <Select
        label=""
        value={explorar}
        disabled={guardando}
        onChange={e => cambiarExploracion(e.target.value)}
        options={estado.salidas_disponibles.map(s => ({ value: s.codigo, label: s.nombre }))}
        placeholder="Elegir salida"
      />
      <p className="text-xs text-gray-500 mt-1">Sus componentes aparecen debajo.</p>

      {explorar && (
        <div className="mt-2 rounded-md border border-blue-100 overflow-hidden" data-testid="catalogo">
          <div className="bg-blue-50 px-3 py-2">
            <p className="text-sm font-semibold text-gray-800">Componentes de esta salida</p>
            <p className="text-xs text-gray-600">{nombreSalida(explorar)}</p>
          </div>
          <div className="p-2 space-y-2">
            {catalogo.map(f => {
              const e = eleccionDe(f.componente_codigo);
              return (
                <div key={f.componente_codigo} data-catalogo={f.componente_codigo}
                     className={`rounded-md border p-2 ${e.seleccionado ? 'border-blue-300 bg-blue-50/40' : 'bg-white'}`}>
                  <label className="flex gap-3 items-start cursor-pointer">
                    <input type="checkbox" className="mt-1 w-4 h-4"
                      checked={!!f.guardado || e.seleccionado}
                      disabled={!!f.guardado || guardando}
                      onChange={ev => elegir(f.componente_codigo, { seleccionado: ev.target.checked })} />
                    <span className="text-sm font-medium text-gray-800">{f.nombre_oficial}</span>
                  </label>
                  <div className="pl-7 mt-1">
                    {f.guardado ? (
                      <p className="text-xs text-green-700 flex items-center gap-1">
                        <Punto color="bg-green-600" /> Guardado{f.guardado.profesor_nombre ? ` con ${f.guardado.profesor_nombre}` : ''}
                      </p>
                    ) : !e.seleccionado ? (
                      <p className="text-xs text-gray-500 flex items-center gap-1"><Punto color="bg-gray-400" /> No seleccionado</p>
                    ) : (
                      <div className="space-y-2">
                        <Select label="Profesor responsable" value={e.profesorId || 0} disabled={guardando}
                          onChange={ev => elegir(f.componente_codigo, { profesorId: parseInt(ev.target.value) || null })}
                          options={opcionesProfe} placeholder="Elegir profesor" />
                        {f.candidatas.length > 0 && (
                          <ElegirAsignatura nombre={`asig-${f.componente_codigo}`} candidatas={f.candidatas}
                            valor={e.identidad} onChange={v => elegir(f.componente_codigo, { identidad: v })} />
                        )}
                        {esPendiente(f.componente_codigo) ? (
                          <p className="text-xs text-blue-700 flex items-center gap-1"><Punto color="bg-blue-600" /> Pendiente de guardar</p>
                        ) : (
                          <p className="text-xs text-gray-500 flex items-center gap-1"><Punto color="bg-gray-400" /> Falta elegir profesor</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-xs text-gray-600 mt-3 flex items-center gap-2">
        <span className="flex-none w-4 h-4 rounded-full bg-gray-500 text-white text-[10px] flex items-center justify-center" aria-hidden="true">i</span>
        Elegir otra salida no cambia las asignaciones guardadas.
      </p>
      {pendientes > 0 && (
        <p className="text-xs text-amber-800 mt-1" data-testid="aviso-pendientes">
          {pendientes === 1 ? 'Hay un profesor elegido sin guardar.' : `Hay ${pendientes} profesores elegidos sin guardar.`}
          {' '}«Guardar datos del curso» no guarda profesores.
        </p>
      )}
      {explorar && (
        <div className="flex flex-col items-end mt-3 gap-1">
          <Button loading={guardando} disabled={!!motivoNoGuardar}
            onClick={() => guardar(listos.map(f => f.componente_codigo))}>
            Guardar asignación
          </Button>
          {motivoNoGuardar && <p className="text-xs text-gray-500">{motivoNoGuardar}</p>}
        </div>
      )}
    </div>
  );
};
