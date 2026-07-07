import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import { MainLayout } from './components/layout';

// Pages
import { LoginPage } from './pages/login';
import { DashboardPage } from './pages/dashboard';
import { EstudiantesPage } from './pages/estudiantes';
import { AcademicoPage } from './pages/academico';
import { FichaEstudianteAsignatura } from './pages/academico/FichaEstudianteAsignatura';
import { AsistenciaPage } from './pages/asistencia';
import { ReportesPage } from './pages/reportes';
import { PsicologiaPage } from './pages/psicologia';
import { UsuariosPage } from './pages/usuarios';
import { ConfiguracionPage } from './pages/configuracion';
import { HorariosPage } from './pages/horarios';
import { AsignacionesPage } from './pages/asignaciones';
import { ComunicacionPage } from './pages/comunicacion';
import { BoletinesPage } from './pages/boletines';
import { PerfilPage } from './pages/perfil';
import { AuditoriaPage } from './pages/auditoria';
import { EstadisticasPage } from './pages/estadisticas';
import { WhatsAppPage } from './pages/whatsapp';
import { CierreAnoPage } from './pages/cierre-ano';
import { RegistroEscolarPage } from './pages/registro-escolar';
import { CalificacionesGeneralPage } from './pages/calificaciones-general';
import { CuadroHonorPage } from './pages/cuadro-honor';
import { EvaluacionesPage } from './pages/evaluaciones';
import { NotasPage } from './pages/notas';
import { EvalInternaPage } from './pages/eval-interna';
import { ItemsCompletivosPage } from './pages/items-completivos';
import { SuperAdminPage } from './pages/superadmin';
import { CambiarPasswordPage } from './pages/cambiar-password';
import { EvaluacionesExtraPage } from './pages/evaluaciones-extra';

const ProtectedRoute = ({ children, roles }: { children: React.ReactNode; roles?: string[] }) => {
  const { user, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (roles && !roles.includes(user.role)) {
    // Superadmin goes to their panel, others to dashboard
    return <Navigate to={user.role === 'superadmin' ? '/superadmin' : '/dashboard'} replace />;
  }
  
  return <>{children}</>;
};

export const AppRouter = () => {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/cambiar-password" element={<CambiarPasswordPage />} />
        
        <Route path="/dashboard" element={
          <ProtectedRoute><MainLayout><DashboardPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/estudiantes" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor', 'secretaria']}><MainLayout><EstudiantesPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/academico" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><AcademicoPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/academico/estudiante/:estudianteId/asignatura/:asignaturaId" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><FichaEstudianteAsignatura /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/evaluaciones-extra" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><EvaluacionesExtraPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/items-completivos" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><ItemsCompletivosPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/boletines" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'secretaria']}><MainLayout><BoletinesPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/asistencia" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><AsistenciaPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/horarios" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><HorariosPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/asignaciones" element={
          <ProtectedRoute roles={['direccion']}><MainLayout><AsignacionesPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/reportes" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor', 'secretaria']}><MainLayout><ReportesPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/psicologia" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor', 'psicologia']}><MainLayout><PsicologiaPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/comunicacion" element={
          <ProtectedRoute><MainLayout><ComunicacionPage /></MainLayout></ProtectedRoute>
        } />
        <Route path="/comunicados" element={
          <ProtectedRoute><MainLayout><ComunicacionPage /></MainLayout></ProtectedRoute>
        } />
        <Route path="/mensajes" element={
          <ProtectedRoute><MainLayout><ComunicacionPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/usuarios" element={
          <ProtectedRoute roles={['direccion']}><MainLayout><UsuariosPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/configuracion" element={
          <ProtectedRoute roles={['direccion']}><MainLayout><ConfiguracionPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/auditoria" element={
          <ProtectedRoute roles={['direccion']}><MainLayout><AuditoriaPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/registro-escolar" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor', 'secretaria']}><MainLayout><RegistroEscolarPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/calificaciones-general" element={
          <ProtectedRoute roles={['direccion', 'coordinador']}><MainLayout><CalificacionesGeneralPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/cuadro-honor" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'secretaria']}><MainLayout><CuadroHonorPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/estadisticas" element={
          <ProtectedRoute roles={['direccion', 'coordinador']}><MainLayout><EstadisticasPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/whatsapp" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><WhatsAppPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/evaluaciones" element={
          <ProtectedRoute roles={['direccion', 'coordinador']}><MainLayout><EvaluacionesPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/cierre-ano" element={
          <ProtectedRoute roles={['direccion']}><MainLayout><CierreAnoPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/eval-interna" element={
          <ProtectedRoute roles={['direccion', 'coordinador', 'profesor']}><MainLayout><EvalInternaPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/superadmin" element={
          <ProtectedRoute roles={['superadmin']}><MainLayout><SuperAdminPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/notas" element={
          <ProtectedRoute><MainLayout><NotasPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/perfil" element={
          <ProtectedRoute><MainLayout><PerfilPage /></MainLayout></ProtectedRoute>
        } />
        
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;
