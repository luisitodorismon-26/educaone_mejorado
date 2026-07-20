import axios from 'axios';

// Vite expone import.meta.env.PROD pero TypeScript no siempre lo reconoce
// según la versión de @types/vite. Casteamos a any para evitar el error TS.
const env = import.meta.env as any;
// v2.13.23: NO hardcodear puerto. En desarrollo usamos rutas relativas
// ('/api/...') que el proxy de vite (vite.config.ts) redirige al backend.
// Así el ÚNICO lugar que define el puerto del backend es vite.config.ts.
// En producción, VITE_API_URL puede definir el dominio del backend.
const API_URL = env.VITE_API_URL || '';

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json'
  }
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // v2.15 F1: lente de nivel — el switch de dirección guarda su elección en
  // localStorage y TODAS las peticiones la mandan en X-Nivel. El backend la
  // aplica solo a usuarios sin nivel fijo (dirección); para coordinadores el
  // lente fijo manda y este header se ignora. Un solo punto: las páginas ni
  // se enteran de que existe la división.
  const nivelVista = localStorage.getItem('educaone_nivel_vista');
  if (nivelVista === 'primaria' || nivelVista === 'secundaria') {
    config.headers['X-Nivel'] = nivelVista;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      localStorage.removeItem('superadmin_token');
      localStorage.removeItem('superadmin_user');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    // 423 Locked = el usuario tiene must_change_password=True y debe cambiar
    // su contraseña antes de continuar usando el sistema. Redirigimos a la
    // página de cambio de password (excepto si ya está ahí, para evitar loop).
    if (error.response?.status === 423) {
      if (window.location.pathname !== '/cambiar-password' && window.location.pathname !== '/login') {
        window.location.href = '/cambiar-password';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
