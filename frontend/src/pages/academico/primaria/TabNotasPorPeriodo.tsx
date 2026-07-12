import { useState, useCallback, useMemo, Fragment } from 'react';
import api from '../../../services/api';
import { Save } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import {
  EstudiantePrimData, CampoEditable,
  NOMBRES_COMPETENCIAS_PRIM, UMBRAL_RP_PRIMARIA, rpHabilitado,
} from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB NOTAS POR PERÍODO — PRIMARIA (v2.13.45)
// Selector de período (1-4) + tabla con las N competencias como columnas.
// Cada celda = P y RP del período para esa competencia.
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudiantePrimData[];
  asignaturaId: number;
  numCompetencias: number;
  puedeEditar: boolean;
  onReload: () => Promise<void>;
}

// draft key: "estudianteId-competencia" -> { campo: valor }
type Draft = Record<string, Partial<Record<CampoEditable, string>>>;

export const TabNotasPorPeriodo: React.FC<Props> = ({ estudiantes, asignaturaId, numCompetencias, puedeEditar, onReload }) => {
  const [periodo, setPeriodo] = useState(1);
  const [drafts, setDrafts] = useState<Draft>({});
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const campoP = `p${periodo}` as CampoEditable;
  const campoRP = `rp${periodo}` as CampoEditable;
  const key = (estId: number, comp: number) => `${estId}-${comp}`;

  const getComp = (est: EstudiantePrimData, compNum: number) =>
    est.competencias.find(c => c.competencia_numero === compNum);

  const getValor = (est: EstudiantePrimData, compNum: number, campo: CampoEditable): string => {
    const k = key(est.estudiante.id, compNum);
    if (drafts[k]?.[campo] !== undefined) return drafts[k]![campo]!;
    const comp = getComp(est, compNum);
    const v = comp ? (comp[campo] as number | null) : null;
    return v != null ? String(v) : '';
  };

  const handleChange = useCallback((estId: number, compNum: number, campo: CampoEditable, valor: string) => {
    if (valor !== '' && (isNaN(Number(valor)) || Number(valor) < 0 || Number(valor) > 100)) return;
    setDrafts(prev => ({ ...prev, [key(estId, compNum)]: { ...prev[key(estId, compNum)], [campo]: valor } }));
  }, []);

  const cambios = useMemo(() => Object.values(drafts).filter(d => Object.keys(d).length > 0).length, [drafts]);

  const guardar = async () => {
    setGuardando(true);
    setMensaje(null);
    try {
      const aGuardar = Object.keys(drafts).filter(k => Object.keys(drafts[k]).length > 0);
      for (const k of aGuardar) {
        const [estId, compNum] = k.split('-').map(Number);
        const payload: any = { estudiante_id: estId, asignatura_id: asignaturaId, competencia_numero: compNum };
        for (const [campo, val] of Object.entries(drafts[k])) {
          payload[campo] = val === '' ? null : Number(val);
        }
        await api.post('/calificaciones-primaria', payload);
      }
      setDrafts({});
      setMensaje({ tipo: 'success', texto: `Guardado (${aGuardar.length} celda${aGuardar.length !== 1 ? 's' : ''})` });
      await onReload();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setGuardando(false);
    }
  };

  const comps = Array.from({ length: numCompetencias }, (_, i) => i + 1);
  const activos = estudiantes.filter(e => !e.estudiante.retirado);

  return (
    <div className="space-y-3">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-sm text-gray-600">Período:</label>
        <div className="flex gap-1 bg-gray-100 p-1 rounded-lg">
          {[1, 2, 3, 4].map(p => (
            <button
              key={p}
              onClick={() => setPeriodo(p)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
                periodo === p ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              P{p}
            </button>
          ))}
        </div>
        {puedeEditar && cambios > 0 && (
          <Button variant="success" size="sm" loading={guardando} onClick={guardar} icon={<Save size={14} />}>
            Guardar ({cambios})
          </Button>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th rowSpan={2} className="px-3 py-2 text-left font-medium text-gray-600 sticky left-0 bg-gray-50 align-bottom">Estudiante</th>
              {comps.map(n => (
                <th key={n} colSpan={2} className="px-2 py-1.5 text-center font-medium text-gray-600 border-l">
                  C{n} · {NOMBRES_COMPETENCIAS_PRIM[n]?.split(',')[0] || `Comp ${n}`}
                </th>
              ))}
            </tr>
            <tr className="text-xs">
              {comps.map(n => (
                <Fragment key={n}>
                  <th className="px-1 py-1 text-center font-medium text-gray-500 border-l">P{periodo}</th>
                  <th className="px-1 py-1 text-center font-normal text-gray-400">RP{periodo}</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {activos.map(est => (
              <tr key={est.estudiante.id} className="border-b hover:bg-gray-50">
                <td className="px-3 py-1.5 font-medium text-gray-800 sticky left-0 bg-white">{est.estudiante.nombre_completo}</td>
                {comps.map(n => {
                  const pVal = getValor(est, n, campoP) !== '' ? Number(getValor(est, n, campoP)) : null;
                  const rpOn = rpHabilitado(pVal);
                  return (
                  <Fragment key={n}>
                    <td className="px-1 py-1 text-center border-l">
                      <input
                        type="number" min={0} max={100}
                        value={getValor(est, n, campoP)}
                        onChange={e => handleChange(est.estudiante.id, n, campoP, e.target.value)}
                        disabled={!puedeEditar}
                        className="w-14 px-1 py-1 text-center border rounded text-sm focus:ring-1 focus:ring-blue-400 disabled:bg-gray-50"
                      />
                    </td>
                    <td className="px-1 py-1 text-center">
                      <input
                        type="number" min={0} max={100}
                        value={rpOn ? getValor(est, n, campoRP) : ''}
                        onChange={e => handleChange(est.estudiante.id, n, campoRP, e.target.value)}
                        disabled={!puedeEditar || !rpOn}
                        placeholder={rpOn ? 'RP' : '—'}
                        title={rpOn ? `Recuperación del P${periodo}` : `RP se habilita solo si P${periodo} < ${UMBRAL_RP_PRIMARIA}`}
                        className={`w-12 px-1 py-1 text-center border rounded text-xs focus:ring-1 focus:ring-amber-400 disabled:bg-gray-100 disabled:text-gray-300 ${rpOn ? 'bg-amber-50/40' : ''}`}
                      />
                    </td>
                  </Fragment>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-500">
        Cada celda: P{periodo} y su recuperación (RP{periodo}). Se toma el mayor de los dos como valor del período.
      </p>
    </div>
  );
};
