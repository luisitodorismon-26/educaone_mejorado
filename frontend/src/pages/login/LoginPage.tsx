import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { GraduationCap, Eye, EyeOff, Loader2 } from 'lucide-react';

export const LoginPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      // Redirect superadmin to their panel
      const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
      if (storedUser.role === 'superadmin') {
        navigate('/superadmin');
      } else {
        navigate('/dashboard');
      }
    } catch (e: any) {
      setError(e.response?.data?.error || 'Error al iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Panel izquierdo - Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 relative overflow-hidden">
        {/* Pattern decorativo */}
        <div className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`
          }}
        />
        {/* Glow decorativo */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/3 w-64 h-64 bg-indigo-500/8 rounded-full blur-3xl" />

        <div className="relative z-10 flex flex-col justify-center items-center w-full px-16">
          <div className="w-20 h-20 bg-white/10 backdrop-blur-sm rounded-2xl flex items-center justify-center mb-8 ring-1 ring-white/10">
            <GraduationCap size={40} className="text-blue-400" />
          </div>
          <h1 className="text-4xl font-extrabold text-white tracking-tight mb-3">
            Educa One
          </h1>
          <p className="text-blue-300/70 text-lg font-medium mb-12">
            Plataforma Educativa Integral
          </p>

          <div className="space-y-6 max-w-sm">
            {[
              { icon: '📊', text: 'Gestión académica completa' },
              { icon: '📋', text: 'Calificaciones y boletines MINERD' },
              { icon: '👥', text: 'Control de asistencia y conducta' },
              { icon: '🔒', text: 'Seguridad y auditoría integrada' },
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-4 text-slate-300/80">
                <span className="text-xl w-8 text-center">{item.icon}</span>
                <span className="text-sm font-medium">{item.text}</span>
              </div>
            ))}
          </div>

          <div className="mt-16 text-xs text-slate-500 text-center">
            Sistema de Gestión Escolar
          </div>
        </div>
      </div>

      {/* Panel derecho - Formulario */}
      <div className="flex-1 flex items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-sm">
          {/* Logo mobile */}
          <div className="lg:hidden text-center mb-10">
            <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-600/20">
              <GraduationCap size={32} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Educa One</h1>
            <p className="text-slate-500 text-sm mt-1">Plataforma Educativa Integral</p>
          </div>

          <div className="hidden lg:block mb-10">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
              Bienvenido
            </h2>
            <p className="text-slate-500 text-sm mt-1.5">
              Ingresa tus credenciales para acceder al sistema
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl mb-6 text-sm font-medium flex items-start gap-2 animate-fade-in">
              <span className="text-red-500 mt-0.5">⚠</span>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                Usuario
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full px-4 py-3 bg-white border border-slate-200 rounded-xl text-sm
                           focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none
                           transition-all duration-150 hover:border-slate-300
                           placeholder:text-slate-400"
                placeholder="Ingresa tu usuario"
                autoComplete="username"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                Contraseña
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full px-4 py-3 pr-11 bg-white border border-slate-200 rounded-xl text-sm
                             focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none
                             transition-all duration-150 hover:border-slate-300
                             placeholder:text-slate-400"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-blue-600 text-white rounded-xl font-semibold text-sm
                         hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50
                         transition-all duration-150 mt-2
                         shadow-lg shadow-blue-600/20 hover:shadow-blue-600/30
                         focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:ring-offset-2
                         flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  Iniciando...
                </>
              ) : (
                'Iniciar Sesión'
              )}
            </button>
          </form>

          <p className="text-center text-xs text-slate-400 mt-8">
            Educa One &copy; {new Date().getFullYear()} &mdash; Todos los derechos reservados
          </p>
        </div>
      </div>
    </div>
  );
};
export default LoginPage;
