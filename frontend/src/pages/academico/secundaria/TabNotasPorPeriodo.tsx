import { useState, useCallback, useMemo, Fragment } from 'react';
import api from '../../../services/api';
import { Save, BookOpen } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import {
  EstudianteData, NOMBRES_COMPETENCIAS, getNotaClass,
} from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB NOTAS POR PERÍODO (vista alternativa)
// Selector de período (P1-P4). Muestra las 4 competencias de ese período
// lado a lado (P y RP de cada una) para cada estudiante.
// Coincide con cómo el maestro califica: por período.
// El cálculo del PC/CF NO cambia — se hace en el backend.
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudianteData[];
  asignaturaId: number;
  puedeEditar: boolean;
  onReload: () => Promise<void>;
  periodosCerrados?: Record<string, boolean>;
}

// clave: "estudianteId-competenciaNumero" → { p?: valor, rp?: valor }
type EditadasState = Record<string, { p?: number | null; rp?: number | null }>;

export const TabNotasPorPeriodo: React.FC<Props> = ({ estudiantes, asignaturaId, puedeEditar, onReload, periodosCerrados = {} }) => {
  const [periodoActivo, setPeriodoActivo] = useState<number>(1);
  const [editadas, setEditadas] = useState<EditadasState>({});
  const [saving, setSaving] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  // ¿El período activo está cerrado? → bloquea las casillas
  const periodoActivoCerrado = !!periodosCerrados[`p${periodoActivo}`];

  // Nombre del campo P/RP para el período activo (ej. periodo 1 → 'p1' / 'rp1')
  const campoP = `p${periodoActivo}` as const;
  const campoRP = `rp${periodoActivo}` as const;

  // Obtener valor actual (editado o del backend) de un estudiante/competencia
  const getValor = useCallback((est: EstudianteData, compNum: number, tipo: 'p' | 'rp'): number | null => {
    const key = `${est.estudiante.id}-${compNum}`;
    const ed = editadas[key];
    if (ed && tipo in ed) return (tipo === 'p' ? ed.p : ed.rp) ?? null;
    const comp = est.competencias[compNum];
    if (!comp) return null;
    return (comp[tipo === 'p' ? campoP : campoRP]) ?? null;
  }, [editadas, campoP, campoRP]);

  // Registrar un cambio en una celda
  const onChangeCelda = useCallback((estId: number, compNum: number, tipo: 'p' | 'rp', valorStr: string) => {
    const key = `${estId}-${compNum}`;
    let valor: number | null = null;
    if (valorStr !== '') {
      const parsed = parseFloat(valorStr);
      if (Number.isNaN(parsed)) return;
      if (parsed < 0 || parsed > 100) return;
      valor = parsed;
    }
    setEditadas(prev => ({
      ...prev,
      [key]: { ...prev[key], [tipo]: valor },
    }));
  }, []);

  // Guardar todos los cambios
  const guardar = async () => {
    const keys = Object.keys(editadas);
    if (keys.length === 0) {
      setMensaje({ tipo: 'error', texto: 'No hay cambios por guardar' });
      return;
    }
    setSaving(true);
    setMensaje(null);
    const errores: string[] = [];
    const avisosCierre: string[] = [];

    try {
      // Agrupar por estudiante+competencia y enviar solo el período activo
      for (const key of keys) {
        const [estIdStr, compNumStr] = key.split('-');
        const estId = parseInt(estIdStr);
        const compNum = parseInt(compNumStr);
        const cambios = editadas[key];

        const payload: Record<string, unknown> = {
          estudiante_id: estId,
          asignatura_id: asignaturaId,
          competencia_numero: compNum,
        };
        // Solo mandamos el P/RP del período activo
        if ('p' in cambios) payload[campoP] = cambios.p;
        if ('rp' in cambios) payload[campoRP] = cambios.rp;

        try {
          const res = await api.post('/calificaciones-secundaria', payload);
          // Si el backend avisa que el período estaba cerrado
          if (res.data?.periodos_cerrados_ignorados?.length > 0) {
            avisosCierre.push(res.data.message);
          }
        } catch (err: unknown) {
          const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'error';
          errores.push(`Est ${estId}: ${msg}`);
        }
      }

      if (errores.length > 0) {
        setMensaje({ tipo: 'error', texto: `Errores: ${errores.slice(0, 3).join('; ')}` });
      } else if (avisosCierre.length > 0) {
        setMensaje({ tipo: 'warning', texto: avisosCierre[0] });
      } else {
        setMensaje({ tipo: 'success', texto: 'Notas guardadas correctamente' });
      }

      setEditadas({});
      await onReload();
    } catch {
      setMensaje({ tipo: 'error', texto: 'Error al guardar las notas' });
    } finally {
      setSaving(false);
    }
  };

  // Renderizar una celda editable (input)
  const renderCelda = (est: EstudianteData, compNum: number, tipo: 'p' | 'rp') => {
    const valor = getValor(est, compNum, tipo);
    const esRetirado = !!est.estudiante.retirado;
    // Si no puede editar, está retirado, o el período está cerrado → solo lectura
    if (!puedeEditar || esRetirado || periodoActivoCerrado) {
      return <span className={getNotaClass(valor)}>{valor ?? '—'}</span>;
    }
    return (
      <input
        type="number"
        min={0}
        max={100}
        value={valor ?? ''}
        onChange={e => onChangeCelda(est.estudiante.id, compNum, tipo, e.target.value)}
        className={`w-14 px-1 py-1 text-center border rounded text-sm ${tipo === 'rp' ? 'bg-amber-50' : ''}`}
      />
    );
  };

  const totalEditados = useMemo(() => Object.keys(editadas).length, [editadas]);

  return (
    <div className="space-y-4">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Acción guardar */}
      {totalEditados > 0 && puedeEditar && (
        <div className="flex justify-end">
          <Button onClick={guardar} loading={saving} icon={<Save size={16} />} variant="success">
            Guardar ({totalEditados})
          </Button>
        </div>
      )}

      {/* Selector de período (pestañas) */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">Período a calificar</label>
        <div className="flex gap-2">
          {[1, 2, 3, 4].map(n => {
            const cerrado = !!periodosCerrados[`p${n}`];
            return (
              <button
                key={n}
                onClick={() => setPeriodoActivo(n)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  periodoActivo === n
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Período {n} {cerrado && '🔒'}
              </button>
            );
          })}
        </div>
        {!puedeEditar && (
          <p className="text-xs text-gray-500 mt-2">Vista solo lectura. Únicamente los profesores asignados pueden calificar.</p>
        )}
      </div>

      {/* Tabla: 4 competencias del período activo */}
      {estudiantes.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
          <BookOpen size={42} className="mx-auto text-gray-300 mb-3" />
          <p className="text-gray-500">No hay estudiantes en este curso</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          {periodoActivoCerrado ? (
            <div className="mb-3 px-3 py-2 bg-red-50 border-l-4 border-red-500 rounded">
              <p className="font-bold text-red-900 text-sm">🔒 Período {periodoActivo} cerrado</p>
              <p className="text-xs text-red-700">
                Este período está cerrado y no se puede editar. Use "Solicitar Corrección" si necesita cambiar una nota.
              </p>
            </div>
          ) : (
            <div className="mb-3 px-3 py-2 bg-blue-50 border-l-4 border-blue-500 rounded">
              <p className="font-bold text-blue-900 text-sm">Período {periodoActivo}</p>
              <p className="text-xs text-blue-700">
                Llená el P{periodoActivo} de las 4 competencias. RP = recuperación (solo si P &lt; 70).
              </p>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-2 py-2 text-left font-medium text-gray-600">No.</th>
                  <th className="px-2 py-2 text-left font-medium text-gray-600 min-w-[160px]">Estudiante</th>
                  {[1, 2, 3, 4].map(c => (
                    <th key={c} colSpan={2} className="px-2 py-2 text-center font-medium text-teal-700 bg-teal-50 border-l">
                      Comp. {c}
                    </th>
                  ))}
                </tr>
                <tr className="bg-gray-50 text-xs">
                  <th></th>
                  <th></th>
                  {[1, 2, 3, 4].map(c => (
                    <Fragment key={c}>
                      <th className="px-1 py-1 text-center font-medium text-gray-600 border-l">P{periodoActivo}</th>
                      <th className="px-1 py-1 text-center font-medium text-amber-600 bg-amber-50">RP</th>
                    </Fragment>
                  ))}
                </tr>
              </thead>
              <tbody>
                {estudiantes.map((est, idx) => {
                  const esRetirado = !!est.estudiante.retirado;
                  return (
                    <tr key={est.estudiante.id} className={`border-b ${esRetirado ? 'bg-gray-50' : 'hover:bg-gray-50'}`}>
                      <td className="px-2 py-1 text-center text-gray-500">{idx + 1}</td>
                      <td className="px-2 py-1">
                        {est.estudiante.nombre_completo}
                        {esRetirado && <span className="ml-1 text-xs text-red-500">(retirado)</span>}
                      </td>
                      {[1, 2, 3, 4].map(c => (
                        <Fragment key={c}>
                          <td className="px-1 py-1 text-center border-l">{renderCelda(est, c, 'p')}</td>
                          <td className="px-1 py-1 text-center bg-amber-50">{renderCelda(est, c, 'rp')}</td>
                        </Fragment>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
