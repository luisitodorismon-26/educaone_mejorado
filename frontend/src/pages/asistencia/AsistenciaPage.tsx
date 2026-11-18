import { useState, useEffect, useRef } from 'react';
import { useRefrescoEnVivo } from '../../hooks/useRefrescoEnVivo';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { NivelTabs } from '../../components/NivelTabs';
import { useNivelesActivos, Nivel } from '../../hooks/useNivelesActivos';
import { labelCurso } from '../../utils/labelCurso';
import { SesionNoImpartidaPanel, SesionNI } from './SesionNoImpartida';
import { textoSoloLectura } from './permisoAsistencia';
import { VistaRapidaAsistencia } from './VistaRapidaAsistencia';

interface Estudiante {
  id: number;
  nombre_completo: string;
  no_lista: number;
  // Flags de retiro (vienen del backend en GET /asistencia/curso/{id})
  retirado?: boolean;
  fecha_retiro?: string | null;
  motivo_retiro?: string | null;
  // TRAS-1 · ¿pertenece al curso ESE día? Si no: «No aplica» (solo lectura).
  aplica?: boolean;
  avisos?: string[];
  marca_fuera_de_permanencia?: boolean;
  // RET-R · marca anulada por retiro ese día (no cuenta; solo lectura).
  asistencia_anulada?: { estado_original: string; motivo: string | null; anulada_en: string | null } | null;
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

/** Mensaje legible de un error de la API (el servidor manda `message`). */
const mensajeDelServidor = (err: any, porDefecto: string) =>
  err?.response?.data?.message || err?.response?.data?.error || porDefecto;

/** ¿El error es de red (sin respuesta del servidor) y no un rechazo? */
const sinRespuesta = (err: any) => !!err && !err.response;

type EstadoLista = 'vacio' | 'cargando' | 'ok' | 'error' | 'sin_conexion';
/** Una operación enviada cuya respuesta no llegó: puede haberse aplicado o no
 *  (incluso más tarde). Una entrada por OPERACIÓN, ligada a la selección
 *  COMPLETA (usuario, colegio, curso, materia y fecha) y al estudiante: un
 *  envío nuevo no borra la incertidumbre de uno anterior. */
interface SinConfirmar {
  clave: string;                  // selección en la que se pulsó
  estudianteId: number;
  nombre: string;
  pedido: string | null;          // estado pedido; null = desmarcar
  seq: number;                    // identifica esta operación entre las de la misma fila
  /** Último estado de asistencia LEÍDO del servidor para esa fila (no es una
   *  confirmación). undefined = aún no leído; null = sin marca. */
  observado?: string | null;
  /** La fila del estudiante no vino en la última lectura (no es un estado de asistencia). */
  filaNoRecibida?: boolean;
}
const MSG_SIN_RESPUESTA = 'No se recibió respuesta del servidor: la operación puede haberse aplicado o no. Queda «sin confirmar» y se comprobará el estado al recuperar la conexión; también puede pulsar «Comprobar».';
const idOperacion = (clave: string, estudianteId: number, seq: number) => `${clave}#${estudianteId}#${seq}`;
const textoEstado = (e: string | null | undefined) => (e === undefined ? 'sin leer' : e === null ? 'sin marca' : e);
/** Lo observado de un pendiente, distinguiendo «fila no recibida» del estado «ausente».
 *  Una lectura muestra el estado, no qué operación lo produjo: nunca confirma un envío. */
const textoObservado = (p: SinConfirmar) =>
  (p.filaNoRecibida ? 'Fila no recibida en la última lectura'
    : `El servidor muestra actualmente ${textoEstado(p.observado)}`) + '; no se pudo confirmar este envío';
const AYUDA_QUITAR_AVISO = 'No cancela el envío ni modifica la asistencia';

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
  // S1: la sesion declarada NO impartida de esta clase y fecha, si existe.
  const [sesionNI, setSesionNI] = useState<SesionNI | null>(null);
  // ENT-B · rango de vacaciones que contiene la fecha elegida (lo dice el servidor).
  const [vacaciones, setVacaciones] =
    useState<{ nombre: string; fecha_inicio: string; fecha_fin: string } | null>(null);
  const niveles = useNivelesActivos();
  const [nivelFiltro, setNivelFiltro] = useState<Nivel | 'todos'>('todos');
  // Lo que el servidor responde sobre si este usuario puede editar ESTE curso.
  const [permisoAsistencia, setPermisoAsistencia] =
    useState<{ puedeEditar: boolean | null; motivo: string | null }>(
      { puedeEditar: null, motivo: null });
  // Mantener siempre 'todos' por defecto al cargar — solo cambia si el usuario elige tab

