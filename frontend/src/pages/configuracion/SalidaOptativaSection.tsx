import { useState, useEffect } from 'react';
import api from '../../services/api';
import { Button, Select, Alert } from '../../components/ui';
import { labelCurso, CursoEtiquetable } from '../../utils/labelCurso';

/**
 * R3.2 — Salida Optativa de un curso de 4to-6to de Secundaria.
 *
 * Vive DENTRO del modal de edición del curso (Configuración → Cursos), no en
 * un item nuevo del menú: la salida es un atributo del curso, como su tanda.
 *
 * Todo lo que se pinta sale del backend —las 4 salidas y los nombres oficiales
 * de los componentes llegan en la respuesta—, así que el frontend NO tiene
 * ninguna copia del catálogo MINERD que pueda quedar desincronizada.
 */

interface ComponenteEstado {
  componente_codigo: string;
  nombre_oficial: string;
  slot: number;
  horas_semana: number;
  asignatura_id: number | null;
  asignatura_nombre: string | null;
  tiene_historia: boolean;
  // R3.4
  identidad_independiente: boolean;
  profesor_id: number | null;
  profesor_nombre: string | null;
  // SALIDAS-MIXTAS
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

// Elección explícita de la asignatura de un componente cuando el curso ya
// tiene alguna sin vincular (p. ej. dos "Apreciación y Producción Literarias").
const ElegirIdentidad = ({ nombre, candidatas, valor, onChange }: {
  nombre: string;
  candidatas: Candidata[];
  valor: number | 'nueva' | null;
  onChange: (v: number | 'nueva') => void;
}) => (
  <div className="border rounded-md p-2 bg-amber-50 text-xs space-y-1 mt-2">
    <p className="text-amber-800">
      Este curso ya tiene {candidatas.length === 1 ? 'una asignatura' : `${candidatas.length} asignaturas`} de
      este componente sin vincular. Elige cuál es la del componente; no se crea otra ni se elige
      ninguna sola.
    </p>
    {candidatas.map(cand => (
      <label key={cand.asignatura_id} className="flex gap-2 items-start">
        <input type="radio" name={nombre}
          checked={valor === cand.asignatura_id}
          disabled={!cand.activo}
          onChange={() => onChange(cand.asignatura_id)} />
        <span>
          #{cand.asignatura_id} {cand.nombre}
          {!cand.activo && ' (inactiva: reactívala en Asignaturas si es esta)'}
          {' · '}{cand.historia_resumen || 'sin datos académicos'}
          {cand.asignaciones.length > 0 && ' · ' + cand.asignaciones.map(a =>
            `${a.profesor_nombre || a.profesor_id}${a.activo ? '' : ' (asignación inactiva)'}`).join(', ')}
        </span>
      </label>
    ))}
    <label className="flex gap-2 items-start">
      <input type="radio" name={nombre}
        checked={valor === 'nueva'}
        onChange={() => onChange('nueva')} />
      <span>Ninguna: crear una asignatura nueva</span>
    </label>
  </div>
);

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

// Estado de una tarjeta. Sale SIEMPRE de lo que confirmó el servidor, salvo
// «pendiente», que es una selección local todavía no enviada.
type EstadoTarjeta = 'guardada' | 'sin_profesor' | 'pendiente';

const ETIQUETA_ESTADO: Record<EstadoTarjeta, { texto: string; clase: string }> = {
  guardada: { texto: 'Asignación guardada', clase: 'bg-green-50 text-green-700 border-green-200' },
  sin_profesor: { texto: 'Sin profesor', clase: 'bg-amber-50 text-amber-800 border-amber-200' },
  pendiente: { texto: 'Profesor pendiente de guardar', clase: 'bg-blue-50 text-blue-700 border-blue-200' },
};

interface Edicion {
  profesorId: number | null;
  identidad: number | 'nueva' | null;
}

export const SalidaOptativaSection = ({ cursoId, curso, asignaturas, onCambiosPendientes }: {
  cursoId: number;
  // Solo para rotular. La identidad sigue siendo `cursoId`: en multi-tanda el
  // mismo grado existe en Matutina y Vespertina, y la pantalla tiene que decir
  // cuál de los dos se está configurando.
  curso?: CursoEtiquetable;
  asignaturas: Asignatura[];
  // Número de componentes con un profesor elegido y SIN guardar. El modal del
  // curso lo usa para avisar antes de cerrarse: su botón «Guardar» no guarda
  // los profesores de la Salida Optativa.
  onCambiosPendientes?: (n: number) => void;
}) => {
  // `estado` es SIEMPRE la última respuesta del servidor. Nada de lo que se
  // pinta como guardado sale de otra fuente.
  const [estado, setEstado] = useState<SalidaEstado | null>(null);
  const [profesores, setProfesores] = useState<Profesor[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState<string | null>(null);   // qué se está guardando
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // Tarjetas abiertas para editar, con la selección LOCAL todavía no guardada.
  const [edicion, setEdicion] = useState<Record<string, Edicion>>({});
  // Vínculo manual a una asignatura existente (R3.2), por componente.
  const [vinculo, setVinculo] = useState<Record<string, number | null>>({});
  // Formulario «Añadir componente», separado de las tarjetas.
  const [nuevoCodigo, setNuevoCodigo] = useState<string>('');
  const [nuevoProfe, setNuevoProfe] = useState<number | null>(null);
  const [nuevaIdentidad, setNuevaIdentidad] = useState<number | 'nueva' | null>(null);

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
      const r = await api.get('/usuarios');
      setProfesores((r.data || []).filter((u: Profesor) => u.role === 'profesor'));
    } catch {
      setProfesores([]);
    }
  };

