import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import {
  Users, GraduationCap, TrendingUp, AlertTriangle, Clock, BookOpen,
  CalendarCheck, FileBarChart, Bell, ChevronRight, MapPin, Plus, X,
  Brain, Star, Edit3, Save, Activity, StickyNote, Pin, Trash2
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts';
import { colorPorNombreCurso } from '../../utils/colorPorCurso';

interface Stats {
  estudiantes: number; profesores: number; cursos: number;
  reportes_pendientes: number; casos_psicologia: number;
  asignaturas?: number; casos_pendientes?: number;
  casos_en_proceso?: number; casos_urgentes?: number; casos_atendidos_mes?: number;
}
interface GraficoData {
  promedios_por_grado: Array<{ grado: string; promedio: number; estudiantes: number }>;
  estado_estudiantes: Array<{ nombre: string; cantidad: number; color: string }>;
  asistencia_resumen: {
    presentes: number; ausentes: number; tardanzas: number; porcentaje_asistencia: number;
    periodo_inicio?: string | null; periodo_fin?: string | null;
  };
  asistencia_hoy?: {
    fecha: string | null;
    presentes: number; ausentes: number; tardanzas: number; excusas: number;
    no_registrados: number;
    total_estudiantes: number;
    porcentaje_asistencia: number;
  };
  asistencia_por_materia?: Array<{ asignatura: string; presentes: number; ausentes: number; tardanzas: number; excusas: number; total: number; porcentaje: number }>;
  // v2.14: desglose de asistencia de HOY por curso (registrado=false ⇒ "Sin registrar")
  asistencia_hoy_por_curso?: Array<{
    curso_id: number; curso: string; total: number;
    presentes: number; ausentes: number; tardanzas: number; excusas: number;
    sin_marca: number; registrado: boolean; porcentaje: number;
  }>;
  ranking_mejor?: Array<{ nombre: string; curso: string; promedio: number; corte?: number }>;
  ranking_peligro?: Array<{ nombre: string; curso: string; promedio: number; corte?: number }>;
  periodo_activo?: number;
}
// v2.14: clave+atendible ⇒ la alerta puede marcarse como atendida (con nota) y desaparece
interface Alerta { tipo: string; prioridad: string; mensaje: string; count?: number; link?: string; clave?: string; atendible?: boolean; }

// Labels amigables para los tipos de alerta. Si el tipo no está aquí,
// se usa el fallback `tipo.replace('_', ' ')` (que es lo que había antes).
const ALERTA_LABELS: Record<string, string> = {
  'inasistencia': 'Inasistencia',
  'comunicado': 'Comunicado',
  'asistencia': 'Asistencia pendiente',
  'solicitud_edicion': 'Solicitud de edición',
  // Alertas v2.13 secundaria
  'evaluacion_extra_pendiente': 'Evaluación extra',
  'cierre_periodo_secundaria': 'Cierre de período',
  'profesores_atrasados_secundaria': 'Profesores atrasados',
  // Alertas v2.14
  'inasistencia_semana': 'Inasistencia semanal',
  'asistencia_sin_registrar': 'Asistencia sin registrar',
};
interface HorarioHoy { id: number; hora_inicio: string; hora_fin: string; asignatura: string; curso: string; curso_id: number; aula: string; }
interface Comunicado { id: number; titulo: string; contenido: string; autor: string; fecha: string; imagen?: string; }
interface DashboardProfesor {
  dia: string; dia_hoy: string; es_proximo_dia: boolean; fecha: string;
  horario_hoy: HorarioHoy[];
  cursos_asignados: Array<{ curso_id: number; curso: string; asignatura: string; estudiantes: number; tanda?: string }>;
  pendientes_calificar: Array<{ curso: string; asignatura: string; sin_nota: number; curso_id: number; asignatura_id: number }>;
  periodo_activo: number;
}
interface DashboardDireccion {
  periodo_activo: number; ano_escolar: string;
  profesores_sin_completar: Array<{ profesor: string; curso: string; asignatura: string; sin_nota: number }>;
  resumen_cursos: Array<{ curso: string; estudiantes: number; promedio: number; asistencia: number }>;
}
interface DashboardPsicologia {
  pendientes: number; en_proceso: number; atendidos_total: number; urgentes: number;
  casos_recientes_7dias: number;
  mis_casos: Array<{ id: number; estudiante: string; tipo: string; urgencia: string; estado: string; fecha: string; solicitante: string }>;
  casos_por_tipo: Array<{ tipo: string; cantidad: number }>;
}
interface NotaPersonal {
  id: number; titulo: string; contenido: string; color: string;
  fijada: boolean; fecha_creacion: string; fecha_actualizacion: string;
}
interface DashboardSecretaria {
  total_estudiantes: number;
  matriculados_hoy: number;
  matriculados_semana: number;
  cursos_vacios: number;
  total_cursos: number;
  estudiantes_por_curso: Array<{ curso_id: number; curso: string; estudiantes: number }>;
  ano_escolar: string;
  periodo_activo: number;
}

export const DashboardPage = () => {
  const { user } = useAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [graficos, setGraficos] = useState<GraficoData | null>(null);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [alertasOcultas, setAlertasOcultas] = useState<number[]>([]);
  // v2.14: atención de alertas (inasistencia): clave en proceso, nota y claves ya atendidas en esta sesión
  const [atendiendoClave, setAtendiendoClave] = useState<string | null>(null);
  const [notaAtencion, setNotaAtencion] = useState('');
  const [alertasAtendidas, setAlertasAtendidas] = useState<string[]>([]);
  const [comunicados, setComunicados] = useState<Comunicado[]>([]);
  const [dashProfesor, setDashProfesor] = useState<DashboardProfesor | null>(null);
  const [dashDireccion, setDashDireccion] = useState<DashboardDireccion | null>(null);
  const [dashPsicologia, setDashPsicologia] = useState<DashboardPsicologia | null>(null);
  const [dashSecretaria, setDashSecretaria] = useState<DashboardSecretaria | null>(null);
  const [notas, setNotas] = useState<NotaPersonal[]>([]);
  const [loading, setLoading] = useState(true);

  const esProfesor = user?.role === 'profesor';
  const esDireccion = user?.role === 'direccion';
  const esCoordinador = user?.role === 'coordinador';
  const esPsicologia = user?.role === 'psicologia';
  const esSecretaria = user?.role === 'secretaria';

  useEffect(() => { cargarDatos(); }, [user]);
  
  // v2.11.1: recargar datos cuando la pestaña vuelve a estar visible
  // (ej: el director cambió de tab para marcar asistencia y volvió).
  // También permite ver cambios casi en tiempo real si trabaja en varias tabs.
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        cargarDatos();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  const cargarDatos = async () => {
    try {
      const promises: Promise<any>[] = [
        api.get('/dashboard/stats-rol').catch(() => api.get('/dashboard/stats')),
        api.get('/dashboard/alertas').catch(() => ({ data: [] })),
        api.get('/comunicados').catch(() => ({ data: [] })),
        api.get('/notas-personales').catch(() => ({ data: [] })),
      ];
      if (esProfesor) {
        promises.push(api.get('/dashboard/profesor').catch(() => ({ data: null })));
      } else if (esDireccion || esCoordinador) {
        promises.push(api.get('/dashboard/graficos').catch(() => ({ data: null })));
        promises.push(api.get('/dashboard/direccion').catch(() => ({ data: null })));
      } else if (esPsicologia) {
        promises.push(api.get('/dashboard/psicologia').catch(() => ({ data: null })));
      } else if (esSecretaria) {
        promises.push(api.get('/dashboard/secretaria').catch(() => ({ data: null })));
      }
      const results = await Promise.all(promises);
      setStats(results[0].data);
      setAlertas(results[1].data || []);
      setComunicados((results[2].data || []).filter((c: any) => !c.leido_por_mi && c.autor_id !== user?.id));
      setNotas(results[3].data || []);
      if (esProfesor && results[4]?.data) setDashProfesor(results[4].data);
      else if ((esDireccion || esCoordinador)) {
        if (results[4]?.data) setGraficos(results[4].data);
        if (results[5]?.data) setDashDireccion(results[5].data);
      } else if (esPsicologia && results[4]?.data) setDashPsicologia(results[4].data);
      else if (esSecretaria && results[4]?.data) setDashSecretaria(results[4].data);
    } catch (error) { console.error('Error cargando dashboard:', error); }
    finally { setLoading(false); }
  };

  const marcarComunicadoLeido = async (id: number) => {
    try { await api.post(`/comunicados/${id}/marcar-leido`); setComunicados(prev => prev.filter(c => c.id !== id)); } catch (e) {}
  };

  if (loading) return (<div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div></div>);

  // v2.14: marcar una alerta atendible como atendida (con nota de seguimiento).
  // Solo inserta en alertas_atendidas en el backend; la alerta desaparece del
  // dashboard y del badge del sidebar. Si el caso se repite otra semana, reaparece.
  const atenderAlerta = async (alerta: Alerta) => {
    if (!alerta.clave) return;
    try {
      await api.post('/dashboard/alertas/atender', { clave: alerta.clave, tipo: alerta.tipo, nota: notaAtencion });
      setAlertasAtendidas(prev => [...prev, alerta.clave!]);
      setAtendiendoClave(null);
      setNotaAtencion('');
    } catch (e) { console.error('Error atendiendo alerta:', e); }
  };

  const alertasVisibles = alertas.filter((a, i) =>
    !alertasOcultas.includes(i) && !(a.clave && alertasAtendidas.includes(a.clave))
  );

  // v2.14: sección de Alertas reutilizable. Para dirección/coordinación se
  // renderiza ARRIBA (justo después de las stats); para los demás roles queda
  // en su posición de siempre, al final.
  const seccionAlertas = alertasVisibles.length > 0 ? (
    <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
      <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
        <h2 className="font-bold text-gray-800 flex items-center gap-2"><Bell className="text-amber-500" /> Alertas</h2>
        <div className="flex items-center gap-2">
          <span className="bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">{alertasVisibles.length}</span>
          <button onClick={() => setAlertasOcultas(alertas.map((_, i) => i))} className="text-xs text-gray-400 hover:text-gray-600">Ocultar todas</button>
        </div>
      </div>
      <div className="divide-y">
        {alertasVisibles.map((alerta) => (
          <div key={alerta.clave || `${alerta.tipo}-${alertas.indexOf(alerta)}`} className="hover:bg-gray-50">
            <div className="p-4 flex items-start gap-3">
              <Link to={(alerta as any).link || '#'} className="flex items-start gap-3 flex-1 min-w-0">
                <span className={`w-3 h-3 mt-1.5 rounded-full flex-shrink-0 ${alerta.prioridad === 'alta' ? 'bg-red-500 animate-pulse' : alerta.prioridad === 'media' ? 'bg-amber-500' : 'bg-blue-500'}`}></span>
                <div className="flex-1 min-w-0"><p className="text-sm font-medium text-gray-800 truncate">{alerta.mensaje}</p><p className="text-xs text-gray-400 mt-1 capitalize">{ALERTA_LABELS[alerta.tipo] || alerta.tipo.replace('_', ' ')}</p></div>
                {alerta.count && alerta.count > 0 && <span className={`px-2 py-1 text-xs rounded-full font-bold flex-shrink-0 ${alerta.prioridad === 'alta' ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-600'}`}>{alerta.count}</span>}
              </Link>
              {alerta.atendible && alerta.clave && (esDireccion || esCoordinador) && (
                <button
                  onClick={() => { setAtendiendoClave(atendiendoClave === alerta.clave ? null : alerta.clave!); setNotaAtencion(''); }}
                  className="flex-shrink-0 px-2.5 py-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100"
                  title="Marcar como atendida (con nota de seguimiento)"
                >
                  ✓ Atender
                </button>
              )}
              <button onClick={() => setAlertasOcultas([...alertasOcultas, alertas.indexOf(alerta)])} className="text-gray-300 hover:text-gray-500 flex-shrink-0 p-1" title="Ocultar">
                <X size={14} />
              </button>
            </div>
            {alerta.atendible && alerta.clave === atendiendoClave && (
              <div className="px-4 pb-4 -mt-1 flex flex-col sm:flex-row gap-2">
                <input
                  type="text"
                  value={notaAtencion}
                  onChange={e => setNotaAtencion(e.target.value)}
                  placeholder="Nota de seguimiento (opcional): ej. se llamó a la madre..."
                  maxLength={300}
                  className="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-emerald-400 focus:outline-none"
                  autoFocus
                />
                <div className="flex gap-2 flex-shrink-0">
                  <button onClick={() => atenderAlerta(alerta)} className="px-3 py-1.5 bg-emerald-600 text-white text-xs font-medium rounded-lg hover:bg-emerald-700">Confirmar</button>
                  <button onClick={() => { setAtendiendoClave(null); setNotaAtencion(''); }} className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700">Cancelar</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  ) : null;

  const getRoleLabel = () => {
    const labels: Record<string, string> = { profesor: 'Panel de Control — Profesor', direccion: 'Panel de Control — Dirección', coordinador: 'Panel de Control — Coordinación', psicologia: 'Panel de Control — Psicología', secretaria: 'Panel de Control — Secretaría' };
    return labels[user?.role || ''] || 'Panel de Control';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-800 text-white p-6 rounded-xl shadow-lg">
        <h1 className="text-2xl font-bold truncate">¡Bienvenido, {user?.nombre}!</h1>
        <p className="text-blue-100 mt-1">{getRoleLabel()}</p>
        {dashDireccion && <p className="text-blue-200 text-sm mt-2">Año Escolar: {dashDireccion.ano_escolar} | Período Activo: P{dashDireccion.periodo_activo}</p>}
        {dashSecretaria && <p className="text-blue-200 text-sm mt-2">Año Escolar: {dashSecretaria.ano_escolar} | Período Activo: P{dashSecretaria.periodo_activo}</p>}
      </div>

      {/* COMUNICADOS IMPORTANTES - Banner visible al entrar */}
      {comunicados.length > 0 && (
        <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-xl shadow-sm border border-amber-200 overflow-hidden animate-fade-in">
          <div className="p-4 border-b border-amber-200 bg-amber-100/50 flex items-center justify-between">
            <h2 className="font-bold text-amber-800 flex items-center gap-2">📢 Comunicados Nuevos</h2>
            <span className="bg-amber-500 text-white text-xs px-2 py-0.5 rounded-full">{comunicados.length}</span>
          </div>
          <div className="divide-y divide-amber-100">
            {comunicados.slice(0, 3).map((com) => (
              <div key={com.id} className="p-4 hover:bg-amber-50/50">
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 min-w-0"><h3 className="font-semibold text-gray-800 truncate">{com.titulo}</h3><p className="text-sm text-gray-600 mt-1 line-clamp-2">{com.contenido}</p><p className="text-xs text-gray-400 mt-2">Por {com.autor} • {new Date(com.fecha).toLocaleDateString('es-DO')}</p></div>
                  <button onClick={() => marcarComunicadoLeido(com.id)} className="text-amber-600 hover:text-amber-800 text-xs font-medium px-3 py-1 rounded-lg bg-amber-100 hover:bg-amber-200 flex-shrink-0">✓ Leído</button>
                </div>
              </div>
            ))}
          </div>
          {comunicados.length > 3 && <Link to="/comunicacion" className="block p-3 text-center text-amber-700 hover:bg-amber-100 border-t border-amber-200 text-sm font-medium">Ver todos ({comunicados.length})</Link>}
        </div>
      )}

      {/* STATS POR ROL */}
      {(esDireccion || esCoordinador) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<GraduationCap size={24} />} title="Estudiantes" value={stats?.estudiantes || 0} color="blue" />
          <StatCard icon={<Users size={24} />} title="Profesores" value={stats?.profesores || 0} color="emerald" />
          <StatCard icon={<AlertTriangle size={24} />} title="Reportes Pend." value={stats?.reportes_pendientes || 0} color="amber" />
          <StatCard icon={<BookOpen size={24} />} title="Cursos" value={stats?.cursos || 0} color="purple" />
        </div>
      )}
      {esSecretaria && dashSecretaria && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<GraduationCap size={24} />} title="Total Estudiantes" value={dashSecretaria.total_estudiantes} color="blue" />
          <StatCard icon={<Plus size={24} />} title="Matriculados Hoy" value={dashSecretaria.matriculados_hoy} color="emerald" />
          <StatCard icon={<TrendingUp size={24} />} title="Esta Semana" value={dashSecretaria.matriculados_semana} color="purple" />
          <StatCard icon={<BookOpen size={24} />} title="Cursos Activos" value={dashSecretaria.total_cursos} color="amber" />
        </div>
      )}
      {esProfesor && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<GraduationCap size={24} />} title="Mis Estudiantes" value={stats?.estudiantes || 0} color="blue" />
          <StatCard icon={<BookOpen size={24} />} title="Mis Cursos" value={stats?.cursos || 0} color="emerald" />
          <StatCard icon={<FileBarChart size={24} />} title="Mis Asignaturas" value={stats?.asignaturas || 0} color="purple" />
          <StatCard icon={<AlertTriangle size={24} />} title="Mis Reportes" value={stats?.reportes_pendientes || 0} color="amber" />
        </div>
      )}
      {esPsicologia && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={<Clock size={24} />} title="Pendientes" value={stats?.casos_pendientes || 0} color="amber" />
          <StatCard icon={<Activity size={24} />} title="En Proceso" value={stats?.casos_en_proceso || 0} color="blue" />
          <StatCard icon={<AlertTriangle size={24} />} title="Urgentes" value={stats?.casos_urgentes || 0} color="amber" />
          <StatCard icon={<Star size={24} />} title="Atendidos (Mes)" value={stats?.casos_atendidos_mes || 0} color="emerald" />
        </div>
      )}

      {/* ALERTAS (v2.14): para dirección/coordinación van ARRIBA, justo
          después de las stats — es la sección más valiosa del panel y estaba
          enterrada al fondo (había que scrollear dos pantallas para verla). */}
      {(esDireccion || esCoordinador) && seccionAlertas}

      {/* GUÍA INICIAL */}
      {(esDireccion || esCoordinador) && stats && stats.estudiantes === 0 && stats.profesores === 0 && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border-2 border-blue-200 p-6">
          <h2 className="text-xl font-bold text-blue-800 mb-4">🚀 Guía de Configuración Inicial</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Link to="/configuracion" className="bg-white p-4 rounded-lg border-2 border-blue-200 hover:border-blue-400"><div className="text-2xl mb-2">1️⃣</div><p className="font-semibold">Crear Año Escolar</p><p className="text-xs text-gray-500 mt-1">Configuración → Períodos</p></Link>
            <Link to="/usuarios" className="bg-white p-4 rounded-lg border-2 border-blue-200 hover:border-blue-400"><div className="text-2xl mb-2">2️⃣</div><p className="font-semibold">Crear Profesores</p><p className="text-xs text-gray-500 mt-1">Usuarios → + Nuevo</p></Link>
            <Link to="/configuracion" className="bg-white p-4 rounded-lg border-2 border-blue-200 hover:border-blue-400"><div className="text-2xl mb-2">3️⃣</div><p className="font-semibold">Crear Cursos</p><p className="text-xs text-gray-500 mt-1">Configuración → Cursos</p></Link>
            <Link to="/asignaciones" className="bg-white p-4 rounded-lg border-2 border-blue-200 hover:border-blue-400"><div className="text-2xl mb-2">4️⃣</div><p className="font-semibold">Asignar Profesores</p><p className="text-xs text-gray-500 mt-1">Asignaciones</p></Link>
          </div>
        </div>
      )}

      {/* DASHBOARD PROFESOR */}
      {esProfesor && dashProfesor && (<>
        <div className="bg-white rounded-xl shadow-sm border p-5">
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2 mb-4">
            <Clock className="text-blue-600" />
            {dashProfesor.es_fin_semana ? '🏖️ Fin de Semana' :
             dashProfesor.todas_pasaron ? `✅ ${dashProfesor.dia_hoy}` :
             dashProfesor.es_proximo_dia ? `📅 Próximas Clases - ${dashProfesor.dia}` :
             `🕐 Mi Horario – ${dashProfesor.dia}`}
          </h2>
          {/* Mensaje de fin de semana o clases terminadas */}
          {(dashProfesor.es_fin_semana || dashProfesor.todas_pasaron) && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 mb-3 text-sm text-green-700 font-medium">
              {dashProfesor.es_fin_semana ? '🟢 No tienes clases hoy — disfruta tu fin de semana' :
               '✅ Terminaste tus clases de hoy'}
            </div>
          )}
          {dashProfesor.es_proximo_dia && (dashProfesor.es_fin_semana || dashProfesor.todas_pasaron) && (
            <p className="text-xs text-gray-500 mb-2">Próximas clases: {dashProfesor.dia}</p>
          )}
          {dashProfesor.horario_hoy.length > 0 ? (() => {
            const to12h = (t: string) => {
              if (!t) return '';
              const [hh, mm] = t.split(':').map(Number);
              const ampm = hh >= 12 ? 'PM' : 'AM';
              const h12 = hh % 12 || 12;
              return `${h12}:${mm.toString().padStart(2, '0')} ${ampm}`;
            };
            const now = new Date();
            const nowMin = now.getHours() * 60 + now.getMinutes();
            const clases = dashProfesor.horario_hoy.map((h: any) => {
              const [h1, m1] = (h.hora_inicio || '0:0').split(':').map(Number);
              const [h2, m2] = (h.hora_fin || '0:0').split(':').map(Number);
              return { ...h, startMin: h1 * 60 + m1, endMin: h2 * 60 + m2 };
            });
            
            // Si es día futuro, mostrar las primeras 2 clases sin filtrar por hora
            const esFuturo = dashProfesor.es_proximo_dia;
            
            let currentIdx = -1;
            let nextIdx = -1;
            let isInLibre = false;
            let isBetween = false;
            let allDone = false;
            const show: number[] = [];
            
            if (esFuturo) {
              // Día futuro: mostrar primeras 2 clases
              show.push(0);
              if (clases.length > 1) show.push(1);
            } else {
              // Día actual: filtrar por hora
              currentIdx = clases.findIndex((c: any) => nowMin >= c.startMin && nowMin < c.endMin);
              nextIdx = currentIdx >= 0 ? currentIdx + 1 : clases.findIndex((c: any) => c.startMin > nowMin);
              isInLibre = currentIdx >= 0 && clases[currentIdx].tipo_bloque === 'libre';
              isBetween = currentIdx < 0 && clases.some((c: any) => c.endMin <= nowMin) && clases.some((c: any) => c.startMin > nowMin);
              allDone = clases.length > 0 && nowMin >= clases[clases.length - 1].endMin;
              
              if (currentIdx >= 0) show.push(currentIdx);
              if (nextIdx >= 0 && nextIdx < clases.length && !show.includes(nextIdx)) show.push(nextIdx);
              if (show.length === 0 && clases.length > 0) {
                const fi = clases.findIndex((c: any) => c.startMin > nowMin);
                show.push(fi >= 0 ? fi : 0);
              }
              if (show.length === 1 && show[0] + 1 < clases.length) show.push(show[0] + 1);
            }
            return (
              <div className="space-y-2">
                {!dashProfesor.es_proximo_dia && (
                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                    isInLibre || isBetween ? 'bg-green-50 text-green-700 border border-green-200' :
                    allDone ? 'bg-gray-50 text-gray-500 border border-gray-200' :
                    currentIdx >= 0 ? 'bg-green-50 text-green-700 border border-green-200' :
                    'bg-gray-50 text-gray-500 border border-gray-200'
                  }`}>
                    {isInLibre ? '🟢 Estás en hora libre' :
                     isBetween ? '🟢 Estás libre ahora' :
                     allDone ? '✅ Terminaste tus clases de hoy' :
                     currentIdx >= 0 ? '🟢 Estás en clase' :
                     '⏳ Esperando próxima clase'}
                  </div>
                )}
                {show.map((idx: number) => {
                  const h = clases[idx];
                  const isCurrent = idx === currentIdx;
                  const isNext = idx === nextIdx && currentIdx >= 0;
                  const isLibre = h.tipo_bloque === 'libre';
                  return (
                    <div key={h.id}>
                      {isCurrent && !isLibre && <span className="text-[10px] font-bold text-white bg-green-600 px-2 py-0.5 rounded-full mb-1 inline-block">EN CLASE</span>}
                      {isCurrent && isLibre && <span className="text-[10px] font-bold text-green-700 bg-green-100 px-2 py-0.5 rounded-full mb-1 inline-block">HORA LIBRE</span>}
                      {isNext && <span className="text-[10px] font-bold text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full mb-1 inline-block">SIGUIENTE</span>}
                      <div className={`flex items-center gap-3 p-3 rounded-lg border ${
                        esFuturo ? 'bg-gray-50 border-gray-200' :
                        isCurrent && !isLibre ? 'bg-green-50 border-green-300' :
                        isLibre && isCurrent ? 'bg-green-50 border-green-200' :
                        isNext ? 'bg-blue-50 border-blue-200' :
                        'bg-gray-50 border-gray-200'
                      }`}>
                        <div className="text-center min-w-[85px]">
                          <p className={`text-base font-bold ${
                            esFuturo ? 'text-gray-700' :
                            isCurrent && !isLibre ? 'text-green-700' :
                            isLibre && isCurrent ? 'text-green-600' :
                            isNext ? 'text-blue-700' : 'text-gray-700'
                          }`}>{to12h(h.hora_inicio)}</p>
                          <p className="text-[11px] text-gray-400">a {to12h(h.hora_fin)}</p>
                        </div>
                        <div className={`h-8 w-px ${esFuturo ? 'bg-gray-200' : isLibre ? 'bg-green-200' : 'bg-gray-200'}`}></div>
                        <div className="flex-1 min-w-0">
                          {isLibre ? (
                            <p className={`font-semibold text-sm ${esFuturo ? 'text-gray-500' : 'text-green-700'}`}>{esFuturo ? '⏸ Hora Libre' : '🟢 Hora Libre'}</p>
                          ) : (
                            <><p className="font-semibold text-gray-800 truncate text-sm">{h.asignatura}</p><p className="text-xs text-gray-500 truncate">{h.curso}</p></>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {clases.length > 2 && (
                  <Link to="/horarios" className="block text-center text-xs text-blue-600 hover:text-blue-800 font-medium py-1">
                    Ver horario completo ({clases.filter((c: any) => c.tipo_bloque === 'clase').length} clases)
                  </Link>
                )}
              </div>
            );
          })() : (
            <div className="text-center py-4 bg-green-50 rounded-lg border border-green-200">
              <p className="text-green-700 font-medium text-sm">🟢 No tienes clases hoy</p>
              <p className="text-green-500 text-xs mt-1">Día libre</p>
            </div>
          )}
        </div>
        {dashProfesor.pendientes_calificar.length > 0 && (
          <div className="bg-amber-50 rounded-xl border border-amber-200 p-3">
            <Link to="/academico" className="flex items-center justify-between">
              <div className="flex items-center gap-2"><AlertTriangle size={16} className="text-amber-600" /><span className="font-bold text-amber-800 text-sm">Sin Calificar (P{dashProfesor.periodo_activo})</span></div>
              <span className="px-2.5 py-0.5 bg-amber-200 text-amber-800 text-xs font-bold rounded-full">{dashProfesor.pendientes_calificar.reduce((a: number, p: any) => a + p.sin_nota, 0)}</span>
            </Link>
          </div>
        )}
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-bold text-gray-800 flex items-center gap-2 text-sm"><BookOpen size={16} className="text-blue-600" /> Mis Cursos</h2>
            <span className="text-xs text-gray-400">{dashProfesor.cursos_asignados.length} asignaciones</span>
          </div>
          {dashProfesor.cursos_asignados.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {[...new Set(dashProfesor.cursos_asignados.map((c: any) => c.curso))].map((curso: any, idx: number) => (
                <span key={idx} className="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-md border border-blue-100">{curso}</span>
              ))}
            </div>
          ) : (<p className="text-gray-400 text-xs py-2">No tienes cursos asignados</p>)}
        </div>
      </>)}

      {/* DASHBOARD PSICOLOGÍA */}
      {esPsicologia && dashPsicologia && (<>
        {dashPsicologia.urgentes > 0 && (
          <div className="bg-red-50 rounded-xl border-2 border-red-200 p-6">
            <h2 className="text-lg font-bold text-red-800 flex items-center gap-2"><AlertTriangle className="text-red-600" /> {dashPsicologia.urgentes} Caso(s) Urgente(s)</h2>
            <Link to="/psicologia" className="inline-block mt-3 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700">Ir a Psicología</Link>
          </div>
        )}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2 mb-4"><Brain className="text-purple-600" /> Mis Casos Activos</h2>
          {dashPsicologia.mis_casos.length > 0 ? (
            <div className="space-y-3">
              {dashPsicologia.mis_casos.map((c) => (
                <Link key={c.id} to="/psicologia" className="flex items-center gap-4 p-4 rounded-lg border hover:shadow-md block">
                  <div className={`w-3 h-3 rounded-full flex-shrink-0 ${c.urgencia === 'urgente' ? 'bg-red-500 animate-pulse' : 'bg-blue-500'}`} />
                  <div className="flex-1 min-w-0"><p className="font-medium text-gray-800 truncate">{c.estudiante}</p><p className="text-sm text-gray-500 truncate">{c.tipo} • {c.solicitante}</p></div>
                  <span className={`px-2 py-1 text-xs font-bold rounded flex-shrink-0 ${c.estado === 'pendiente' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>{c.estado === 'pendiente' ? 'Pendiente' : 'En Proceso'}</span>
                </Link>
              ))}
            </div>
          ) : (<div className="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed"><Brain size={40} className="mx-auto mb-3 text-gray-300" /><p className="text-gray-600">No tienes casos asignados</p></div>)}
        </div>
        {dashPsicologia.casos_por_tipo.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-bold text-gray-800 mb-4">Casos Activos por Tipo</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {dashPsicologia.casos_por_tipo.map((t, idx) => {
                const colores: Record<string, string> = { emocional: 'bg-pink-50 border-pink-200 text-pink-700', conductual: 'bg-orange-50 border-orange-200 text-orange-700', academico: 'bg-blue-50 border-blue-200 text-blue-700', familiar: 'bg-purple-50 border-purple-200 text-purple-700' };
                return (<div key={idx} className={`p-4 rounded-lg border ${colores[t.tipo] || 'bg-gray-50 border-gray-200 text-gray-700'}`}><p className="text-2xl font-bold">{t.cantidad}</p><p className="text-sm capitalize font-medium">{t.tipo || 'Otro'}</p></div>);
              })}
            </div>
          </div>
        )}
      </>)}

      {/* DASHBOARD SECRETARÍA */}
      {esSecretaria && dashSecretaria && (<>
        {/* Accesos rápidos de secretaría */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Link to="/estudiantes" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition-all group">
            <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0"><GraduationCap size={22} /></div>
            <div className="min-w-0"><p className="font-semibold text-gray-800 text-sm">Estudiantes</p><p className="text-xs text-gray-500">Matriculación</p></div>
          </Link>
          <Link to="/registro-escolar" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-gray-200 hover:border-emerald-300 hover:bg-emerald-50 transition-all group">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center flex-shrink-0"><FileBarChart size={22} /></div>
            <div className="min-w-0"><p className="font-semibold text-gray-800 text-sm">Registro Escolar</p><p className="text-xs text-gray-500">Formato MINERD</p></div>
          </Link>
          <Link to="/boletines" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-gray-200 hover:border-purple-300 hover:bg-purple-50 transition-all group">
            <div className="w-10 h-10 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center flex-shrink-0"><BookOpen size={22} /></div>
            <div className="min-w-0"><p className="font-semibold text-gray-800 text-sm">Boletines</p><p className="text-xs text-gray-500">Emitir por período</p></div>
          </Link>
          <Link to="/reportes" className="flex items-center gap-3 p-4 bg-white rounded-xl border border-gray-200 hover:border-amber-300 hover:bg-amber-50 transition-all group">
            <div className="w-10 h-10 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center flex-shrink-0"><FileBarChart size={22} /></div>
            <div className="min-w-0"><p className="font-semibold text-gray-800 text-sm">Reportes</p><p className="text-xs text-gray-500">Por período</p></div>
          </Link>
        </div>

        {/* Estudiantes por curso */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2 mb-4"><GraduationCap className="text-blue-600" /> Estudiantes por Curso</h2>
          {dashSecretaria.estudiantes_por_curso.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {dashSecretaria.estudiantes_por_curso.map((c) => (
                <div key={c.curso_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border hover:shadow-sm transition-shadow">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-gray-800 truncate">{c.curso}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    <span className={`px-3 py-1 rounded-full text-sm font-bold ${c.estudiantes > 0 ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-400'}`}>
                      {c.estudiantes}
                    </span>
                    <Users size={14} className="text-gray-400" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed">
              <GraduationCap size={40} className="mx-auto mb-3 text-gray-300" />
              <p className="text-gray-600">No hay cursos configurados</p>
            </div>
          )}
          {dashSecretaria.cursos_vacios > 0 && (
            <div className="mt-3 p-3 bg-amber-50 rounded-lg border border-amber-200">
              <p className="text-sm text-amber-700"><AlertTriangle size={14} className="inline mr-1" />{dashSecretaria.cursos_vacios} curso(s) sin estudiantes matriculados</p>
            </div>
          )}
        </div>

        {/* Gráfico de distribución */}
        {dashSecretaria.estudiantes_por_curso.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-bold text-gray-800 mb-4">Distribución de Matrícula</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dashSecretaria.estudiantes_por_curso.filter(c => c.estudiantes > 0)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="curso" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="estudiantes" radius={[4, 4, 0, 0]}>
                    {dashSecretaria.estudiantes_por_curso.filter(c => c.estudiantes > 0).map((c) => (
                      <Cell key={`curso-${c.curso}`} fill={colorPorNombreCurso(c.curso)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </>)}

      {/* GRÁFICOS DIRECCIÓN */}
      {(esDireccion || esCoordinador) && (<>
        {graficos ? (
          <div className="space-y-3">
            {/* Fila 1: Promedio por Grado + Estado Estudiantes */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <div className="bg-white rounded-xl shadow-sm border p-4">
                <h2 className="font-bold text-gray-800 mb-3 flex items-center gap-2 text-sm"><TrendingUp size={16} className="text-blue-600" /> Promedio por grado {graficos.periodo_activo ? `(P${graficos.periodo_activo})` : ''}</h2>
                {graficos.promedios_por_grado && graficos.promedios_por_grado.length > 0 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={graficos.promedios_por_grado}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="grado" tick={{ fontSize: 9 }} />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Bar dataKey="promedio" radius={[6, 6, 0, 0]}>
                        {graficos.promedios_por_grado.map((g) => (
                          <Cell key={`grado-${g.grado}`} fill={colorPorNombreCurso(g.grado)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-center py-6 text-gray-400 text-sm">Sin datos de calificaciones aún</div>
                )}
              </div>
              <div className="bg-white rounded-xl shadow-sm border p-4">
                <h2 className="font-bold text-gray-800 mb-3 text-sm">Estado de estudiantes</h2>
                {graficos.estado_estudiantes && graficos.estado_estudiantes.some((e: any) => e.cantidad > 0) ? (
                  <>
                    <ResponsiveContainer width="100%" height={140}>
                      <PieChart><Pie data={graficos.estado_estudiantes} dataKey="cantidad" nameKey="nombre" cx="50%" cy="50%" outerRadius={55} innerRadius={30}>{graficos.estado_estudiantes.map((entry: any, index: number) => (<Cell key={index} fill={entry.color} />))}</Pie><Tooltip /></PieChart>
                    </ResponsiveContainer>
                    <div className="flex justify-center gap-3 mt-1">
                      {graficos.estado_estudiantes.map((e: any, i: number) => (
                        <span key={i} className="flex items-center gap-1 text-[11px] text-gray-600">
                          <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{background: e.color}}></span>
                          {e.nombre} {e.cantidad}
                        </span>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="text-center py-4">
                    <div className="flex justify-center gap-6">
                      <div className="text-center"><p className="text-2xl font-bold text-emerald-600">{stats?.estudiantes || 0}</p><p className="text-gray-400 text-[10px]">Matriculados</p></div>
                      <div className="text-center"><p className="text-2xl font-bold text-gray-300">0</p><p className="text-gray-400 text-[10px]">Calificados</p></div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Fila 2 (v2.14): Asistencia hoy POR CURSO. Cada curso reporta
                sus propios números; los cursos sin pasar lista se marcan en
                ámbar ("Sin registrar") en vez de inflar un "No reg." global
                que distorsionaba el porcentaje del día. */}
            <div className="bg-white rounded-xl shadow-sm border p-4">
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="font-bold text-gray-800 text-sm">Asistencia hoy</h2>
                {graficos.asistencia_hoy?.fecha && (
                  <span className="text-[10px] text-gray-400">
                    {new Date(graficos.asistencia_hoy.fecha + 'T00:00:00').toLocaleDateString('es-DO', { day: '2-digit', month: 'short' })}
                  </span>
                )}
              </div>

              {graficos.asistencia_hoy_por_curso && graficos.asistencia_hoy_por_curso.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-[10px] text-gray-400 uppercase tracking-wide">
                        <th className="text-left font-semibold pb-2">Curso</th>
                        <th className="text-center font-semibold pb-2">Pres.</th>
                        <th className="text-center font-semibold pb-2">Aus.</th>
                        <th className="text-center font-semibold pb-2">Tard.</th>
                        <th className="text-center font-semibold pb-2 hidden md:table-cell">Exc.</th>
                        <th className="text-right font-semibold pb-2">Asistencia</th>
                      </tr>
                    </thead>
                    <tbody>
                      {graficos.asistencia_hoy_por_curso.map((c) => (
                        <tr key={c.curso_id} className="border-t border-gray-100">
                          <td className="py-2 pr-2 text-xs font-medium text-gray-800">{c.curso}</td>
                          {c.registrado ? (
                            <>
                              <td className="py-2 text-center text-xs font-bold text-emerald-600">{c.presentes}</td>
                              <td className={`py-2 text-center text-xs font-bold ${c.ausentes > 0 ? 'text-red-500' : 'text-gray-300'}`}>{c.ausentes}</td>
                              <td className={`py-2 text-center text-xs font-bold ${c.tardanzas > 0 ? 'text-amber-500' : 'text-gray-300'}`}>{c.tardanzas}</td>
                              <td className="py-2 text-center text-xs text-gray-400 hidden md:table-cell">{c.excusas}</td>
                              <td className="py-2 text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden hidden sm:block">
                                    <div
                                      className={`h-full rounded-full ${c.porcentaje >= 90 ? 'bg-emerald-500' : c.porcentaje >= 75 ? 'bg-blue-500' : 'bg-red-400'}`}
                                      style={{ width: `${Math.min(100, c.porcentaje)}%` }}
                                    ></div>
                                  </div>
                                  <span className="text-xs font-bold text-gray-700 w-11 text-right">{c.porcentaje}%</span>
                                </div>
                              </td>
                            </>
                          ) : (
                            <td colSpan={5} className="py-2 text-right">
                              <Link to="/asistencia" className="inline-block px-2.5 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded-md text-[11px] font-medium hover:bg-amber-100" title="Este curso no ha pasado lista hoy">
                                Sin registrar
                              </Link>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : graficos.asistencia_hoy && graficos.asistencia_hoy.total_estudiantes > 0 ? (
                /* Fallback (compatibilidad): backend sin desglose por curso aún */
                <>
                  <div className="grid grid-cols-4 gap-2 text-center mb-3">
                    <div>
                      <p className="text-lg font-bold text-emerald-600">{graficos.asistencia_hoy.presentes}</p>
                      <p className="text-[10px] text-gray-400">Presentes</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-red-500">{graficos.asistencia_hoy.ausentes}</p>
                      <p className="text-[10px] text-gray-400">Ausentes</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-amber-500">{graficos.asistencia_hoy.excusas ?? 0}</p>
                      <p className="text-[10px] text-gray-400">Excusas</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-gray-400">{graficos.asistencia_hoy.no_registrados}</p>
                      <p className="text-[10px] text-gray-400">No reg.</p>
                    </div>
                  </div>
                  <div className="text-center pb-2 border-b border-gray-100">
                    <p className="text-2xl font-bold text-blue-600">{graficos.asistencia_hoy.porcentaje_asistencia}%</p>
                    <p className="text-[10px] text-gray-400">Asistencia hoy ({graficos.asistencia_hoy.presentes} de {graficos.asistencia_hoy.total_estudiantes})</p>
                  </div>
                </>
              ) : (
                <div className="text-center py-3 text-gray-400 text-sm">Sin registros de asistencia hoy</div>
              )}

              {/* Acumulado del mes (debajo, igual que siempre) */}
              <div className="pt-3 mt-3 border-t border-gray-100">
                <h3 className="font-semibold text-gray-700 text-xs mb-2">
                  Asistencia del mes
                  {graficos.asistencia_resumen?.periodo_inicio && graficos.asistencia_resumen?.periodo_fin && (
                    <span className="text-[10px] text-gray-400 font-normal ml-1">
                      ({new Date(graficos.asistencia_resumen.periodo_inicio + 'T00:00:00').toLocaleDateString('es-DO', { day: '2-digit', month: 'short' })}
                      {' al '}
                      {new Date(graficos.asistencia_resumen.periodo_fin + 'T00:00:00').toLocaleDateString('es-DO', { day: '2-digit', month: 'short' })})
                    </span>
                  )}
                </h3>
                {graficos.asistencia_resumen && (graficos.asistencia_resumen.presentes > 0 || graficos.asistencia_resumen.ausentes > 0) ? (
                  <div className="grid grid-cols-4 gap-2 text-center">
                    <div><p className="text-base font-bold text-emerald-600">{graficos.asistencia_resumen.presentes}</p><p className="text-[10px] text-gray-400">Presentes</p></div>
                    <div><p className="text-base font-bold text-red-500">{graficos.asistencia_resumen.ausentes}</p><p className="text-[10px] text-gray-400">Ausentes</p></div>
                    <div><p className="text-base font-bold text-amber-500">{graficos.asistencia_resumen.tardanzas}</p><p className="text-[10px] text-gray-400">Tardanzas</p></div>
                    <div><p className="text-base font-bold text-blue-600">{graficos.asistencia_resumen.porcentaje_asistencia}%</p><p className="text-[10px] text-gray-400">Asistencia</p></div>
                  </div>
                ) : (
                  <div className="text-center py-2 text-gray-400 text-xs">Sin registros este mes</div>
                )}
              </div>
            </div>

            {/* Fila 3 (v2.14): Mejores promedios + En peligro lado a lado —
                se eliminan las tarjetas horizontales largas medio vacías. */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <div className="bg-white rounded-xl shadow-sm border p-4">
                <h2 className="font-bold text-gray-800 mb-3 text-sm flex items-center gap-2"><span className="text-amber-500">⭐</span> Mejores promedios {graficos.periodo_activo ? `(P${graficos.periodo_activo})` : ''}</h2>
                {graficos.ranking_mejor && graficos.ranking_mejor.length > 0 ? (
                  <div className="space-y-1">
                    {graficos.ranking_mejor.map((e: any, i: number) => (
                      <div key={i} className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`text-xs font-bold w-5 text-center ${i < 3 ? 'text-amber-500' : 'text-gray-400'}`}>{i + 1}</span>
                          <div className="min-w-0"><p className="text-xs font-medium text-gray-800 truncate">{e.nombre}</p><p className="text-[10px] text-gray-400 truncate">{e.curso}</p></div>
                        </div>
                        <span className={`text-sm font-bold flex-shrink-0 ml-2 ${e.promedio >= 90 ? 'text-emerald-600' : e.promedio >= 80 ? 'text-blue-600' : 'text-gray-600'}`}>{e.promedio}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-4 text-gray-400 text-sm">Sin datos aún</div>
                )}
              </div>

              {/* v2.14: el corte es POR NIVEL (65 primaria / 70 secundaria) —
                  ya viene calculado del backend en e.corte. Antes el título
                  decía "< 70" fijo y ponía en peligro injustamente a primaria. */}
              <div className={`rounded-xl border p-4 ${graficos.ranking_peligro && graficos.ranking_peligro.length > 0 ? 'bg-red-50 border-red-200' : 'bg-white shadow-sm'}`}>
                <h2 className={`font-bold flex items-center gap-2 mb-2 text-sm ${graficos.ranking_peligro && graficos.ranking_peligro.length > 0 ? 'text-red-800' : 'text-gray-800'}`}>
                  <AlertTriangle size={16} className={graficos.ranking_peligro && graficos.ranking_peligro.length > 0 ? 'text-red-600' : 'text-gray-400'} /> Estudiantes en peligro (bajo el corte de su nivel)
                </h2>
                {graficos.ranking_peligro && graficos.ranking_peligro.length > 0 ? (
                  <div className="space-y-1">
                    {graficos.ranking_peligro.map((e: any, i: number) => (
                      <div key={i} className="flex items-center justify-between py-1.5 px-2 bg-white rounded-lg border border-red-100">
                        <div className="min-w-0"><p className="text-xs font-medium text-gray-800 truncate">{e.nombre}</p><p className="text-[10px] text-gray-400 truncate">{e.curso}{e.corte ? ` · corte ${e.corte}` : ''}</p></div>
                        <span className="text-sm font-bold text-red-600 flex-shrink-0 ml-2">{e.promedio}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-4 text-emerald-600 text-sm font-medium">✓ Ningún estudiante por debajo del corte</div>
                )}
              </div>
            </div>

            {/* Profesores con calificaciones pendientes */}
            {esDireccion && dashDireccion && dashDireccion.profesores_sin_completar && dashDireccion.profesores_sin_completar.length > 0 && (
              <div className="bg-amber-50 rounded-xl border border-amber-200 p-4">
                <h2 className="font-bold text-amber-800 flex items-center gap-2 mb-2 text-sm"><AlertTriangle size={16} className="text-amber-600" /> Profesores con calificaciones pendientes</h2>
                <div className="space-y-1">
                  {dashDireccion.profesores_sin_completar.map((p: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between py-1.5 px-2 bg-white rounded-lg border border-amber-100">
                      <div className="min-w-0"><p className="text-xs font-medium text-gray-800 truncate">{p.profesor}</p><p className="text-[10px] text-gray-500 truncate">{p.curso} - {p.asignatura}</p></div>
                      <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-[10px] font-bold rounded flex-shrink-0 ml-2">{p.sin_nota} sin nota</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border p-6 text-center">
            <TrendingUp size={32} className="mx-auto mb-2 text-gray-300" />
            <p className="text-gray-500 text-sm">Cargando estadísticas...</p>
          </div>
        )}
      </>)}

      {/* BLOC DE NOTAS - TODOS LOS ROLES */}
      <BlocDeNotas notas={notas} setNotas={setNotas} />

      {/* ALERTAS: los roles que no son dirección/coordinación las mantienen
          aquí, en su posición de siempre (al final). */}
      {!(esDireccion || esCoordinador) && seccionAlertas}

      {/* ACCESOS RÁPIDOS */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {esProfesor && (<><QuickLink icon={<BookOpen size={24} />} label="Calificaciones" to="/academico" color="blue" /><QuickLink icon={<CalendarCheck size={24} />} label="Asistencia" to="/asistencia" color="emerald" /><QuickLink icon={<GraduationCap size={24} />} label="Eval. Estudiantes" to="/eval-interna" color="purple" /><QuickLink icon={<FileBarChart size={24} />} label="Reportes" to="/reportes" color="amber" /></>)}
        {(esDireccion || esCoordinador) && (<><QuickLink icon={<BookOpen size={24} />} label="Calificaciones" to="/academico" color="blue" /><QuickLink icon={<GraduationCap size={24} />} label="Eval. Profesores" to="/evaluaciones" color="emerald" /><QuickLink icon={<FileBarChart size={24} />} label="Notas Período" to="/calificaciones-general" color="purple" /><QuickLink icon={<Users size={24} />} label="Usuarios" to="/usuarios" color="amber" /></>)}
        {esPsicologia && (<><QuickLink icon={<Brain size={24} />} label="Mis Casos" to="/psicologia" color="purple" /><QuickLink icon={<FileBarChart size={24} />} label="Reportes" to="/reportes" color="amber" /><QuickLink icon={<GraduationCap size={24} />} label="Estudiantes" to="/estudiantes" color="blue" /><QuickLink icon={<CalendarCheck size={24} />} label="Comunicación" to="/comunicacion" color="emerald" /></>)}
        {user?.role === 'secretaria' && (<><QuickLink icon={<GraduationCap size={24} />} label="Estudiantes" to="/estudiantes" color="blue" /><QuickLink icon={<FileBarChart size={24} />} label="Registro" to="/registro-escolar" color="emerald" /><QuickLink icon={<BookOpen size={24} />} label="Boletines" to="/boletines" color="purple" /><QuickLink icon={<CalendarCheck size={24} />} label="Comunicación" to="/comunicacion" color="amber" /></>)}
      </div>
    </div>
  );
};

// BLOC DE NOTAS
const BlocDeNotas = ({ notas, setNotas }: { notas: NotaPersonal[]; setNotas: (n: NotaPersonal[]) => void }) => {
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ titulo: '', contenido: '', color: 'yellow' });
  const colores: Record<string, { bg: string; border: string; header: string }> = {
    yellow: { bg: 'bg-yellow-50', border: 'border-yellow-200', header: 'bg-yellow-100' },
    blue: { bg: 'bg-blue-50', border: 'border-blue-200', header: 'bg-blue-100' },
    green: { bg: 'bg-emerald-50', border: 'border-emerald-200', header: 'bg-emerald-100' },
    pink: { bg: 'bg-pink-50', border: 'border-pink-200', header: 'bg-pink-100' },
    purple: { bg: 'bg-purple-50', border: 'border-purple-200', header: 'bg-purple-100' },
  };
  const guardar = async () => {
    try {
      if (editingId) { const res = await api.put(`/notas-personales/${editingId}`, form); setNotas(notas.map(n => n.id === editingId ? res.data : n)); }
      else { const res = await api.post('/notas-personales', form); setNotas([res.data, ...notas]); }
      setShowForm(false); setEditingId(null); setForm({ titulo: '', contenido: '', color: 'yellow' });
    } catch (e) { console.error('Error:', e); }
  };
  const eliminar = async (id: number) => { try { await api.delete(`/notas-personales/${id}`); setNotas(notas.filter(n => n.id !== id)); } catch (e) {} };
  const fijar = async (nota: NotaPersonal) => {
    try { const res = await api.put(`/notas-personales/${nota.id}`, { fijada: !nota.fijada }); setNotas(notas.map(n => n.id === nota.id ? res.data : n).sort((a, b) => (a.fijada === b.fijada ? 0 : a.fijada ? -1 : 1))); } catch (e) {}
  };
  const editar = (nota: NotaPersonal) => { setForm({ titulo: nota.titulo, contenido: nota.contenido, color: nota.color }); setEditingId(nota.id); setShowForm(true); };

  return (
    <div className="bg-white rounded-xl shadow-sm border p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2"><StickyNote className="text-yellow-500" /> Mis Notas</h2>
        <button onClick={() => { setShowForm(true); setEditingId(null); setForm({ titulo: '', contenido: '', color: 'yellow' }); }} className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"><Plus size={16} /> Nueva</button>
      </div>
      {showForm && (
        <div className="mb-4 p-4 bg-gray-50 rounded-lg border">
          <div className="flex items-center justify-between mb-3">
            <input type="text" placeholder="Título..." value={form.titulo} onChange={e => setForm({...form, titulo: e.target.value})} className="flex-1 px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
            <button onClick={() => { setShowForm(false); setEditingId(null); }} className="ml-2 text-gray-400 hover:text-gray-600"><X size={20} /></button>
          </div>
          <textarea placeholder="Escribe aquí..." value={form.contenido} onChange={e => setForm({...form, contenido: e.target.value})} rows={3} className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 mb-3" />
          <div className="flex items-center justify-between">
            <div className="flex gap-2">{Object.keys(colores).map(c => (<button key={c} onClick={() => setForm({...form, color: c})} className={`w-6 h-6 rounded-full border-2 ${colores[c].header} ${form.color === c ? 'border-gray-600 ring-2 ring-offset-1 ring-gray-400' : 'border-transparent'}`} />))}</div>
            <button onClick={guardar} className="flex items-center gap-1 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"><Save size={16} /> {editingId ? 'Actualizar' : 'Guardar'}</button>
          </div>
        </div>
      )}
      {notas.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {notas.map(nota => { const c = colores[nota.color] || colores.yellow; return (
            <div key={nota.id} className={`${c.bg} ${c.border} border rounded-lg overflow-hidden`}>
              <div className={`${c.header} px-3 py-2 flex items-center justify-between`}>
                <p className="font-semibold text-sm text-gray-800 truncate flex-1">{nota.titulo || 'Sin título'}</p>
                <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                  <button onClick={() => fijar(nota)} className={`p-1 rounded hover:bg-white/50 ${nota.fijada ? 'text-blue-600' : 'text-gray-400'}`}><Pin size={14} /></button>
                  <button onClick={() => editar(nota)} className="p-1 rounded hover:bg-white/50 text-gray-400 hover:text-blue-600"><Edit3 size={14} /></button>
                  <button onClick={() => eliminar(nota.id)} className="p-1 rounded hover:bg-white/50 text-gray-400 hover:text-red-600"><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="px-3 py-2"><p className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-4">{nota.contenido}</p><p className="text-xs text-gray-400 mt-2">{new Date(nota.fecha_actualizacion).toLocaleDateString('es-DO', { day: 'numeric', month: 'short' })}</p></div>
            </div>
          ); })}
        </div>
      ) : !showForm && (<div className="text-center py-6 bg-gray-50 rounded-lg border-2 border-dashed"><StickyNote size={36} className="mx-auto mb-2 text-gray-300" /><p className="text-sm text-gray-500">No tienes notas. Crea una para recordar algo importante.</p></div>)}
    </div>
  );
};

// COMPONENTES AUXILIARES
const StatCard = ({ icon, title, value, color }: { icon: React.ReactNode; title: string; value: number; color: 'blue' | 'emerald' | 'amber' | 'purple' }) => {
  const colors = { blue: 'bg-blue-50 border-blue-200 text-blue-600', emerald: 'bg-emerald-50 border-emerald-200 text-emerald-600', amber: 'bg-amber-50 border-amber-200 text-amber-600', purple: 'bg-purple-50 border-purple-200 text-purple-600' };
  return (<div className={`p-4 rounded-xl border ${colors[color]} transition-transform hover:scale-105`}><div className="flex items-center justify-between"><div className="min-w-0"><p className="text-xs text-gray-500 font-medium uppercase truncate">{title}</p><p className="text-2xl font-bold mt-1">{value}</p></div><div className="flex-shrink-0">{icon}</div></div></div>);
};

const QuickLink = ({ icon, label, to, color }: { icon: React.ReactNode; label: string; to: string; color: 'blue' | 'emerald' | 'amber' | 'purple' }) => {
  const colors = { blue: 'hover:border-blue-300 hover:bg-blue-50 text-blue-600', emerald: 'hover:border-emerald-300 hover:bg-emerald-50 text-emerald-600', amber: 'hover:border-amber-300 hover:bg-amber-50 text-amber-600', purple: 'hover:border-purple-300 hover:bg-purple-50 text-purple-600' };
  return (<Link to={to} className={`flex flex-col items-center justify-center p-4 bg-white rounded-xl border border-gray-200 ${colors[color]} transition-all group`}><div className="mb-2">{icon}</div><span className="text-sm font-medium text-gray-700 truncate w-full text-center">{label}</span><ChevronRight size={16} className="mt-1 text-gray-300 group-hover:translate-x-1 transition-transform" /></Link>);
};

export default DashboardPage;