  // ── ENT1 · Lista vinculada a su selección ─────────────────────────────
  // Cada lista pertenece a UNA clave (usuario, colegio, curso, materia y
  // fecha). Solo se marca sobre la lista cuya clave es la de la selección
  // actual y cuyo estado es «ok». Una respuesta que llega para otra clave, o
  // que ya no es la última pedida, se descarta.
  const [listaClave, setListaClave] = useState('');
  const [estadoLista, setEstadoLista] = useState<EstadoLista>('vacio');
  const [revalidando, setRevalidando] = useState(false);
  const [enLinea, setEnLinea] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [sinConfirmar, setSinConfirmar] = useState<Record<string, SinConfirmar>>({});
  const secuenciaRef = useRef(0);             // número de la última petición de lista
  const enVueloRef = useRef<string | null>(null);
  const claveActualRef = useRef('');
  const listaClaveRef = useRef('');
  const guardandoRef = useRef(0);             // guardados en curso
  const revalidarPendienteRef = useRef(false);
  const sinConfirmarRef = useRef<Record<string, SinConfirmar>>({});
  const secOperacionRef = useRef(0);
  const secAsignaturasRef = useRef(0);

  // Solo profesores pueden marcar asistencia
  const esProfesor = user?.role === 'profesor';
  // ASIS-DASH-1: Dirección y Coordinación ven el resumen del día al elegir curso.
  const veVistaRapida = user?.role === 'direccion' || user?.role === 'coordinador';
  // P3.1 — en Primaria la asistencia diaria la registra el TITULAR del curso.
  // Quién lo es lo decide el servidor y llega en la respuesta: el frontend no
  // lo deduce, y menos aún mirando el horario. `null` = Secundaria, donde esta
  // regla no aplica y el permiso de siempre no cambia.
  const puedeEditar = esProfesor && permisoAsistencia.puedeEditar !== false;

  // Detectar si el curso actual es de primaria
  const cursoActual = cursos.find(c => c.id === cursoId);
  const esPrimaria = cursoActual?.nivel === 'primaria';
  const seleccionCompleta = cursoId > 0 && (esPrimaria || asignaturaId > 0);
  const claveSeleccion = seleccionCompleta
    ? [user?.id ?? '', (user as any)?.colegio_id ?? '', cursoId, esPrimaria ? 'P' : asignaturaId, fecha].join('|')
    : '';
  claveActualRef.current = claveSeleccion;
  const listaValida = seleccionCompleta && estadoLista === 'ok' && listaClave === claveSeleccion;
  // S1: mientras la clase este declarada NO impartida, no se pasa lista. El
  // backend ya lo rechaza; esto evita que el profesor lo descubra a base de
  // errores. `puedeEditar` NO se toca: el panel de S1 sigue siendo suyo.
  // ENT1 · tampoco se marca sobre una lista que no es la de la selección
  // actual, mientras se revalida o sin conexión.
  // ENT-B · dentro de un rango de vacaciones tampoco (el servidor responde 409).
  const puedeMarcar = puedeEditar && !sesionNI && !vacaciones && listaValida && !revalidando && enLinea;

  // Cargar cursos según rol
  useEffect(() => {
    let vigente = true;
    const cargarCursos = async () => {
      try {
        const cursosRes = await api.get('/cursos');
        if (esProfesor) {
          const res = await api.get('/dashboard/profesor');
          const cursosAsignadosIds = new Set(res.data.cursos_asignados?.map((c: any) => c.curso_id) || []);
          if (vigente) setCursos((cursosRes.data || []).filter((c: any) => cursosAsignadosIds.has(c.id)));
        } else if (vigente) {
          setCursos(cursosRes.data || []);
        }
      } catch (err) {
        console.error('Error cargando cursos:', err);
        if (vigente) setError('Error al cargar cursos');
      } finally {
        if (vigente) setLoading(false);
      }
    };
    cargarCursos();
    return () => { vigente = false; };
  }, [esProfesor, user?.id]);

