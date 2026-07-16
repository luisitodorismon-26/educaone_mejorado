import { useState, useEffect, ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { LanguageSelector } from '../../i18n';
import api from '../../services/api';
import {
  LayoutDashboard,
  BookOpen,
  CalendarCheck,
  Clock,
  MessageSquare,
  Brain,
  FileBarChart,
  FileText,
  Users,
  Settings,
  LogOut,
  Bell,
  Menu,
  X,
  GraduationCap,
  Calendar,
  Shield,
  BarChart3,
  ClipboardCheck,
  StickyNote,
  Building2,
  AlertTriangle,
  Award,
  ChevronDown,
  ChevronRight
} from 'lucide-react';

interface NavItem {
  path: string;
  label: string;
  icon: any;
  roles: string[];
  badge?: number;
  modulo?: string; // Si depende de un módulo habilitado
  section?: string; // agrupación en sidebar
}

interface ColegioConfig {
  nombre: string;
  logo: string | null;
  distrito?: string;
}

interface MainLayoutProps {
  children: ReactNode;
}

// v2.14: secciones abiertas por defecto la PRIMERA vez (luego manda localStorage).
// Dirección lidia sobre todo con lo académico y las personas (estudiantes,
// reportes), así que esas dos arrancan abiertas.
const SECCIONES_DEFAULT_ABIERTAS = ['Académico', 'Personas'];

export const MainLayout = ({ children }: MainLayoutProps) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [config, setConfig] = useState<ColegioConfig | null>(null);
  const [mensajesNoLeidos, setMensajesNoLeidos] = useState(0);
  const [comunicadosNoLeidos, setComunicadosNoLeidos] = useState(0);
  const [alertasCount, setAlertasCount] = useState(0);
  const [alertasData, setAlertasData] = useState<any[]>([]);
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [modulosConfig, setModulosConfig] = useState<any>(null);
  const [notificaciones, setNotificaciones] = useState<any[]>([]);
  const [notifNoLeidas, setNotifNoLeidas] = useState(0);
  const [showNotifPanel, setShowNotifPanel] = useState(false);

  // v2.14: menú colapsable con memoria. El estado abierto/cerrado de cada
  // sección se persiste en localStorage POR ROL, así al recargar la página
  // el menú queda exactamente como el usuario lo dejó (queja resuelta:
  // "al recargar vuelve al inicio"). Solo aplica a dirección/coordinación
  // (el menú de profesor/secretaría/psicología es corto y no lo necesita).
  const esMenuColapsable = user?.role === 'direccion' || user?.role === 'coordinador';
  const storageKey = `educaone_sidebar_secciones_${user?.role || 'anon'}`;
  const [seccionesAbiertas, setSeccionesAbiertas] = useState<string[]>(SECCIONES_DEFAULT_ABIERTAS);

  useEffect(() => {
    if (!user?.role) return;
    try {
      const guardado = localStorage.getItem(storageKey);
      if (guardado) {
        setSeccionesAbiertas(JSON.parse(guardado));
        return;
      }
    } catch {}
    setSeccionesAbiertas(SECCIONES_DEFAULT_ABIERTAS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role]);

  const toggleSeccion = (seccion: string) => {
    setSeccionesAbiertas(prev => {
      const next = prev.includes(seccion) ? prev.filter(s => s !== seccion) : [...prev, seccion];
      try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch {}
      return next;
    });
  };

  useEffect(() => {
    if (user?.role !== 'superadmin') {
      loadConfig();
      loadNotificaciones();
      loadModulosConfig();
      const interval = setInterval(loadNotificaciones, 30000);
      return () => clearInterval(interval);
    } else {
      setModulosConfig({});
    }
    // Dependencia user?.id: si el usuario cambia (logout + login a otro colegio),
    // recargamos todos los flags de módulos. Sin esto, queda con la config anterior.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.role]);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  const loadConfig = async () => {
    try {
      const res = await api.get('/configuracion/colegio');
      setConfig(res.data);
    } catch (e) {
      console.error('Error cargando config:', e);
    }
  };

  const loadNotificaciones = async () => {
    try {
      const [msgs, alertas, notifs] = await Promise.all([
        api.get('/mensajes/no-leidos'),
        api.get('/dashboard/alertas').catch(() => ({ data: [] })),
        api.get('/notificaciones?limit=10').catch(() => ({ data: { notificaciones: [], no_leidas: 0 } }))
      ]);
      setMensajesNoLeidos(msgs.data.count || 0);
      const comunicados = (alertas.data || []).find((a: any) => a.tipo === 'comunicado');
      setComunicadosNoLeidos(comunicados?.count || 0);
      setAlertasCount((alertas.data || []).length);
      setAlertasData(alertas.data || []);
      setNotificaciones(notifs.data.notificaciones || []);
      setNotifNoLeidas(notifs.data.no_leidas || 0);
    } catch (e) {
      // Silenciar error
    }
  };

  const marcarNotifLeida = async (id: number) => {
    try { await api.put(`/notificaciones/${id}/leer`); loadNotificaciones(); } catch {}
  };

  const marcarTodasLeidas = async () => {
    try { await api.put('/notificaciones/leer-todas'); loadNotificaciones(); } catch {}
  };

  const loadModulosConfig = async () => {
    try {
      const res = await api.get('/configuracion/modulos');
      setModulosConfig(res.data);
    } catch (e) {
      // Si falla cargar config, asumir TODO DESACTIVADO (seguro). Esto evita
      // que si el endpoint falla por cualquier motivo, el sidebar muestre
      // módulos que el colegio no tiene contratados.
      setModulosConfig({
        modulo_whatsapp: false, whatsapp_solo_direccion: false,
        modulo_psicologia: false, modulo_comunicacion_padres: false,
        modulo_eval_profesores: false, modulo_eval_interna: false,
        modulo_registro_escolar: false, permitir_profesor_reportes: false,
      });
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  // v2.14: badges por ruta a partir de las alertas del dashboard. Cada alerta
  // trae un `link`; sumamos sus counts por ruta y el item del menú muestra el
  // total en rojo (ej: "Asistencia 🔴3"). /comunicacion se excluye porque ya
  // tiene su propio badge de mensajes no leídos (evita doble conteo).
  const pathBadges: Record<string, number> = {};
  alertasData.forEach((a: any) => {
    if (a.link && a.link !== '/comunicacion') {
      pathBadges[a.link] = (pathBadges[a.link] || 0) + (a.count || 1);
    }
  });

  const NAV_ITEMS: NavItem[] = [
    { path: '/superadmin', label: 'Gestión Colegios', icon: Building2, roles: ['superadmin'] },
    { path: '/dashboard', label: 'Panel Principal', icon: LayoutDashboard, roles: ['direccion', 'coordinador', 'profesor', 'psicologia', 'secretaria'] },

    // ─── ACADÉMICO ───
    { path: '/academico', label: 'Calificaciones', icon: BookOpen, roles: ['direccion', 'coordinador', 'profesor'], section: 'Académico' },
    { path: '/calificaciones-general', label: 'Notas por Período', icon: BarChart3, roles: ['direccion', 'coordinador'], section: 'Académico' },
    { path: '/cuadro-honor', label: 'Cuadro de Honor', icon: Award, roles: ['direccion', 'coordinador', 'secretaria'], section: 'Académico' },
    { path: '/recuperaciones-primaria', label: 'Recuperaciones (Primaria)', icon: AlertTriangle, roles: ['direccion', 'coordinador', 'secretaria', 'profesor'], section: 'Académico' },
    { path: '/evaluaciones-extra', label: 'Evaluaciones Extra', icon: AlertTriangle, roles: ['direccion', 'coordinador', 'profesor'], section: 'Académico' },
    { path: '/items-completivos', label: 'Detalle de evaluaciones (Registro)', icon: ClipboardCheck, roles: ['direccion', 'coordinador', 'profesor'], section: 'Académico' },
    { path: '/asistencia', label: 'Asistencia', icon: CalendarCheck, roles: ['direccion', 'coordinador', 'profesor'], section: 'Académico' },
    { path: '/boletines', label: 'Boletines', icon: FileBarChart, roles: ['direccion', 'coordinador', 'secretaria'], section: 'Académico' },
    { path: '/registro-escolar', label: 'Registro Escolar', icon: FileBarChart, roles: ['direccion', 'coordinador', 'profesor', 'secretaria'], modulo: 'registro_escolar', section: 'Académico' },

    // ─── PERSONAS ───
    { path: '/estudiantes', label: 'Estudiantes', icon: GraduationCap, roles: ['direccion', 'coordinador', 'profesor', 'secretaria'], section: 'Personas' },
    { path: '/eval-interna', label: 'Eval. de Estudiantes', icon: ClipboardCheck, roles: ['direccion', 'coordinador', 'profesor'], modulo: 'eval_interna', section: 'Personas' },
    { path: '/psicologia', label: 'Psicología', icon: Brain, roles: ['direccion', 'coordinador', 'profesor', 'psicologia'], modulo: 'psicologia', section: 'Personas' },
    { path: '/reportes', label: 'Reportes Conducta', icon: FileBarChart, roles: ['direccion', 'coordinador', 'profesor', 'psicologia', 'secretaria'], modulo: 'reportes_conducta', section: 'Personas' },

    // ─── PLANIFICACIÓN ───
    { path: '/horarios', label: 'Horarios', icon: Clock, roles: ['direccion', 'coordinador', 'profesor'], section: 'Planificación' },
    { path: '/asignaciones', label: 'Asignaciones', icon: Users, roles: ['direccion'], section: 'Planificación' },
    { path: '/evaluaciones', label: 'Eval. Profesores', icon: ClipboardCheck, roles: ['direccion', 'coordinador'], modulo: 'eval_profesores', section: 'Planificación' },

    // ─── COMUNICACIÓN ───
    { path: '/comunicacion', label: 'Mensajes internos', icon: MessageSquare, roles: ['direccion', 'coordinador', 'profesor', 'psicologia', 'secretaria'], badge: mensajesNoLeidos, section: 'Comunicación' },
    { path: '/whatsapp', label: 'WhatsApp', icon: MessageSquare, roles: ['direccion', 'coordinador', 'profesor', 'psicologia'], modulo: 'whatsapp', section: 'Comunicación' },
    { path: '/notas', label: 'Mis Notas', icon: StickyNote, roles: ['direccion', 'coordinador', 'profesor', 'psicologia', 'secretaria'], section: 'Comunicación' },

    // ─── ANÁLISIS ───
    { path: '/estadisticas', label: 'Estadísticas', icon: BarChart3, roles: ['direccion', 'coordinador', 'psicologia'], section: 'Análisis' },

    // ─── ADMINISTRACIÓN ───
    { path: '/usuarios', label: 'Usuarios', icon: Users, roles: ['direccion'], section: 'Administración' },
    { path: '/configuracion', label: 'Configuración', icon: Settings, roles: ['direccion'], section: 'Administración' },
    { path: '/cierre-ano', label: 'Cierre de Año', icon: Calendar, roles: ['direccion'], section: 'Administración' },
    { path: '/auditoria', label: 'Auditoría', icon: Shield, roles: ['direccion'], section: 'Administración' },
  ];

  const filteredNavItems = NAV_ITEMS.filter(item => {
    if (!user || !item.roles.includes(user.role)) return false;

    // Verificar si el módulo está habilitado
    if (item.modulo && modulosConfig) {
      const mc = modulosConfig;
      if (item.modulo === 'whatsapp') {
        if (!mc.modulo_whatsapp) return false;
        if (mc.whatsapp_solo_direccion && user.role !== 'direccion') return false;
      }
      if (item.modulo === 'psicologia' && !mc.modulo_psicologia) return false;
      if (item.modulo === 'eval_profesores' && !mc.modulo_eval_profesores) return false;
      if (item.modulo === 'eval_interna' && !mc.modulo_eval_interna) return false;
      if (item.modulo === 'registro_escolar' && !mc.modulo_registro_escolar) return false;
      if (item.modulo === 'reportes_conducta' && !mc.modulo_reportes_conducta) return false;
    }
    return true;
  });

  // v2.14: si la ruta activa está dentro de una sección cerrada, abrirla
  // automáticamente para que el item activo siempre sea visible.
  useEffect(() => {
    if (!esMenuColapsable) return;
    const activo = filteredNavItems.find(i =>
      location.pathname === i.path || location.pathname.startsWith(i.path + '/')
    );
    if (activo?.section && !seccionesAbiertas.includes(activo.section)) {
      toggleSeccion(activo.section);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, esMenuColapsable]);

  const getRoleBadge = (role: string) => {
    const badges: Record<string, { label: string; color: string }> = {
      'superadmin': { label: 'SUPER', color: 'bg-red-900 text-red-200' },
      'direccion': { label: 'ADMIN', color: 'bg-blue-900 text-blue-200' },
      'coordinador': { label: 'COORD', color: 'bg-emerald-900 text-emerald-200' },
      'profesor': { label: 'PROF', color: 'bg-amber-900 text-amber-200' },
      'psicologia': { label: 'PSIC', color: 'bg-pink-900 text-pink-200' },
      'secretaria': { label: 'SEC', color: 'bg-slate-700 text-slate-200' }
    };
    return badges[role] || { label: role, color: 'bg-gray-700 text-gray-200' };
  };

  // v2.14: accesos rápidos del sidebar (solo dirección/coordinación).
  // Se construyen desde filteredNavItems para respetar roles y módulos
  // contratados (si Reportes está apagado, el atajo no aparece).
  const ATAJOS_DEF = [
    { path: '/estudiantes', label: 'Estudiantes', icon: GraduationCap },
    { path: '/academico', label: 'Calificar', icon: BookOpen },
    { path: '/reportes', label: 'Reportes', icon: FileText },
    { path: '/boletines', label: 'Boletines', icon: FileBarChart },
  ];
  const atajos = esMenuColapsable
    ? ATAJOS_DEF.filter(a => filteredNavItems.some(i => i.path === a.path))
    : [];

  const badgeDe = (item: NavItem): number => {
    if (item.badge && item.badge > 0) return item.badge;
    return pathBadges[item.path] || 0;
  };

  const renderNavLink = (item: NavItem) => {
    const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/');
    const Icon = item.icon;
    const badge = badgeDe(item);
    return (
      <Link
        key={item.path}
        to={item.path}
        onClick={() => setMobileMenuOpen(false)}
        className={`flex items-center px-3 py-2.5 mb-1 rounded-lg transition-all group ${
          isActive
            ? 'bg-blue-600/90 text-white shadow-md shadow-blue-600/20'
            : 'text-slate-300 hover:bg-slate-800 hover:text-white'
        }`}
      >
        <Icon size={20} className="min-w-[20px]" />
        {isSidebarOpen && (
          <>
            <span className="ml-3 text-sm font-medium">{item.label}</span>
            {badge > 0 && (
              <span className="ml-auto bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                {badge}
              </span>
            )}
          </>
        )}
      </Link>
    );
  };

  // v2.14: navegación agrupada por secciones colapsables (dirección/coordinación).
  // Los items sin section (Panel Principal) van al tope, planos.
  const renderNavColapsable = () => {
    const sinSeccion = filteredNavItems.filter(i => !i.section);
    const secciones: string[] = [];
    filteredNavItems.forEach(i => {
      if (i.section && !secciones.includes(i.section)) secciones.push(i.section);
    });
    return (
      <>
        {sinSeccion.map(renderNavLink)}
        {secciones.map(seccion => {
          const items = filteredNavItems.filter(i => i.section === seccion);
          const abierta = seccionesAbiertas.includes(seccion);
          const badgeSeccion = items.reduce((acc, i) => acc + badgeDe(i), 0);
          return (
            <div key={seccion}>
              <button
                onClick={() => toggleSeccion(seccion)}
                className="w-full flex items-center justify-between px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 transition-colors"
              >
                <span className="flex items-center gap-2">
                  {seccion}
                  {!abierta && badgeSeccion > 0 && (
                    <span className="bg-red-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full normal-case">
                      {badgeSeccion}
                    </span>
                  )}
                </span>
                {abierta ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {abierta && items.map(renderNavLink)}
            </div>
          );
        })}
      </>
    );
  };

  // Navegación plana con mini-headers (profesor, secretaría, psicología —
  // menús cortos donde colapsar estorbaría). Comportamiento v2.13.2 intacto.
  const renderNavPlano = () => (
    <>
      {filteredNavItems.map((item, idx) => {
        const prevItem = idx > 0 ? filteredNavItems[idx - 1] : null;
        const showSectionHeader = isSidebarOpen && item.section && item.section !== prevItem?.section;
        return (
          <div key={item.path}>
            {showSectionHeader && (
              <div className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                {item.section}
              </div>
            )}
            {renderNavLink(item)}
          </div>
        );
      })}
    </>
  );

  const SidebarContent = () => (
    <>
      {/* Logo Header */}
      <div className="p-4 flex items-center justify-between border-b border-slate-800">
        {isSidebarOpen && (
          <span className="font-extrabold text-xl tracking-tight bg-gradient-to-r from-blue-400 to-blue-300 bg-clip-text text-transparent">Educa One</span>
        )}
        <button
          onClick={() => setSidebarOpen(!isSidebarOpen)}
          className="p-1.5 hover:bg-slate-800 rounded-lg transition-colors hidden lg:block"
        >
          {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* v2.14: Accesos rápidos (solo dirección/coordinación, sidebar expandido) */}
      {isSidebarOpen && atajos.length > 0 && (
        <div className="px-3 pt-3">
          <div className="grid grid-cols-4 gap-1.5">
            {atajos.map(a => {
              const Icon = a.icon;
              const badge = pathBadges[a.path] || 0;
              const isActive = location.pathname === a.path || location.pathname.startsWith(a.path + '/');
              return (
                <Link
                  key={a.path}
                  to={a.path}
                  onClick={() => setMobileMenuOpen(false)}
                  title={a.label}
                  className={`relative flex flex-col items-center justify-center py-2 rounded-lg transition-colors ${
                    isActive ? 'bg-blue-600/90 text-white' : 'bg-slate-800/70 text-slate-300 hover:bg-slate-700 hover:text-white'
                  }`}
                >
                  <Icon size={17} />
                  <span className="text-[9px] mt-1 font-medium leading-none">{a.label}</span>
                  {badge > 0 && (
                    <span className="absolute -top-1 -right-1 min-w-[16px] h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center px-1">
                      {badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 mt-2 overflow-y-auto overflow-x-hidden px-2 sidebar-scroll">
        {isSidebarOpen && esMenuColapsable ? renderNavColapsable() : renderNavPlano()}
      </nav>

      {/* User Section */}
      <div className="p-3 border-t border-slate-800 bg-slate-950">
        {isSidebarOpen && (
          <div className="mb-3 px-2">
            <p className="text-[10px] text-slate-500 uppercase font-semibold tracking-wider">Usuario</p>
            <p className="text-sm font-medium text-white truncate mt-1">{user?.nombre} {user?.apellido}</p>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${getRoleBadge(user?.role || '').color}`}>
              {getRoleBadge(user?.role || '').label}
            </span>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="flex items-center w-full px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
        >
          <LogOut size={20} />
          {isSidebarOpen && <span className="ml-3 text-sm">Cerrar Sesión</span>}
        </button>
      </div>
    </>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Sidebar Desktop */}
      <aside
        className={`${isSidebarOpen ? 'w-64' : 'w-20'} bg-gradient-to-b from-slate-900 via-slate-900 to-slate-950 text-white transition-all duration-300 flex-col z-50 hidden lg:flex`}
      >
        <SidebarContent />
      </aside>

      {/* Mobile Overlay */}
      {mobileMenuOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Sidebar */}
      <aside
        className={`lg:hidden fixed left-0 top-0 h-full w-64 bg-gradient-to-b from-slate-900 via-slate-900 to-slate-950 text-white z-50 transform transition-transform duration-300 flex flex-col ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <SidebarContent />
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 bg-white border-b border-slate-200/80 flex items-center justify-between px-4 lg:px-8 z-10 shrink-0 shadow-sm">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <Menu size={24} />
            </button>
            <div>
              <h1 className="text-lg font-semibold text-slate-800">{config?.nombre || 'Educa One'}</h1>
              {config?.distrito && (
                <p className="text-xs text-slate-500">{config.distrito}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <button onClick={() => setShowNotifPanel(!showNotifPanel)} className="relative p-2 text-slate-400 hover:text-blue-600 hover:bg-slate-100 rounded-lg transition-colors">
                <Bell size={22} />
                {(notifNoLeidas + mensajesNoLeidos) > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] bg-red-500 rounded-full border-2 border-white flex items-center justify-center text-[10px] text-white font-bold">
                    {notifNoLeidas + mensajesNoLeidos}
                  </span>
                )}
              </button>
              {showNotifPanel && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowNotifPanel(false)}></div>
                  <div className="absolute right-0 top-12 w-80 max-h-[400px] bg-white rounded-xl shadow-xl border z-50 overflow-hidden">
                    <div className="p-3 border-b bg-gray-50 flex items-center justify-between">
                      <h3 className="font-bold text-sm text-gray-800">Notificaciones</h3>
                      {notifNoLeidas > 0 && (
                        <button onClick={marcarTodasLeidas} className="text-[10px] text-blue-600 hover:underline">Marcar todas leídas</button>
                      )}
                    </div>
                    <div className="overflow-y-auto max-h-[320px]">
                      {notificaciones.length === 0 ? (
                        <div className="p-6 text-center text-gray-400 text-sm">Sin notificaciones</div>
                      ) : (
                        notificaciones.map((n: any) => (
                          <div key={n.id} onClick={() => { marcarNotifLeida(n.id); if (n.link) navigate(n.link); setShowNotifPanel(false); }}
                            className={`p-3 border-b cursor-pointer hover:bg-gray-50 transition-colors ${!n.leida ? 'bg-blue-50' : ''}`}>
                            <div className="flex justify-between items-start">
                              <p className={`text-xs ${!n.leida ? 'font-bold text-gray-800' : 'text-gray-600'}`}>{n.titulo}</p>
                              {!n.leida && <span className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0 mt-1"></span>}
                            </div>
                            {n.mensaje && <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-2">{n.mensaje}</p>}
                            <p className="text-[10px] text-gray-400 mt-1">{n.tiempo_relativo}</p>
                          </div>
                        ))
                      )}
                    </div>
                    {mensajesNoLeidos > 0 && (
                      <div onClick={() => { navigate('/comunicacion'); setShowNotifPanel(false); }} className="p-2 border-t bg-gray-50 text-center cursor-pointer hover:bg-gray-100">
                        <p className="text-xs text-blue-600 font-medium">📬 {mensajesNoLeidos} mensaje(s) sin leer</p>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
            <div className="h-9 w-9 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-sm">
              {user?.nombre?.charAt(0)}{user?.apellido?.charAt(0)}
            </div>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 lg:p-8">
          {/* Impersonation Banner */}
          {typeof window !== 'undefined' && localStorage.getItem('superadmin_token') && (
            <div className="mb-4 flex items-center justify-between gap-3 p-3 bg-indigo-50 border border-indigo-200 rounded-xl">
              <p className="text-indigo-700 text-sm font-medium">
                👁 Estás viendo este colegio como Super Admin
              </p>
              <button
                onClick={() => {
                  const saToken = localStorage.getItem('superadmin_token');
                  const saUser = localStorage.getItem('superadmin_user');
                  if (saToken) {
                    localStorage.setItem('token', saToken);
                    if (saUser) localStorage.setItem('user', saUser);
                    localStorage.removeItem('superadmin_token');
                    localStorage.removeItem('superadmin_user');
                    window.location.href = '/superadmin';
                  }
                }}
                className="px-4 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium whitespace-nowrap"
              >
                ← Volver a Super Admin
              </button>
            </div>
          )}
          {children}
        </div>
      </main>
    </div>
  );
};

export default MainLayout;