  useEffect(() => { cargar(); cargarProfesores(); /* eslint-disable-next-line */ }, [cursoId]);

  const nombreProfe = (id: number | null) => {
    const p = profesores.find(x => x.id === id);
    return p ? (p.nombre_completo || `${p.nombre || ''} ${p.apellido || ''}`.trim()) : '';
  };

  const estadoDe = (c: ComponenteEstado): EstadoTarjeta => {
    const ed = edicion[c.componente_codigo];
    if (ed && ed.profesorId && ed.profesorId !== c.profesor_id) return 'pendiente';
    return c.asignatura_id && c.profesor_id ? 'guardada' : 'sin_profesor';
  };

  const pendientes = (estado?.componentes || []).filter(c => estadoDe(c) === 'pendiente').length
    + (nuevoCodigo && nuevoProfe ? 1 : 0);
  useEffect(() => { onCambiosPendientes?.(pendientes); /* eslint-disable-next-line */ }, [pendientes]);

  const tras = (d: SalidaEstado, msg: string) => {
    setEstado(d);
    setOk(msg);
  };

  // Cambiar de salida cambia el juego de componentes: se guarda al instante y
  // el servidor responde con los componentes que tocan.
  const cambiarSalida = async (codigo: string) => {
    // Cambiar la salida retira TODOS los componentes vinculados (si ninguno
    // tiene datos académicos; si alguno los tiene, el servidor lo impide). Se
    // avisa antes, nombrándolos, para que no se haga por error.
    const vinculados = (estado?.componentes || []).filter(c => c.asignatura_id);
    if (vinculados.length && codigo !== (estado?.salida_optativa_codigo || '')) {
      const lista = vinculados.map(c => `• ${c.nombre_oficial} (${c.componente_codigo})`).join('\n');
      if (!window.confirm(
        `Cambiar la Salida Optativa retira estos componentes del curso y sus ` +
        `profesores:\n${lista}\n\nPara añadir un componente de otra salida sin ` +
        `quitar los actuales, usa «Añadir componente». ¿Cambiar la salida?`)) {
        return;
      }
    }
    setError(null);
    setOk(null);
    setGuardando('salida');
    try {
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        salida_optativa_codigo: codigo || null,
      });
      setEdicion({});
      tras(r.data, codigo ? 'Salida guardada. Falta asignar el profesor de cada componente.'
                          : 'Salida retirada.');
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo cambiar la Salida Optativa');
    } finally {
      setGuardando(null);
    }
  };

  // Guarda UN componente (profesor y, si hace falta, la asignatura elegida).
  // Solo toca ese componente; la respuesta del servidor es lo que se pinta.
  const guardarComponente = async (codigo: string, profesorId: number | null,
                                   identidad: number | 'nueva' | null) => {
    setError(null);
    setOk(null);
    setGuardando(codigo);
    try {
      const r = await api.post(`/cursos/${cursoId}/salida-optativa/componentes`, {
        componente_codigo: codigo,
        profesor_id: profesorId,
        ...(typeof identidad === 'number' ? { asignatura_id: identidad } : {}),
        ...(identidad === 'nueva' ? { crear_identidad_nueva: true } : {}),
      });
      const guardado = (r.data as SalidaEstado).componentes.find(c => c.componente_codigo === codigo);
      tras(r.data, guardado?.profesor_nombre
        ? `Guardado: ${guardado.profesor_nombre} imparte ${guardado.nombre_oficial}.`
        : 'Componente guardado.');
      return true;
    } catch (e: any) {
      const d = e.response?.data;
      setError(d?.error || 'No se pudo guardar el componente');
      // Asignaturas del curso que hay que elegir: se recargan para mostrarlas.
      if (d?.motivo === 'identidad_por_elegir') cargar();
      return false;
    } finally {
      setGuardando(null);
    }
  };

  const guardarTarjeta = async (c: ComponenteEstado) => {
    const ed = edicion[c.componente_codigo];
    if (!ed?.profesorId) return;
    if (await guardarComponente(c.componente_codigo, ed.profesorId, ed.identidad)) {
      const resto = { ...edicion };
      delete resto[c.componente_codigo];
      setEdicion(resto);
    }
  };

  const guardarNuevo = async () => {
    if (await guardarComponente(nuevoCodigo, nuevoProfe, nuevaIdentidad)) {
      setNuevoCodigo('');
      setNuevoProfe(null);
      setNuevaIdentidad(null);
    }
  };

  // Vínculo manual de R3.2: SOLO ese componente, por el PUT de siempre.
  const vincularManual = async (c: ComponenteEstado) => {
    setError(null);
    setOk(null);
    setGuardando(c.componente_codigo);
    try {
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        componentes: { [c.componente_codigo]: vinculo[c.componente_codigo] ?? null },
      });
      tras(r.data, 'Vínculo guardado.');
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo guardar el vínculo');
    } finally {
      setGuardando(null);
    }
  };

  const quitarComponente = async (c: ComponenteEstado) => {
    if (!window.confirm(
      `¿Quitar ${c.nombre_oficial} (${c.componente_codigo}) de este curso? ` +
      `La asignatura y sus datos no se borran; su profesor deja de tenerla asignada.`)) {
      return;
    }
    setError(null);
    setOk(null);
    setGuardando(c.componente_codigo);
    try {
      const r = await api.delete(
        `/cursos/${cursoId}/salida-optativa/componentes/${c.componente_codigo}`);
      tras(r.data, 'Componente retirado.');
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo quitar el componente');
    } finally {
      setGuardando(null);
    }
  };

  if (cargando) return <div className="text-sm text-gray-500 py-2">Cargando Salida Optativa…</div>;
  // 1ro-3ro de Secundaria y toda Primaria: la sección NO existe.
  if (!estado || !estado.aplica) return null;

  const comps = estado.componentes;
  const guardadas = comps.filter(c => c.asignatura_id && c.profesor_id).length;
  // Resumen del curso según el SERVIDOR (nunca según selecciones locales).
  const resumen = !estado.salida_optativa_codigo
    ? { texto: 'Sin Salida Optativa', clase: 'text-gray-600' }
    : guardadas === 0
      ? { texto: 'Salida seleccionada · ningún profesor asignado todavía', clase: 'text-amber-800' }
      : guardadas < comps.length
        ? { texto: `Asignaciones guardadas: ${guardadas} de ${comps.length}`, clase: 'text-amber-800' }
        : { texto: `Configurada · ${guardadas} de ${comps.length} asignaciones guardadas`, clase: 'text-green-700' };
  const vinculadas = comps.filter(c => c.asignatura_id).length;
  const sinEspacio = vinculadas >= estado.capacidad_registro;
  const elegido = estado.componentes_disponibles.find(d => d.componente_codigo === nuevoCodigo);
  const faltaIdentidad = !!elegido && elegido.candidatas.length > 0 && nuevaIdentidad === null;
  const pendientesSalida = estado.modo === 'salida' ? comps.filter(c => !c.asignatura_id) : [];
  const opcionesProfe = profesores.map(p => ({
    value: p.id,
    label: p.nombre_completo || `${p.nombre || ''} ${p.apellido || ''}`.trim(),
  }));

  return (
    <div className="border-t pt-4 mt-2">
      <h4 className="font-semibold text-gray-800 mb-1">Salida Optativa — Modalidad Académica</h4>
      {curso && <p className="text-xs font-medium text-gray-700 mb-1">{labelCurso(curso)}</p>}
      <p className="text-xs text-gray-500 mb-3">
        Cada componente se guarda con su propio botón. El «Guardar» del curso no guarda los profesores.
      </p>

      {error && <div className="mb-3"><Alert variant="error">{error}</Alert></div>}
      {ok && <div className="mb-3"><Alert variant="success">{ok}</Alert></div>}

      <Select
        label="Salida Optativa del curso"
        value={estado.salida_optativa_codigo || ''}
        disabled={!!guardando}
        onChange={e => cambiarSalida(e.target.value)}
        options={estado.salidas_disponibles.map(s => ({ value: s.codigo, label: `${s.nombre} (${s.codigo})` }))}
        placeholder="Sin Salida Optativa"
      />

      {estado.salida_optativa_codigo && (
        <div className="mt-2 flex items-center justify-between text-xs">
          <span className={`font-medium ${resumen.clase}`} data-testid="resumen-salida">{resumen.texto}</span>
          <span className={estado.excede_capacidad ? 'text-red-700' : 'text-gray-600'}>
            Espacios del registro: {estado.espacios_en_uso} de {estado.capacidad_registro}
          </span>
        </div>
      )}
      {estado.excede_capacidad && estado.mensaje_capacidad && (
        <div className="mt-2"><Alert variant="error">{estado.mensaje_capacidad}</Alert></div>
      )}
      {pendientes > 0 && (
        <div className="mt-2">
          <Alert variant="warning">
            Hay {pendientes} cambio{pendientes === 1 ? '' : 's'} sin guardar. Usa «Guardar» en cada
            componente; al cerrar el curso se perderían.
          </Alert>
        </div>
      )}

      {estado.salida_optativa_codigo && comps.length > 0 && (
        <div className="mt-4 space-y-3">
          <p className="text-xs font-semibold text-gray-500 uppercase">Componentes del curso</p>
          {comps.map(c => {
            const est = estadoDe(c);
            const ed = edicion[c.componente_codigo];
            const etq = ETIQUETA_ESTADO[est];
            return (
              <div key={c.componente_codigo} data-componente={c.componente_codigo}
                   className="border rounded-md p-3 bg-white">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-gray-800 text-sm">{c.orden_impresion}. {c.nombre_oficial}</p>
                    <p className="text-xs text-gray-500">
                      {c.componente_codigo} · {c.salida_nombre} · espacio {c.orden_impresion} en asistencia, acta y boletín
                    </p>
                  </div>
                  <span className={`text-[11px] px-2 py-0.5 rounded border whitespace-nowrap ${etq.clase}`}
                        data-testid="estado-componente">
                    {etq.texto}
                  </span>
                </div>

                {/* Lo GUARDADO, siempre visible: viene del servidor. */}
                <p className="text-sm mt-2" data-testid="profesor-guardado">
                  <span className="text-gray-500">Profesor guardado: </span>
                  {c.profesor_nombre
                    ? <strong>{c.profesor_nombre}</strong>
                    : <span className="text-amber-800">ninguno</span>}
                </p>
                {c.asignatura_id && !c.identidad_independiente && (
                  <p className="text-xs text-amber-700 mt-1">
                    Hoy apunta a una materia del Registro; al guardar el profesor se le dará identidad
                    propia y las notas de esa materia no se tocan.
                  </p>
                )}

                {!ed ? (
                  <div className="flex gap-2 mt-2">
                    <Button size="sm" variant="secondary" disabled={!!guardando}
                      onClick={() => setEdicion({ ...edicion, [c.componente_codigo]: {
                        profesorId: c.profesor_id, identidad: null } })}>
                      {c.profesor_id ? 'Cambiar profesor' : 'Asignar profesor'}
                    </Button>
                    {c.asignatura_id && (
                      <Button size="sm" variant="ghost" disabled={!!guardando}
                        onClick={() => quitarComponente(c)}>
                        Quitar del curso
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="mt-2 border-t pt-2 space-y-2">
                    <Select
                      label="Profesor responsable"
                      value={ed.profesorId || 0}
                      disabled={!!guardando}
                      onChange={e => setEdicion({ ...edicion, [c.componente_codigo]: {
                        ...ed, profesorId: parseInt(e.target.value) || null } })}
                      options={opcionesProfe}
                      placeholder="Elegir profesor"
                    />
                    {(c.candidatas || []).length > 0 && (
                      <ElegirIdentidad nombre={`identidad-${c.componente_codigo}`} candidatas={c.candidatas}
                        valor={ed.identidad}
                        onChange={v => setEdicion({ ...edicion, [c.componente_codigo]: { ...ed, identidad: v } })} />
                    )}
                    {est === 'pendiente' && (
                      <p className="text-xs text-blue-700">
                        {nombreProfe(ed.profesorId)} todavía no está guardado.
                      </p>
                    )}
                    <div className="flex gap-2">
                      <Button size="sm" loading={guardando === c.componente_codigo}
                        disabled={!ed.profesorId || ed.profesorId === c.profesor_id
                                  || ((c.candidatas || []).length > 0 && ed.identidad === null)}
                        onClick={() => guardarTarjeta(c)}>
                        Guardar
                      </Button>
                      <Button size="sm" variant="secondary" disabled={guardando === c.componente_codigo}
                        onClick={() => { const r = { ...edicion }; delete r[c.componente_codigo]; setEdicion(r); }}>
                        Cancelar
                      </Button>
                    </div>
                    {/* Vínculo manual de R3.2, como respaldo. */}
                    {c.de_la_salida_del_curso && !c.tiene_historia && (
                      <details>
                        <summary className="text-xs text-gray-500 cursor-pointer">
                          Vincular a una asignatura existente (opcional)
                        </summary>
                        <div className="mt-2 flex gap-2 items-end">
                          <div className="flex-1">
                            <Select label="" value={vinculo[c.componente_codigo] ?? c.asignatura_id ?? 0}
                              disabled={!!guardando}
                              onChange={e => setVinculo({ ...vinculo, [c.componente_codigo]: parseInt(e.target.value) || null })}
                              options={asignaturas.map(a => ({ value: a.id, label: a.nombre }))}
                              placeholder="Sin vincular" />
                          </div>
                          <Button size="sm" variant="secondary" disabled={!!guardando}
                            onClick={() => vincularManual(c)}>Vincular</Button>
                        </div>
                      </details>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* AÑADIR COMPONENTE: formulario aparte, nunca mezclado con los guardados. */}
      {estado.salida_optativa_codigo && estado.componentes_disponibles.length > 0 && (
        <div className="mt-4 border-2 border-dashed rounded-md p-3 bg-gray-50 space-y-2" data-testid="form-anadir">
          <p className="text-xs font-semibold text-gray-600 uppercase">Añadir otro componente</p>
          {sinEspacio ? (
            <p className="text-xs text-amber-700">
              El registro y el boletín tienen {estado.capacidad_registro} espacios para la Salida Optativa y ya
              están en uso. Un tercer componente no se puede guardar todavía: imprimirlo obligaría a omitir
              datos. Para cambiar uno, quítalo primero.
            </p>
          ) : (
            <>
              <Select
                label="Componente"
                value={nuevoCodigo}
                disabled={!!guardando}
                onChange={e => { setNuevoCodigo(e.target.value); setNuevaIdentidad(null); }}
                options={estado.componentes_disponibles.map(d => ({
                  value: d.componente_codigo, label: `${d.nombre_oficial} (${d.componente_codigo})`, group: d.salida_nombre,
                }))}
                placeholder="Elegir componente"
              />
              {elegido && elegido.candidatas.length > 0 && (
                <ElegirIdentidad nombre="identidad-nueva" candidatas={elegido.candidatas}
                  valor={nuevaIdentidad} onChange={setNuevaIdentidad} />
              )}
              <Select
                label="Profesor responsable"
                value={nuevoProfe || 0}
                disabled={!!guardando}
                onChange={e => setNuevoProfe(parseInt(e.target.value) || null)}
                options={opcionesProfe}
                placeholder="Elegir profesor"
              />
              {elegido && pendientesSalida.length > 0 && elegido.salida_codigo !== estado.salida_optativa_codigo && (
                <p className="text-xs text-gray-600">
                  Al añadirlo, el curso pasa a definirse por sus componentes vinculados:{' '}
                  {pendientesSalida.map(p => p.nombre_oficial).join(', ')} dejará de figurar como pendiente.
                </p>
              )}
              <div className="flex justify-end">
                <Button size="sm" loading={guardando === nuevoCodigo}
                  disabled={!nuevoCodigo || !nuevoProfe || faltaIdentidad}
                  onClick={guardarNuevo}>
                  Guardar componente
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