  // Cargar asignaturas cuando cambia el curso (solo si NO es primaria)
  useEffect(() => {
    if (cursoId > 0 && !esPrimaria) {
      cargarAsignaturas();
    } else {
      secAsignaturasRef.current += 1;       // descarta una respuesta en vuelo
      setAsignaturas([]);
      setAsignaturaId(0);
    }
  }, [cursoId, esPrimaria]);

  // Cargar asistencia cuando cambia la selección (curso, materia, fecha o usuario)
  useEffect(() => {
    if (claveSeleccion) {
      cargarAsistencia();
    } else {
      secuenciaRef.current += 1;            // ninguna respuesta anterior vale ya
      enVueloRef.current = null;
      setEstadoLista('vacio');
    }
  }, [claveSeleccion]);

  // ENT1 · Revalidar al volver a la pantalla (visibilidad, foco, aviso del
  // service worker) y al recuperar la conexión. Sin intervalos: solo cuando
  // pudo haber cambiado algo sin que esta pantalla lo viera.
  useRefrescoEnVivo(() => { if (claveActualRef.current) cargarAsistencia(); });
  useEffect(() => {
    const alConectar = () => { setEnLinea(true); if (claveActualRef.current) cargarAsistencia(); };
    const alDesconectar = () => setEnLinea(false);
    window.addEventListener('online', alConectar);
    window.addEventListener('offline', alDesconectar);
    return () => {
      window.removeEventListener('online', alConectar);
      window.removeEventListener('offline', alDesconectar);
    };
  }, []);

  const cargarAsignaturas = async () => {
    const sec = ++secAsignaturasRef.current;
    const paraCurso = cursoId;
    setLoadingAsignaturas(true);
    try {
      const res = await api.get(`/mis-asignaturas/${paraCurso}`);
      if (sec !== secAsignaturasRef.current) return;      // respuesta de otro curso
      setAsignaturas(res.data || []);
      if (res.data && res.data.length === 1) {
        setAsignaturaId(res.data[0].id);
      } else {
        setAsignaturaId(0);
      }
    } catch (err) {
      if (sec !== secAsignaturasRef.current) return;
      console.error('Error cargando asignaturas:', err);
      setAsignaturas([]);
    } finally {
      if (sec === secAsignaturasRef.current) setLoadingAsignaturas(false);
    }
  };

  /** Tras leer la lista de una selección, anota lo OBSERVADO para cada operación
   *  sin confirmar de ESA selección. Una lectura muestra el estado, no qué
   *  operación lo produjo (pudo ser este envío, otro, u otro dispositivo): no
   *  se elimina ningún pendiente porque coincida el valor ni se atribuye el
   *  estado a una operación. El pendiente sigue hasta una confirmación
   *  identificable de ESA operación o hasta que la persona quite el aviso. */
  const resolverSinConfirmar = (clave: string, lista: AsistenciaItem[]) => {
    const pendientes = Object.entries(sinConfirmarRef.current).filter(([, p]) => p.clave === clave);
    if (pendientes.length === 0) return;
    for (const [id, p] of pendientes) {
      const fila = lista.find(a => a.estudiante.id === p.estudianteId);
      sinConfirmarRef.current[id] = fila
        ? { ...p, observado: fila.asistencia?.estado ?? null, filaNoRecibida: false }
        : { ...p, filaNoRecibida: true };
    }
    setSinConfirmar({ ...sinConfirmarRef.current });
  };

  /** Pendientes que siguen abiertas para una selección y estudiante. */
  const pendientesDe = (clave: string, estudianteId: number) =>
    Object.values(sinConfirmarRef.current).filter(p => p.clave === clave && p.estudianteId === estudianteId);

  /** «Quitar aviso»: la persona deja de ver la incertidumbre de una operación.
   *  No cancela el envío ni modifica la asistencia. */
  const quitarAviso = (p: SinConfirmar) => {
    delete sinConfirmarRef.current[idOperacion(p.clave, p.estudianteId, p.seq)];
    setSinConfirmar({ ...sinConfirmarRef.current });
    if (!Object.values(sinConfirmarRef.current).some(x => x.clave === p.clave)) {
      setError(e => (e === MSG_SIN_RESPUESTA ? '' : e));
    }
  };

