import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../services/api';

/**
 * Página de cambio de contraseña.
 * 
 * Aparece automáticamente cuando el backend devuelve HTTP 423 (must_change_password=True)
 * en cualquier endpoint. El interceptor de api.ts redirige aquí.
 * 
 * También se puede acceder voluntariamente desde el perfil del usuario.
 */
export const CambiarPasswordPage = () => {
  const navigate = useNavigate();
  const [passwordActual, setPasswordActual] = useState('');
  const [passwordNuevo, setPasswordNuevo] = useState('');
  const [passwordConfirmar, setPasswordConfirmar] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exito, setExito] = useState(false);

  useEffect(() => {
    // Si llegó aquí sin estar logueado, mandar a login
    const token = localStorage.getItem('token') || localStorage.getItem('superadmin_token');
    if (!token) {
      navigate('/login');
    }
  }, [navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (passwordNuevo.length < 8) {
      setError('La contraseña nueva debe tener al menos 8 caracteres.');
      return;
    }
    if (passwordNuevo !== passwordConfirmar) {
      setError('La confirmación no coincide con la contraseña nueva.');
      return;
    }
    if (passwordNuevo === passwordActual) {
      setError('La contraseña nueva debe ser distinta a la actual.');
      return;
    }
    if (!/[A-Z]/.test(passwordNuevo) || !/[a-z]/.test(passwordNuevo) || !/\d/.test(passwordNuevo)) {
      setError('La contraseña debe incluir mayúsculas, minúsculas y al menos un número.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/cambiar-password', {
        password_actual: passwordActual,
        password_nuevo: passwordNuevo,
      });
      setExito(true);
      setTimeout(() => {
        // Después del cambio, redirigir según rol
        const userJson = localStorage.getItem('user') || localStorage.getItem('superadmin_user');
        let destino = '/dashboard';
        if (userJson) {
          try {
            const u = JSON.parse(userJson);
            destino = u.role === 'superadmin' ? '/superadmin' : '/dashboard';
          } catch {}
        }
        navigate(destino);
      }, 1200);
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.error ||
        err.response?.data?.message ||
        'No se pudo cambiar la contraseña. Verificá la actual.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-700 px-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-100 mb-3">
            <svg className="w-8 h-8 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 15v2m0 0v2m0-2h2m-2 0h-2m6-6V9a4 4 0 10-8 0v2m-2 0h12a2 2 0 012 2v7a2 2 0 01-2 2H6a2 2 0 01-2-2v-7a2 2 0 012-2z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Cambiar contraseña</h1>
          <p className="text-sm text-slate-600 mt-2">
            Por seguridad, debés cambiar tu contraseña antes de continuar usando el sistema.
          </p>
        </div>

        {exito ? (
          <div className="text-center py-6">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-green-100 mb-3">
              <svg className="w-7 h-7 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-slate-700 font-medium">Contraseña actualizada</p>
            <p className="text-sm text-slate-500 mt-1">Redirigiendo...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Contraseña actual
              </label>
              <input
                type="password"
                value={passwordActual}
                onChange={(e) => setPasswordActual(e.target.value)}
                required
                autoFocus
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="La que te dieron / la actual"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Contraseña nueva
              </label>
              <input
                type="password"
                value={passwordNuevo}
                onChange={(e) => setPasswordNuevo(e.target.value)}
                required
                minLength={8}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Mínimo 8 caracteres con mayúsculas, minúsculas y números"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Confirmá la nueva
              </label>
              <input
                type="password"
                value={passwordConfirmar}
                onChange={(e) => setPasswordConfirmar(e.target.value)}
                required
                minLength={8}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Repetir la contraseña nueva"
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-2.5 rounded-lg transition"
            >
              {loading ? 'Cambiando...' : 'Cambiar contraseña'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default CambiarPasswordPage;
