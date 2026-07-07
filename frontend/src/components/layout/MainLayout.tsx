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
  Award
} from 'lucide-react';

interface NavItem {
  path: string;
  label: string;
  icon: any;
  roles: string[];
  badge?: number;
  modulo?: string; // Si depende de un módulo habilitado
  section?: string; // v2.13.2: agrupación visual en sidebar (Opción 4 plana con separadores)
}

interface ColegioConfig {
  nombre: string;
  logo: string | null;
  distrito?: string;
}

interface MainLayoutProps {
  children: ReactNode;
}

export const MainLayout = ({ children }: MainLayoutProps) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [config, setConfig] = useState<ColegioConfig | null>(null);
  const [mensajesNoLeidos, setMensajesNoLeidos] = useState(0);
  const [comunicadosNoLeidos, setComunicadosNoLeidos] = useState(0);
  const [alertasCount, setAlertasCount] = useState(0);
  const [isSidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [modulosConfig, setModulosConfig] = useState<any>(null);
  const [notificaciones, setNotificaciones] = useState<any[]>([]);
  const [notifNoLeidas, setNotifNoLeidas] = useState(0);
  const [showNotifPanel, setShowNotifPanel] = useState(false);

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

  // v2.13.2: cada item lleva una `section` que se renderiza como mini-header
  // de separación visual en el sidebar. Items sin section (Panel Principal,
  // Gestión Colegios) se renderizan al tope sin header encima.
  const NAV_ITEMS: NavItem[] = [
    { path: '/superadmin', label: 'Gestión Colegios', icon: Building2, roles: ['superadmin'] },
    { path: '/dashboard', label: 'Panel Principal', icon: LayoutDashboard, roles: ['direccion', 'coordinador', 'profesor', 'psicologia', 'secretaria'] },
    
    // ─── ACADÉMICO ───
    { path: '/academico', label: 'Calificaciones', icon: BookOpen, roles: ['direccion', 'coordinador', 'profesor'], section: 'Académico' },
    { path: '/calificaciones-general', label: 'Notas por Período', icon: BarChart3, roles: ['direccion', 'coordinador'], section: 'Académico' },
    { path: '/cuadro-honor', label: 'Cuadro de Honor', icon: Award, roles: ['direccion', 'coordinador', 'secretaria'], section: 'Académico' },
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

      {/* Navigation */}
      <nav className="flex-1 mt-2 overflow-y-auto overflow-x-hidden px-2 sidebar-scroll">
        {filteredNavItems.map((item, idx) => {
          const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/');
          const Icon = item.icon;
          
          // v2.13.2: insertar mini-header cuando cambia la sección
          // Solo cuando el sidebar está expandido (en colapsado los headers estorbarían).
          const prevItem = idx > 0 ? filteredNavItems[idx - 1] : null;
          const showSectionHeader = isSidebarOpen && item.section && item.section !== prevItem?.section;
          
          return (
            <div key={item.path}>
              {showSectionHeader && (
                <div className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  {item.section}
                </div>
              )}
              <Link
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
                    {item.badge && item.badge > 0 && (
                      <span className="ml-auto bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                        {item.badge}
                      </span>
                    )}
                  </>
                )}
              </Link>
            </div>
          );
        })}
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