  const cargarAsistencia = async () => {
    const clave = claveActualRef.current;
    if (!clave) return;
    // Durante un guardado no se reemplaza la lista: se revalida al terminar.
    if (guardandoRef.current > 0) { revalidarPendienteRef.current = true; return; }
    // Ya hay una petición en vuelo para esta misma selección: no se duplica.
    if (enVueloRef.current === clave) return;
    const sec = ++secuenciaRef.current;
    enVueloRef.current = clave;
    const mismaLista = listaClaveRef.current === clave;
    if (mismaLista) setRevalidando(true); else { setEstadoLista('cargando'); setLoading(true); }
    const [, , cId, materia, f] = clave.split('|');
    const primaria = materia === 'P';
    const vigente = () => sec === secuenciaRef.current && claveActualRef.current === clave;
    try {
      // Primaria: sin asignatura (asistencia diaria general)
      // Secundaria: con asignatura específica
      const url = primaria
        ? `/asistencia/curso/${cId}?fecha=${f}`
        : `/asistencia/curso/${cId}?fecha=${f}&asignatura_id=${materia}`;
      const res = await api.get(url);
      if (!vigente()) return;               // respuesta atrasada: se descarta
      // S1: solo Secundaria. Se consulta la misma clase y fecha; si esta
      // declarada no impartida, los botones de la tabla se apagan.
      let sni: SesionNI | null = null;
      if (!primaria) {
        try {
          const r = await api.get(
            `/sesiones-no-impartidas?curso_id=${cId}&asignatura_id=${materia}&desde=${f}&hasta=${f}`);
          sni = (r.data && r.data[0]) || null;
        } catch {
          // Si la consulta falla no se bloquea la pantalla: el backend sigue
          // siendo quien decide, y responde 409 si la sesion esta declarada.
          sni = null;
        }
        if (!vigente()) return;
      }
      const lista: AsistenciaItem[] = res.data.asistencias || [];
      setAsistencias(lista);
      setPermisoAsistencia({
        puedeEditar: res.data.puede_editar ?? null,
        motivo: res.data.motivo_solo_lectura ?? null,
      });
      setSesionNI(sni);
      setVacaciones(res.data.vacaciones || null);
      setListaClave(clave);
      listaClaveRef.current = clave;
      setEstadoLista('ok');
      setEnLinea(true);
      resolverSinConfirmar(clave, lista);
    } catch (err: any) {
      if (!vigente()) return;
      console.error('Error cargando asistencia:', err);
      if (!mismaLista) {
        setAsistencias([]);
        setSesionNI(null);
        setVacaciones(null);
      }
      // Si la lista que se ve es de esta selección se conserva a la vista,
      // pero no se marca sobre ella hasta comprobarla de nuevo.
      setEstadoLista(sinRespuesta(err) ? 'sin_conexion' : 'error');
      if (!sinRespuesta(err)) setError(mensajeDelServidor(err, 'Error al cargar asistencia'));
    } finally {
      if (sec === secuenciaRef.current) {
        enVueloRef.current = null;
        setRevalidando(false);
        setLoading(false);
      }
    }
  };

  /** Inicio y fin de un guardado: la revalidación espera a que no quede ninguno. */
  const iniciarGuardado = () => { guardandoRef.current += 1; setSaving(true); };
  const terminarGuardado = () => {
    guardandoRef.current = Math.max(0, guardandoRef.current - 1);
    if (guardandoRef.current === 0) {
      setSaving(false);
      if (revalidarPendienteRef.current) {
        revalidarPendienteRef.current = false;
        cargarAsistencia();
      }
    }
  };

  /** Confirmación de un guardado. Si para esos estudiantes queda una operación
   *  ANTERIOR sin confirmar, se dice: no se muestra todo resuelto. */
  const avisarConfirmada = (texto: string, clave: string, ids: number[]) => {
    const conPendiente = ids.flatMap(id => pendientesDe(clave, id)).map(p => p.nombre);
    const unicos = [...new Set(conPendiente)];
    setSuccess(unicos.length
      ? `${texto}. Atención: queda una operación anterior sin confirmar para ${unicos.join(', ')}; podría aplicarse más tarde.`
      : texto);
    setTimeout(() => setSuccess(''), unicos.length ? 6000 : 1500);
  };

