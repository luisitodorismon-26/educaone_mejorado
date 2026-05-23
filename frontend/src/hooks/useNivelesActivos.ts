import { useState, useEffect } from 'react';
import api from '../services/api';

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

// Cache en memoria para evitar llamadas repetidas (config rara vez cambia)
let cachedNiveles: Omit<NivelesState, 'loading'> | null = null;
let cachedPromise: Promise<void> | null = null;

export const invalidateNivelesCache = () => {
  cachedNiveles = null;
  cachedPromise = null;
};

const loadNiveles = async (): Promise<Omit<NivelesState, 'loading'>> => {
  // Leer config de módulos + también detectar por grados existentes
  // Así si el colegio tiene grados de primaria aunque no haya activado el módulo, también aparecen
  let d: any = {};
  let gradosNivel: string[] = [];
  try {
    const [cfgRes, gradosRes] = await Promise.all([
      api.get('/configuracion/modulos'),
      api.get('/grados').catch(() => ({ data: [] })),
    ]);
    d = cfgRes.data || {};
    gradosNivel = (gradosRes.data || []).map((g: any) => g.nivel || 'secundaria');
  } catch {
    d = {};
  }

  // Un nivel está activo si el módulo está habilitado en el efectivo (plan AND uso).
  // El endpoint /configuracion/modulos ya devuelve estado EFECTIVO desde backend.
  // No inferimos desde grados existentes — si el plan cambió, los grados viejos
  // no deben "resucitar" un nivel desactivado.
  const secundaria = d.modulo_secundaria === true;
  const primaria = d.modulo_primaria === true;
  const inicial = d.modulo_inicial === true;

  const activos: Nivel[] = [];
  if (secundaria) activos.push('secundaria');
  if (primaria) activos.push('primaria');
  if (inicial) activos.push('inicial');

  // Si ninguno activo (config rota o nuevo colegio sin plan), default a secundaria
  // para que la UI no quede en blanco. Backend valida lo que importa.
  if (activos.length === 0) activos.push('secundaria');

  return {
    secundaria,
    primaria,
    inicial,
    activos,
    count: activos.length,
    defaultNivel: activos[0],
  };
};

/**
 * Hook que devuelve qué niveles educativos están activos para el colegio actual.
 * Usa cache en memoria — solo hace la llamada 1 vez por sesión.
 *
 * IMPORTANTE: el estado inicial mientras carga es neutro (loading=true, sin
 * defaults sesgados a secundaria). Los componentes que filtran por nivel deben
 * verificar `loading` antes de hacer el filtrado, o esperar la primera carga.
 */
export const useNivelesActivos = (): NivelesState => {
  const [state, setState] = useState<NivelesState>(() => {
    if (cachedNiveles) return { ...cachedNiveles, loading: false };
    // Estado inicial neutro: TODO falso, sin asumir nada. Esto previene que un
    // componente filtre cursos como "secundaria" mientras la API aún responde,
    // que era el bug que ocultaba cursos de primaria en colegios solo-primaria.
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
    if (cachedNiveles) {
      setState({ ...cachedNiveles, loading: false });
      return;
    }

    if (!cachedPromise) {
      cachedPromise = loadNiveles()
        .then(data => {
          cachedNiveles = data;
        })
        .catch(() => {
          // En caso de error de red, NO asumir nada. Dejar todo apagado y que
          // los componentes muestren mensaje "cargando" o lista vacía. Mejor
          // que mostrar pantalla incorrecta de secundaria a un colegio primaria.
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
      if (cachedNiveles) setState({ ...cachedNiveles, loading: false });
    });
  }, []);

  return state;
};
