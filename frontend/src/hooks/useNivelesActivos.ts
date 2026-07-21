import { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export type Nivel = 'secundaria' | 'primaria' | 'inicial';

interface NivelesState {
  secundaria: boolean;
  primaria: boolean;
  inicial: boolean;
  loading: boolean;
  /** Lista de niveles activos, en orden */
  activos: Nivel[];
  /** Cuántos niveles están activos (si es 1, no se muestran tabs) */
  count: number;
  /** Nivel por defecto recomendado (primero activo o 'secundaria') */
  defaultNivel: Nivel;
}

// Cache en memoria para evitar llamadas repetidas (config rara vez cambia).
// v2.17: la clave incluye usuario+rol — el resultado del PROFESOR es personal
// (sus asignaciones) y no debe reusarse si otra persona inicia sesión.
let cachedNiveles: Omit<NivelesState, 'loading'> | null = null;
let cachedKey: string | null = null;
let cachedPromise: Promise<void> | null = null;

export const invalidateNivelesCache = () => {
  cachedNiveles = null;
  cachedKey = null;
  cachedPromise = null;
};

const loadNiveles = async (esProfesor: boolean): Promise<Omit<NivelesState, 'loading'>> => {
  // Leer config de módulos (estado EFECTIVO: plan AND uso, desde backend)
  let d: any = {};
  try {
    const cfgRes = await api.get('/configuracion/modulos');
    d = cfgRes.data || {};
  } catch {
    d = {};
  }

  const secundariaPlan = d.modulo_secundaria === true;
  const primariaPlan = d.modulo_primaria === true;
  const inicialPlan = d.modulo_inicial === true;

  let activos: Nivel[] = [];
  if (secundariaPlan) activos.push('secundaria');
  if (primariaPlan) activos.push('primaria');
  if (inicialPlan) activos.push('inicial');

  // v2.17: para el PROFESOR, sus pestañas salen de SUS CURSOS ASIGNADOS
  // (/cursos ya viene filtrado por asignaciones en el backend). Un profesor
  // que no trabaja primaria NO ve la pestaña Primaria; si le asignan cursos
  // de primaria (caso del profesor de inglés mixto), la pestaña aparece sola.
  // Con 1 solo nivel, NivelTabs se oculta por completo (count <= 1).
  if (esProfesor) {
    try {
      const cursosRes = await api.get('/cursos');
      const misNiveles = new Set<string>(
        (cursosRes.data || []).map((c: any) => c.nivel || 'secundaria')
      );
      const filtrados = activos.filter(n => misNiveles.has(n));
      // Si aún no tiene asignaciones, no forzamos pestañas de nada
      activos = filtrados;
    } catch {
      // Si /cursos falla, conservar los niveles del plan (comportamiento previo)
    }
  }

  // Si ninguno activo (config rota o colegio nuevo sin plan), default a
  // secundaria para que la UI de dirección no quede en blanco. Para el
  // profesor SIN asignaciones se respeta la lista vacía (sin pestañas).
  if (activos.length === 0 && !esProfesor) activos.push('secundaria');

  return {
    secundaria: activos.includes('secundaria'),
    primaria: activos.includes('primaria'),
    inicial: activos.includes('inicial'),
    activos,
    count: activos.length,
    defaultNivel: activos[0] || 'secundaria',
  };
};

/**
 * Hook que devuelve qué niveles educativos aplican al usuario actual.
 * - Dirección/coordinación/secretaría/psicología: los niveles del PLAN del colegio.
 * - PROFESOR (v2.17): los niveles de SUS cursos asignados.
 * Usa cache en memoria por usuario — 1 llamada por sesión.
 *
 * IMPORTANTE: el estado inicial mientras carga es neutro (loading=true, sin
 * defaults sesgados a secundaria). Los componentes que filtran por nivel deben
 * verificar `loading` antes de hacer el filtrado, o esperar la primera carga.
 */
export const useNivelesActivos = (): NivelesState => {
  const { user } = useAuth();
  const claveUsuario = `${user?.id || 'anon'}-${user?.role || ''}`;

  const [state, setState] = useState<NivelesState>(() => {
    if (cachedNiveles && cachedKey === claveUsuario) {
      return { ...cachedNiveles, loading: false };
    }
    return {
      secundaria: false,
      primaria: false,
      inicial: false,
      activos: [],
      count: 0,
      defaultNivel: 'secundaria',
      loading: true,
    };
  });

  useEffect(() => {
    if (cachedNiveles && cachedKey === claveUsuario) {
      setState({ ...cachedNiveles, loading: false });
      return;
    }

    // Usuario distinto al cacheado (logout/login): invalidar y recargar
    if (cachedKey !== claveUsuario) {
      cachedNiveles = null;
      cachedPromise = null;
      cachedKey = claveUsuario;
    }

    if (!cachedPromise) {
      cachedPromise = loadNiveles(user?.role === 'profesor')
        .then(data => {
          cachedNiveles = data;
        })
        .catch(() => {
          cachedNiveles = {
            secundaria: false,
            primaria: false,
            inicial: false,
            activos: [],
            count: 0,
            defaultNivel: 'secundaria',
          };
        });
    }

    cachedPromise.then(() => {
      if (cachedNiveles && cachedKey === claveUsuario) {
        setState({ ...cachedNiveles, loading: false });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claveUsuario]);

  return state;
};