  /** Error de un guardado: rechazo del servidor (se muestra y se recarga) o
   *  respuesta perdida (queda «sin confirmar» y se comprueba con el servidor). */
  const trasErrorDeGuardado = (err: any, clave: string, seq: number, marcas: Array<[number, string | null]>) => {
    if (sinRespuesta(err)) {
      for (const [estId, pedido] of marcas) {
        const nombre = asistencias.find(a => a.estudiante.id === estId)?.estudiante.nombre_completo || `#${estId}`;
        sinConfirmarRef.current[idOperacion(clave, estId, seq)] = { clave, estudianteId: estId, nombre, pedido, seq };
      }
      setSinConfirmar({ ...sinConfirmarRef.current });
      setError(MSG_SIN_RESPUESTA);
    } else {
      setError(mensajeDelServidor(err, 'Error al guardar'));
    }
    revalidarPendienteRef.current = true;
  };

  const marcarAsistencia = async (estudianteId: number, estado: string) => {
    if (!puedeEditar) {
      setError('Solo profesores pueden registrar');
      return;
    }
    if (sesionNI) {
      setError('Esta clase está registrada como no impartida. Retire la justificación si sí hubo clase.');
      return;
    }
    // Secundaria requiere asignatura, primaria no
    if (!esPrimaria && !asignaturaId) {
      setError('Seleccione una materia');
      return;
    }
    if (!puedeMarcar) return;               // lista no válida para esta selección

    // El guardado queda ligado a la lista sobre la que se pulsó.
    const clave = claveSeleccion;
    const fechaGuardado = fecha;
    setError('');
    // Cada operación tiene su número; un envío nuevo NO borra la
    // incertidumbre de uno anterior (podría aplicarse más tarde).
    const seq = ++secOperacionRef.current;
    iniciarGuardado();
    const asistenciaActual = asistencias.find(a => a.estudiante.id === estudianteId);
    const desmarcar = asistenciaActual?.asistencia?.estado === estado;
    const aplicarEnLista = (nuevo: AsistenciaItem['asistencia']) => {
      // Solo si la pantalla sigue mostrando ESA lista.
      if (claveActualRef.current !== clave || listaClaveRef.current !== clave) return false;
      setAsistencias(prev => prev.map(a => a.estudiante.id === estudianteId ? { ...a, asistencia: nuevo } : a));
      return true;
    };

    try {
      // Si ya tiene ese estado, desmarcar
      if (desmarcar) {
        const delUrl = esPrimaria
          ? `/asistencia/${estudianteId}?fecha=${fechaGuardado}`
          : `/asistencia/${estudianteId}?fecha=${fechaGuardado}&asignatura_id=${asignaturaId}`;
        await api.delete(delUrl);
        const enPantalla = aplicarEnLista(null);
        avisarConfirmada(enPantalla ? '✓ Desmarcado' : `✓ Desmarcado (${fechaGuardado})`, clave, [estudianteId]);
        return;
      }

      const payload: any = {
        estudiante_id: estudianteId,
        curso_id: cursoId,
        fecha: fechaGuardado,
        estado: estado
      };
      if (!esPrimaria) payload.asignatura_id = asignaturaId;

      await api.post('/asistencia', payload);
      const enPantalla = aplicarEnLista({ estado, observacion: '', registrado_por: user?.nombre });
      avisarConfirmada(enPantalla ? '✓' : `✓ Guardado para el ${fechaGuardado}`, clave, [estudianteId]);
    } catch (err: any) {
      trasErrorDeGuardado(err, clave, seq, [[estudianteId, desmarcar ? null : estado]]);
    } finally {
      terminarGuardado();
    }
  };

