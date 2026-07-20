import { useEffect } from 'react';
import { useNivelesActivos, Nivel } from '../hooks/useNivelesActivos';
import { useAuth } from '../context/AuthContext';
import { GraduationCap, BookOpen, Baby } from 'lucide-react';

interface NivelTabsProps {
  value: Nivel | 'todos';
  onChange: (nivel: Nivel | 'todos') => void;
  /** Mostrar opción "Todos" (útil en estadísticas agregadas) */
  showAll?: boolean;
  /** Estilo compacto (para barras superiores) */
  compact?: boolean;
  /** Texto adicional bajo las tabs */
  hint?: string;
}

const NIVEL_CONFIG: Record<Nivel, { label: string; icon: typeof GraduationCap; color: string; activeColor: string }> = {
  secundaria: {
    label: 'Secundaria',
    icon: GraduationCap,
    color: 'text-blue-700',
    activeColor: 'border-blue-600 text-blue-700 bg-blue-50',
  },
  primaria: {
    label: 'Primaria',
    icon: BookOpen,
    color: 'text-indigo-700',
    activeColor: 'border-indigo-600 text-indigo-700 bg-indigo-50',
  },
  inicial: {
    label: 'Inicial',
    icon: Baby,
    color: 'text-pink-700',
    activeColor: 'border-pink-600 text-pink-700 bg-pink-50',
  },
};

/**
 * Tabs de niveles educativos. Se oculta automáticamente si solo hay 1 nivel activo.
 */
export const NivelTabs: React.FC<NivelTabsProps> = ({ value, onChange, showAll = false, compact = false, hint }) => {
  const niveles = useNivelesActivos();
  const { user } = useAuth();

  // v2.15: LENTE DE DIVISIÓN. Si hay lente activo (switch de dirección o
  // división fija de coordinador/secretaría/psicología), estas pestañas
  // desaparecen y el valor se fuerza al nivel del lente — evita el conflicto
  // "lente en Primaria + pestaña Secundaria = 0 resultados y confusión".
  // PROFESORES quedan exentos: su acceso lo rigen las asignaciones (el mixto
  // de inglés necesita ver ambas pestañas), igual que en el backend.
  const lente: Nivel | null = (() => {
    if (!user || user.role === 'profesor' || user.role === 'superadmin') return null;
    if (user.role === 'direccion') {
      const v = typeof window !== 'undefined' ? localStorage.getItem('educaone_nivel_vista') : null;
      return v === 'primaria' || v === 'secundaria' ? (v as Nivel) : null;
    }
    const nv = (user as any)?.nivel_asignado;
    return nv === 'primaria' || nv === 'secundaria' ? (nv as Nivel) : null;
  })();

  useEffect(() => {
    if (lente && value !== lente) onChange(lente);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lente]);

  if (lente) return null; // la división manda: sin pestañas redundantes

  // Si solo hay 1 nivel activo, no tiene sentido mostrar tabs
  if (niveles.loading) return null;
  if (niveles.count <= 1 && !showAll) return null;

  // Poner "Todos" primero para que sea visualmente el default
  const opciones: Array<Nivel | 'todos'> = [];
  if (showAll && niveles.count > 1) opciones.push('todos');
  opciones.push(...niveles.activos);

  const size = compact ? 'text-sm py-2 px-3' : 'py-2.5 px-4';

  return (
    <div className="mb-4">
      <div className="flex gap-1 border-b border-gray-200 overflow-x-auto">
        {opciones.map(op => {
          const isActive = value === op;
          if (op === 'todos') {
            return (
              <button
                key={op}
                onClick={() => onChange('todos')}
                className={`${size} font-medium border-b-2 transition whitespace-nowrap ${
                  isActive
                    ? 'border-slate-700 text-slate-800 bg-slate-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                🔀 Todos
              </button>
            );
          }
          const cfg = NIVEL_CONFIG[op];
          const Icon = cfg.icon;
          return (
            <button
              key={op}
              onClick={() => onChange(op)}
              className={`${size} font-medium border-b-2 transition flex items-center gap-2 whitespace-nowrap ${
                isActive ? cfg.activeColor : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Icon size={16} />
              {cfg.label}
            </button>
          );
        })}
      </div>
      {hint && <p className="text-xs text-gray-500 mt-2">{hint}</p>}
    </div>
  );
};

/**
 * Hook auxiliar: devuelve el nivel inicial recomendado (con fallback al default).
 * Útil para inicializar estado en páginas.
 */
export const useNivelInicial = (defaultFallback: Nivel = 'secundaria'): Nivel => {
  const { defaultNivel, loading } = useNivelesActivos();
  return loading ? defaultFallback : defaultNivel;
};
