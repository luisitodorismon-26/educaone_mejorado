import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import api from '../services/api';

interface User {
  id: number;
  username: string;
  nombre: string;
  apellido: string;
  email: string;
  telefono: string;
  role: string;
  tanda_id: number | null;
  tanda: string | null;
  activo: boolean;
  nombre_completo: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setLoading(false);
      return;
    }
    
    try {
      const res = await api.get('/auth/me');
      setUser(res.data);
    } catch {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (username: string, password: string) => {
    const res = await api.post('/auth/login', { username, password });
    const { user: userData, token } = res.data;
    // Limpiar tokens de impersonación al hacer login nuevo
    localStorage.removeItem('superadmin_token');
    localStorage.removeItem('superadmin_user');
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(userData));
    // Invalidar cache de niveles — el nuevo usuario puede ser de un colegio
    // distinto con plan diferente (solo primaria, mixto, etc.)
    try {
      const { invalidateNivelesCache } = await import('../hooks/useNivelesActivos');
      invalidateNivelesCache();
    } catch {}
    setUser(userData);
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Ignorar errores
    } finally {
      // Limpiar TODO — incluyendo tokens de impersonación
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      localStorage.removeItem('superadmin_token');
      localStorage.removeItem('superadmin_user');
      // Invalidar cache de niveles para que el siguiente login lo recargue limpio
      try {
        const { invalidateNivelesCache } = await import('../hooks/useNivelesActivos');
        invalidateNivelesCache();
      } catch {}
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