  const marcarTodos = async (estado: string) => {
    if (!puedeMarcar) return;
    if (!esPrimaria && !asignaturaId) return;

    const clave = claveSeleccion;
    const fechaGuardado = fecha;
    iniciarGuardado();
    setError('');
    // TRAS-1 · solo quienes pertenecen al curso ese día.
    const ids = asistencias.filter(a => a.estudiante.aplica !== false).map(a => a.estudiante.id);
    const seq = ++secOperacionRef.current;

    try {
      const data = ids.map(id => ({ estudiante_id: id, curso_id: cursoId, estado }));
      const payload: any = { fecha: fechaGuardado, asistencias: data };
      if (!esPrimaria) payload.asignatura_id = asignaturaId;

      await api.post('/asistencia/masivo', payload);

      const enPantalla = claveActualRef.current === clave && listaClaveRef.current === clave;
      if (enPantalla) {
        setAsistencias(prev => prev.map(a => a.estudiante.aplica === false ? a : ({
          ...a,
          asistencia: { estado, observacion: '', registrado_por: user?.nombre }
        })));
      }
      avisarConfirmada(enPantalla ? `✓ Todos ${estado}` : `✓ Todos ${estado} (${fechaGuardado})`, clave, ids);
    } catch (err: any) {
      trasErrorDeGuardado(err, clave, seq, ids.map(id => [id, estado] as [number, string]));
    } finally {
      terminarGuardado();
    }
  };

  const estados = [
    { val: 'presente', emoji: '✅', color: 'bg-green-500', label: 'Presente' },
    { val: 'ausente', emoji: '❌', color: 'bg-red-500', label: 'Ausente' },
    { val: 'tardanza', emoji: '⏰', color: 'bg-yellow-500', label: 'Tardanza' },
    { val: 'excusa', emoji: '📋', color: 'bg-blue-500', label: 'Excusa' }
  ];

  // TRAS-1 · «No aplica» no cuenta para nada: ni ausencia ni día esperado.
  const aplicables = asistencias.filter(a => a.estudiante.aplica !== false);
  const conteo = {
    presente: aplicables.filter(a => a.asistencia?.estado === 'presente').length,
    ausente: aplicables.filter(a => a.asistencia?.estado === 'ausente').length,
    tardanza: aplicables.filter(a => a.asistencia?.estado === 'tardanza').length,
    excusa: aplicables.filter(a => a.asistencia?.estado === 'excusa').length,
    sinMarcar: aplicables.filter(a => !a.asistencia?.estado).length
  };

  const asignaturaSeleccionada = asignaturas.find(a => a.id === asignaturaId);
  // ENT1 · La tabla solo se muestra si es la de la selección actual. Si la
  // última comprobación falló, se sigue viendo, pero sin controles.
  const tablaDeLaSeleccion = seleccionCompleta && listaClave === claveSeleccion && estadoLista !== 'cargando';
  // Pendientes de ESTA selección (las de otras fechas o materias se muestran aparte).
  const pendientesSel: Record<number, SinConfirmar[]> = {};
  const pendientesOtras: SinConfirmar[] = [];
  for (const p of Object.values(sinConfirmar).sort((x, y) => x.seq - y.seq)) {
    if (p.clave === claveSeleccion) (pendientesSel[p.estudianteId] ||= []).push(p); else pendientesOtras.push(p);
  }
  const nSinConfirmar = Object.values(pendientesSel).reduce((n, l) => n + l.length, 0);
  const describirSeleccion = (clave: string) => {
    const [, , , materia, f] = clave.split('|');
    const nombreMateria = materia === 'P' ? 'asistencia diaria'
      : (asignaturas.find(a => String(a.id) === materia)?.nombre || `materia ${materia}`);
    return `${f.split('-').reverse().join('/')} · ${nombreMateria}`;
  };

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
      
