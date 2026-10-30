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

export const SalidaOptativaSection = ({ cursoId, curso, asignaturas }: {
  cursoId: number;
  // Solo para rotular. La identidad sigue siendo `cursoId`: en multi-tanda el
  // mismo grado existe en Matutina y Vespertina, y la pantalla tiene que decir
  // cuál de los dos se está configurando.
  curso?: CursoEtiquetable;
  asignaturas: Asignatura[];
}) => {
  const [estado, setEstado] = useState<SalidaEstado | null>(null);
  const [salida, setSalida] = useState<string>('');
  const [mapeos, setMapeos] = useState<Record<string, number | null>>({});
  // R3.4: profesor responsable por componente. Es LO ÚNICO que Dirección
  // necesita elegir: el backend garantiza la identidad calificable del
  // componente y deja la asignación docente activa.
  const [profes, setProfes] = useState<Record<string, number | null>>({});
  const [profesores, setProfesores] = useState<Profesor[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  // SALIDAS-MIXTAS: añadir un componente de cualquier salida del grado.
  const [nuevoCodigo, setNuevoCodigo] = useState<string>('');
  const [nuevoProfe, setNuevoProfe] = useState<number | null>(null);
  // 'nueva' = crear otra asignatura a propósito; número = candidata elegida.
  const [nuevaIdentidad, setNuevaIdentidad] = useState<number | 'nueva' | null>(null);
  // Elección por componente pendiente que ya tiene candidatas.
  const [identidades, setIdentidades] = useState<Record<string, number | 'nueva'>>({});

  const aplicar = (d: SalidaEstado) => {
    setEstado(d);
    setSalida(d.salida_optativa_codigo || '');
    const m: Record<string, number | null> = {};
    const p: Record<string, number | null> = {};
    d.componentes.forEach(c => {
      m[c.componente_codigo] = c.asignatura_id;
      p[c.componente_codigo] = c.profesor_id;
    });
    setMapeos(m);
    setProfes(p);
  };

  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.get(`/cursos/${cursoId}/salida-optativa`);
      aplicar(r.data);
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

  // Cambiar de salida cambia el juego de componentes: se piden al backend
  // guardando solo la salida, y él responde con los componentes que tocan.
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
    setSalida(codigo);
    setError(null);
    setOk(null);
    setGuardando(true);
    try {
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        salida_optativa_codigo: codigo || null,
      });
      aplicar(r.data);
    } catch (e: any) {
      // 409 = hay datos académicos. Se revierte el selector para que la
      // pantalla no muestre un estado que el servidor no aceptó.
      setError(e.response?.data?.error || 'No se pudo cambiar la Salida Optativa');
      setSalida(estado?.salida_optativa_codigo || '');
    } finally {
      setGuardando(false);
    }
  };

  const guardar = async () => {
    setError(null);
    setOk(null);
    setGuardando(true);
    try {
      // `profesores` es la vía normal: el backend crea o reutiliza la identidad
      // calificable del componente y deja la asignación docente activa.
      //
      // R3.4 §2: se manda el componente SIEMPRE que Dirección haya tocado su
      // selector, incluido el `null` de "Sin asignar". Antes se filtraban los
      // null y por eso retirar a un profesor era imposible. Un `null` sobre un
      // componente que ni siquiera tiene mapeo es inofensivo: el backend no
      // crea nada.
      // SALIDAS-MIXTAS: este guardado solo lleva los componentes de la salida
      // del curso. Los de otra salida se guardan uno a uno con su propio botón
      // (POST), que no toca a los demás.
      // Un pendiente con candidatas tampoco va aquí: se guarda con su propio
      // botón, que lleva la asignatura elegida.
      const propios = (estado?.componentes || []).filter(
        c => c.de_la_salida_del_curso && !(c.candidatas || []).length);
      const enviaProfes: Record<string, number | null> = {};
      propios.forEach(c => {
        const elegido = profes[c.componente_codigo] ?? null;
        if (elegido !== c.profesor_id) enviaProfes[c.componente_codigo] = elegido;
        else if (elegido) enviaProfes[c.componente_codigo] = elegido;
      });
      const enviaMapeos: Record<string, number | null> = {};
      propios.forEach(c => { enviaMapeos[c.componente_codigo] = mapeos[c.componente_codigo] ?? null; });
      const r = await api.put(`/cursos/${cursoId}/salida-optativa`, {
        salida_optativa_codigo: salida || null,
        componentes: enviaMapeos,
        ...(Object.keys(enviaProfes).length ? { profesores: enviaProfes } : {}),
      });
      aplicar(r.data);
      setOk('Configuración guardada');
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo guardar la configuración');
    } finally {
      setGuardando(false);
    }
  };

  // SALIDAS-MIXTAS: añadir un componente, o cambiar el profesor de uno ya
  // añadido. Solo toca ESE componente.
  const guardarComponente = async (codigo: string, profesorId: number | null,
                                   identidad: number | 'nueva' | null = null) => {
    setError(null);
    setOk(null);
    setGuardando(true);
    try {
      const r = await api.post(`/cursos/${cursoId}/salida-optativa/componentes`, {
        componente_codigo: codigo,
        profesor_id: profesorId,
        ...(typeof identidad === 'number' ? { asignatura_id: identidad } : {}),
        ...(identidad === 'nueva' ? { crear_identidad_nueva: true } : {}),
      });
      aplicar(r.data);
      setNuevoCodigo('');
      setNuevoProfe(null);
      setNuevaIdentidad(null);
      setIdentidades({});
      setOk('Componente guardado');
    } catch (e: any) {
      const d = e.response?.data;
      setError(d?.error || 'No se pudo guardar el componente');
      // El servidor encontró asignaturas de ese componente que el curso ya
      // usó: se recarga para mostrarlas y que Dirección elija.
      if (d?.motivo === 'identidad_por_elegir') cargar();
    } finally {
      setGuardando(false);
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
    setGuardando(true);
    try {
      const r = await api.delete(
        `/cursos/${cursoId}/salida-optativa/componentes/${c.componente_codigo}`);
      aplicar(r.data);
      setOk('Componente retirado');
    } catch (e: any) {
      setError(e.response?.data?.error || 'No se pudo quitar el componente');
    } finally {
      setGuardando(false);
    }
  };

  if (cargando) return <div className="text-sm text-gray-500 py-2">Cargando Salida Optativa…</div>;
  // 1ro-3ro de Secundaria y toda Primaria: la sección NO existe.
  if (!estado || !estado.aplica) return null;

  const faltan = estado.componentes.filter(
    c => !mapeos[c.componente_codigo] && !profes[c.componente_codigo]).length;
  const sinProfesor = estado.componentes.filter(c => !profes[c.componente_codigo]).length;

  return (
    <div className="border-t pt-4 mt-2">
      <h4 className="font-semibold text-gray-800 mb-1">Salida Optativa — Modalidad Académica</h4>
      {curso && (
        <p className="text-xs font-medium text-gray-700 mb-1">
          {labelCurso(curso)}
        </p>
      )}
      <p className="text-xs text-gray-500 mb-3">
        Solo para {estado.grado_numero}to de Secundaria. Elige el profesor responsable de
        cada componente oficial: se califica aparte de la materia troncal.
      </p>

      {error && <div className="mb-3"><Alert variant="error">{error}</Alert></div>}
      {ok && <div className="mb-3"><Alert variant="success">{ok}</Alert></div>}

      <Select
        label="Salida Optativa"
        value={salida}
        disabled={guardando}
        onChange={e => cambiarSalida(e.target.value)}
        options={estado.salidas_disponibles.map(s => ({
          value: s.codigo, label: `${s.nombre} (${s.codigo})`,
        }))}
        placeholder="Sin Salida Optativa"
      />

      {salida && estado.componentes.length > 0 && (
        <div className="mt-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-500 uppercase">Componentes del curso</p>
            <span className={`text-xs ${estado.excede_capacidad ? 'text-red-700' : 'text-gray-600'}`}>
              Espacios del registro: {estado.espacios_en_uso} de {estado.capacidad_registro}
            </span>
          </div>
          {estado.excede_capacidad && estado.mensaje_capacidad && (
            <Alert variant="error">{estado.mensaje_capacidad}</Alert>
          )}
          {estado.componentes.map(c => (
            <div key={c.componente_codigo} className="border rounded-md p-3 bg-gray-50">
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium text-gray-800 text-sm">
                  {c.orden_impresion}. {c.nombre_oficial}
                </p>
                {!c.de_la_salida_del_curso && (
                  <span className="text-[11px] px-2 py-0.5 rounded bg-blue-50 text-blue-700 whitespace-nowrap">
                    {c.salida_nombre}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 mb-2">
                {c.componente_codigo} · {c.horas_semana} h/semana · espacio {c.orden_impresion} en
                asistencia, acta y boletín
              </p>

              {/* R3.4: elegir el profesor es TODO lo que Dirección tiene que
                  hacer. EducaOne se encarga de darle al componente su propia
                  identidad calificable y de dejar la asignación activa. */}
              <Select
                label="Profesor responsable"
                value={profes[c.componente_codigo] || 0}
                disabled={guardando}
                onChange={e => setProfes({
                  ...profes,
                  [c.componente_codigo]: parseInt(e.target.value) || null,
                })}
                options={profesores.map(p => ({
                  value: p.id,
                  label: p.nombre_completo || `${p.nombre || ''} ${p.apellido || ''}`.trim(),
                }))}
                placeholder="Sin asignar"
              />

              {c.asignatura_id && (
                <p className="text-xs text-gray-500 mt-2">
                  Se califica como <strong>{c.asignatura_nombre}</strong>, aparte de la
                  materia troncal.
                  {!c.identidad_independiente && (
                    <span className="text-amber-700">
                      {' '}Hoy apunta a una materia del Registro; al guardar se le dará
                      identidad propia y las notas de esa materia no se tocan.
                    </span>
                  )}
                </p>
              )}

              {(c.candidatas || []).length > 0 && (
                <>
                  <ElegirIdentidad nombre={`identidad-${c.componente_codigo}`}
                    candidatas={c.candidatas}
                    valor={identidades[c.componente_codigo] ?? null}
                    onChange={v => setIdentidades({ ...identidades, [c.componente_codigo]: v })} />
                  <div className="flex mt-2">
                    <Button size="sm" variant="secondary" loading={guardando}
                      disabled={identidades[c.componente_codigo] === undefined}
                      onClick={() => guardarComponente(c.componente_codigo,
                                                       profes[c.componente_codigo] ?? null,
                                                       identidades[c.componente_codigo])}>
                      Vincular y guardar
                    </Button>
                  </div>
                </>
              )}

              {/* SALIDAS-MIXTAS: un componente de otra salida se guarda solo,
                  sin pasar por «Guardar configuración». */}
              {(!c.de_la_salida_del_curso || c.asignatura_id) && (
                <div className="flex gap-2 mt-2">
                  {!c.de_la_salida_del_curso && (
                    <Button size="sm" variant="secondary" loading={guardando}
                      disabled={!profes[c.componente_codigo]}
                      onClick={() => guardarComponente(c.componente_codigo,
                                                       profes[c.componente_codigo] ?? null)}>
                      Guardar profesor
                    </Button>
                  )}
                  {c.asignatura_id && (
                    <Button size="sm" variant="ghost" disabled={guardando}
                      onClick={() => quitarComponente(c)}>
                      Quitar del curso
                    </Button>
                  )}
                </div>
              )}

              {/* Vía manual de R3.2, como respaldo: Dirección puede elegir una
                  materia suya en vez de dejar que EducaOne cree la dedicada. */}
              {c.de_la_salida_del_curso && (
              <details className="mt-2">
                <summary className="text-xs text-gray-500 cursor-pointer">
                  Vincular a una asignatura existente (opcional)
                </summary>
                <div className="mt-2">
                  <Select
                    label=""
                    value={mapeos[c.componente_codigo] || 0}
                    disabled={guardando || c.tiene_historia}
                    onChange={e => setMapeos({
                      ...mapeos,
                      [c.componente_codigo]: parseInt(e.target.value) || null,
                    })}
                    options={asignaturas.map(a => ({ value: a.id, label: a.nombre }))}
                    placeholder="Sin vincular"
                  />
                </div>
              </details>
              )}

              {c.tiene_historia && (
                <p className="text-xs text-amber-700 mt-1">
                  Ya tiene datos académicos registrados: no se puede cambiar la
                  asignatura vinculada.
                </p>
              )}
            </div>
          ))}

          <div className="flex items-center justify-between pt-2">
            {faltan === 0 && sinProfesor === 0 ? (
              <span className="text-sm text-green-700">✅ Configurada</span>
            ) : faltan > 0 ? (
              <span className="text-sm text-amber-700">
                ⚠️ Falta vincular {faltan} componente{faltan === 1 ? '' : 's'}
              </span>
            ) : (
              <span className="text-sm text-amber-700">
                ⚠️ Falta el profesor de {sinProfesor} componente{sinProfesor === 1 ? '' : 's'}
              </span>
            )}
            <Button onClick={guardar} loading={guardando} size="sm">
              Guardar configuración
            </Button>
          </div>

          {/* SALIDAS-MIXTAS — el centro decide qué componentes imparte el
              curso, de cualquier salida del grado. Añadir uno no sustituye a
              ningún otro. */}
          {estado.componentes_disponibles.length > 0 && (() => {
            const vinculados = estado.componentes.filter(c => c.asignatura_id).length;
            const sinEspacio = vinculados >= estado.capacidad_registro;
            const elegido = estado.componentes_disponibles.find(
              d => d.componente_codigo === nuevoCodigo);
            const pendientes = estado.modo === 'salida'
              ? estado.componentes.filter(c => !c.asignatura_id) : [];
            const faltaIdentidad = !!elegido && elegido.candidatas.length > 0 && nuevaIdentidad === null;
            return (
              <div className="border-t pt-3 mt-2 space-y-2">
                <p className="text-xs font-semibold text-gray-500 uppercase">Añadir componente</p>
                {sinEspacio ? (
                  <p className="text-xs text-amber-700">
                    El registro y el boletín tienen {estado.capacidad_registro} espacios para la
                    Salida Optativa (asistencia, acta y boletín) y ya están en uso. Un tercer
                    componente no se puede guardar todavía: imprimirlo obligaría a omitir datos.
                    Para cambiar uno, quítalo primero.
                  </p>
                ) : (
                  <>
                    <Select
                      label="Componente"
                      value={nuevoCodigo}
                      disabled={guardando}
                      onChange={e => { setNuevoCodigo(e.target.value); setNuevaIdentidad(null); }}
                      options={estado.componentes_disponibles.map(d => ({
                        value: d.componente_codigo,
                        label: `${d.nombre_oficial} (${d.componente_codigo})`,
                        group: d.salida_nombre,
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
                      disabled={guardando}
                      onChange={e => setNuevoProfe(parseInt(e.target.value) || null)}
                      options={profesores.map(p => ({
                        value: p.id,
                        label: p.nombre_completo || `${p.nombre || ''} ${p.apellido || ''}`.trim(),
                      }))}
                      placeholder="Sin asignar"
                    />
                    {elegido && pendientes.length > 0 && elegido.salida_codigo !== estado.salida_optativa_codigo && (
                      <p className="text-xs text-gray-600">
                        Al añadirlo, el curso pasa a definirse por sus componentes vinculados:{' '}
                        {pendientes.map(p => p.nombre_oficial).join(', ')} dejará de figurar como
                        pendiente.
                      </p>
                    )}
                    <div className="flex justify-end">
                      <Button size="sm" loading={guardando}
                        disabled={!nuevoCodigo || faltaIdentidad}
                        onClick={() => guardarComponente(nuevoCodigo, nuevoProfe, nuevaIdentidad)}>
                        Añadir componente
                      </Button>
                    </div>
                  </>
                )}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
};