      {/* P3.1 — el profesor que no es titular SÍ ve la lista: necesita saber
          quién está presente para dar su clase. Solo se le apagan los
          controles, y se le dice por qué en una línea. */}
      {!puedeEditar && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-blue-800">
            <strong>ℹ️</strong> {textoSoloLectura(esProfesor, permisoAsistencia.motivo)}
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

      {/* ENT1 · Estado de la lista: sin una lista válida para la selección
          actual no se marca, y se dice por qué. */}
      {seleccionCompleta && (estadoLista === 'sin_conexion' || estadoLista === 'error' || !enLinea || nSinConfirmar > 0) && (
        <div role="status" className="p-3 bg-amber-50 border border-amber-300 text-amber-900 rounded-lg flex flex-wrap items-center justify-between gap-2">
          <span>
            {!enLinea || estadoLista === 'sin_conexion'
              ? '📡 Sin conexión con el servidor. La lista no está confirmada y no se puede marcar; se actualizará al recuperar la conexión.'
              : estadoLista === 'error'
                ? '⚠️ No se pudo cargar la lista para esta selección. No se puede marcar hasta cargarla.'
                : `⏳ ${nSinConfirmar} operación(es) sin confirmar en esta fecha y materia: no llegó la respuesta del servidor. La lista muestra el estado leído ahora, que no confirma ningún envío: pudo no aplicarse, aplicarse más tarde o cambiar desde otro dispositivo. Vuelva a marcar si corresponde. «Quitar aviso» no cancela el envío ni modifica la asistencia.`}
          </span>
          <button onClick={() => cargarAsistencia()} disabled={saving || revalidando}
                  className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm disabled:opacity-50">
            {nSinConfirmar > 0 && estadoLista === 'ok' && enLinea ? 'Comprobar' : 'Reintentar'}
          </button>
        </div>
      )}
      {pendientesOtras.length > 0 && (
        <div role="status" className="p-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg text-sm">
          ⏳ También hay operaciones sin confirmar en otras selecciones:{' '}
          {pendientesOtras.map(p => `${p.nombre} (${describirSeleccion(p.clave)}: se pidió ${p.pedido || 'desmarcar'}`
            + `${p.observado !== undefined || p.filaNoRecibida ? '; ' + textoObservado(p) : ''})`).join(' · ')}.
          Se comprobarán al abrir esa fecha y materia.
        </div>
      )}
      {seleccionCompleta && revalidando && (
        <div role="status" className="text-xs text-gray-500">Actualizando la lista…</div>
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
                      <option key={c.id} value={c.id}>{labelCurso(c)}</option>
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
            {tablaDeLaSeleccion && asistencias.length > 0 && puedeMarcar && (
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
                onClick={() => cargarAsistencia()}
                disabled={saving}
                title="Actualizar la lista"
                className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 disabled:opacity-50"
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

        {/* ENT-B · vacaciones: no se pasa lista en esta fecha. */}
        {vacaciones && tablaDeLaSeleccion && (
          <div role="status" data-vacaciones
               className="mt-3 p-3 rounded-lg border border-blue-200 bg-blue-50 text-sm text-blue-800">
            🏖️ <strong>{vacaciones.nombre}</strong> (del{' '}
            {new Date(vacaciones.fecha_inicio + 'T12:00:00').toLocaleDateString('es-DO', { day: 'numeric', month: 'long' })} al{' '}
            {new Date(vacaciones.fecha_fin + 'T12:00:00').toLocaleDateString('es-DO', { day: 'numeric', month: 'long', year: 'numeric' })}):
            no se registra asistencia en esta fecha y no cuenta como día de clase.
          </div>
        )}

        {/* S1 — "No hubo clase". Solo Secundaria: en Primaria la asistencia es
            del curso y no hay una clase concreta que justificar. */}
        {cursoId > 0 && !esPrimaria && asignaturaId > 0 && !loading && (
          <div className="mt-3">
            <SesionNoImpartidaPanel
              cursoId={cursoId}
              asignaturaId={asignaturaId}
              fecha={fecha}
              puedeEditar={puedeEditar}
              sesion={sesionNI}
              onCambio={cargarAsistencia}
            />
          </div>
        )}
      </div>

      {/* ASIS-DASH-1 · Vista rápida del día (solo lectura) */}
      {veVistaRapida && cursoId > 0 && (
        <VistaRapidaAsistencia
          cursoId={cursoId}
          fecha={fecha}
          onAbrirMateria={esPrimaria ? undefined : (id) => setAsignaturaId(id)}
        />
      )}

      {/* Resumen */}
      {tablaDeLaSeleccion && asistencias.length > 0 && (
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
      {seleccionCompleta && estadoLista === 'cargando' && (
        <div role="status" className="text-center py-8 text-gray-600">
          <div className="inline-block animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
          <div className="text-sm mt-2">Cargando la lista de esta fecha… No se puede marcar hasta que llegue.</div>
        </div>
      )}

      {/* Tabla */}
      {tablaDeLaSeleccion && (
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
                  // TRAS-1 · bloqueada = no pertenecía al curso ese día. Un
                  // retirado DENTRO de su permanencia se puede corregir.
                  const noAplica = a.estudiante.aplica === false;
                  const esRetirado = noAplica || (!!a.estudiante.retirado && a.estudiante.aplica === undefined);
                  const avisos = a.estudiante.avisos || [];
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
                        {noAplica && (
                          <span className="inline-block px-2 py-0.5 bg-gray-600 text-white text-[10px] font-medium rounded uppercase tracking-wide">
                            No aplica
                          </span>
                        )}
                        {a.estudiante.asistencia_anulada && (
                          <span data-anulada
                                title={`Anulada por retiro${a.estudiante.asistencia_anulada.motivo ? `: ${a.estudiante.asistencia_anulada.motivo}` : ''}`}
                                className="inline-block px-2 py-0.5 bg-gray-100 text-gray-500 border border-gray-300 text-[10px] rounded line-through">
                            {a.estudiante.asistencia_anulada.estado_original} · anulada por retiro
                          </span>
                        )}
                        {esRetirado && !noAplica && a.estudiante.aplica === undefined && (
                          <span
                            title={a.estudiante.motivo_retiro || 'Estudiante retirado'}
                            className="inline-block px-2 py-0.5 bg-gray-700 text-white text-[10px] font-medium rounded uppercase tracking-wide"
                          >
                            RETIRADO {a.estudiante.fecha_retiro ? a.estudiante.fecha_retiro.slice(5).replace('-','/') : ''}
                          </span>
                        )}
                        {!noAplica && avisos.length > 0 && a.estudiante.aplica === true && (
                          <span title="En la fecha consultada pertenecía a este curso; su situación actual se indica debajo"
                                className="inline-block px-2 py-0.5 bg-indigo-50 text-indigo-800 border border-indigo-200 text-[10px] font-medium rounded">
                            Pertenecía ese día
                          </span>
                        )}
                        {(pendientesSel[a.estudiante.id] || []).map(p => (
                          <span key={p.seq} data-pendiente={p.seq}
                                title="Se envió, pero no llegó la respuesta del servidor; lo observado no confirma la operación"
                                className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-900 text-[10px] font-medium rounded">
                            Sin confirmar: se pidió {p.pedido || 'desmarcar'}
                            {(p.observado !== undefined || p.filaNoRecibida) && ` · ${textoObservado(p)}`}
                            <button type="button" onClick={() => quitarAviso(p)}
                                    title={AYUDA_QUITAR_AVISO} aria-label={`Quitar aviso. ${AYUDA_QUITAR_AVISO}`}
                                    className="ml-1 underline">Quitar aviso</button>
                          </span>
                        ))}
                        {a.estudiante.marca_fuera_de_permanencia && (
                          <span title="Esta marca existe pero cae fuera de su permanencia: se conserva y no cuenta"
                                className="inline-block px-2 py-0.5 bg-amber-100 text-amber-800 text-[10px] font-medium rounded">
                            Marca fuera de permanencia: {a.asistencia?.estado}
                          </span>
                        )}
                      </div>
                      {avisos.length > 0 && (
                        <div className="text-[10px] sm:text-xs text-indigo-700 mt-0.5">
                          <span className="font-semibold">Situación actual:</span> {avisos.join(' · ')}
                        </div>
                      )}
                    </td>
                    <td className="px-1 sm:px-4 py-2">
                      <div className="flex justify-center gap-1 sm:gap-2">
                        {estados.map(e => (
                          <button
                            key={e.val}
                            onClick={() => !esRetirado && puedeMarcar && marcarAsistencia(a.estudiante.id, e.val)}
                            disabled={saving || !puedeMarcar || esRetirado}
                            title={noAplica ? 'No aplica: no pertenecía a este curso en esta fecha'
                                   : esRetirado ? 'Estudiante retirado'
                                   : sesionNI ? 'Clase no impartida: ' + sesionNI.motivo
                                   : e.label}
                            className={`w-8 h-8 sm:w-10 sm:h-10 rounded-lg text-base sm:text-xl transition-all border-2 ${
                              esRetirado
                                ? 'bg-gray-100 border-gray-200 cursor-not-allowed opacity-40'
                                : a.asistencia?.estado === e.val
                                  ? `${e.color} text-white border-transparent scale-110 shadow-md`
                                  : puedeMarcar
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
