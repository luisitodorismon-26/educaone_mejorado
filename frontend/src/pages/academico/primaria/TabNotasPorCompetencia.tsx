import { useState, useCallback, useMemo, Fragment } from 'react';
import api from '../../../services/api';
import { Save } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import {
  EstudiantePrimData, CampoEditable, CAMPOS_PERIODOS,
  NOMBRES_COMPETENCIAS_PRIM, MINIMO_APROBATORIO_PRIMARIA,
  UMBRAL_RP_PRIMARIA, rpHabilitado, finalCompetencia,
  ModalidadRecuperacion, admiteRpNumerica, AYUDA_RP_PRIMARIA, AVISO_RP_CUALITATIVA,
  estadoPeriodoDe, ETIQUETA_ESTADO,
} from './tipos';
import { avisoPeriodoCerrado, mensajeAvisos } from './periodoCerrado';

// ════════════════════════════════════════════════════════════════════
// TAB NOTAS POR COMPETENCIA — PRIMARIA (v2.13.45)
// Selector de competencia (1..N) + tabla de 8 columnas P1/RP1..P4/RP4.
// Mecánica idéntica a secundaria; reglas de primaria (corte 65).
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudiantePrimData[];
  asignaturaId: number;
  numCompetencias: number;
  puedeEditar: boolean;
  modalidadRecuperacion?: ModalidadRecuperacion | null;
  onReload: () => Promise<void>;
}

// draft key: "estudianteId-competencia" -> { campo: valor }
type Draft = Record<string, Partial<Record<CampoEditable, string>>>;

export const TabNotasPorCompetencia: React.FC<Props> = ({ estudiantes, asignaturaId, numCompetencias, puedeEditar, modalidadRecuperacion, onReload }) => {
  // En 1ro y 2do no hay columna RP: la recuperacion del periodo es cualitativa.
  const conRp = admiteRpNumerica(modalidadRecuperacion);
  const [compSel, setCompSel] = useState(1);
  const [drafts, setDrafts] = useState<Draft>({});
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  const key = (estId: number, comp: number) => `${estId}-${comp}`;

  const getComp = (est: EstudiantePrimData, compNum: number) =>
    est.competencias.find(c => c.competencia_numero === compNum);

  const getValor = (est: EstudiantePrimData, campo: CampoEditable): string => {
    const k = key(est.estudiante.id, compSel);
    if (drafts[k]?.[campo] !== undefined) return drafts[k]![campo]!;
    const comp = getComp(est, compSel);
    const v = comp ? (comp[campo] as number | null) : null;
    return v != null ? String(v) : '';
  };

  const handleChange = useCallback((estId: number, campo: CampoEditable, valor: string) => {
    if (valor !== '' && (isNaN(Number(valor)) || Number(valor) < 0 || Number(valor) > 100)) return;
    setDrafts(prev => ({ ...prev, [key(estId, compSel)]: { ...prev[key(estId, compSel)], [campo]: valor } }));
  }, [compSel]);

  const cambios = useMemo(
    () => Object.keys(drafts).filter(k => k.endsWith(`-${compSel}`) && Object.keys(drafts[k]).length > 0).length,
    [drafts, compSel]
  );

  // Final en vivo (con drafts aplicados)
  const finalEnVivo = (est: EstudiantePrimData): number | null => {
    const comp = getComp(est, compSel);
    if (!comp) return null;
    const k = key(est.estudiante.id, compSel);
    const merged = { ...comp };
    if (drafts[k]) {
      for (const [campo, val] of Object.entries(drafts[k])) {
        (merged as any)[campo] = val === '' ? null : Number(val);
      }
    }
    return finalCompetencia(merged);
  };

  const guardar = async () => {
    setGuardando(true);
    setMensaje(null);
    try {
      const aGuardar = Object.keys(drafts).filter(k => k.endsWith(`-${compSel}`) && Object.keys(drafts[k]).length > 0);
      // El backend responde 200 aunque haya saltado un período cerrado: guarda
      // lo que puede y avisa de lo que no. Si no se mira esa respuesta, el
      // profesor ve "Guardado" y cree que su corrección entró cuando no entró.
      const avisos: string[] = [];
      for (const k of aGuardar) {
        const estId = Number(k.split('-')[0]);
        const payload: any = { estudiante_id: estId, asignatura_id: asignaturaId, competencia_numero: compSel };
        for (const [campo, val] of Object.entries(drafts[k])) {
          payload[campo] = val === '' ? null : Number(val);
        }
        const response = await api.post('/calificaciones-primaria', payload);
        const aviso = avisoPeriodoCerrado(response?.data);
        if (aviso) avisos.push(aviso);
      }
      setDrafts(prev => {
        const n = { ...prev };
        aGuardar.forEach(k => delete n[k]);
        return n;
      });
      setMensaje(avisos.length > 0
        ? { tipo: 'warning', texto: mensajeAvisos(avisos) }
        : { tipo: 'success', texto: `Guardado (${aGuardar.length} estudiante${aGuardar.length !== 1 ? 's' : ''})` });
      // Recargar en ambos casos: lo que quedó en el servidor es la verdad.
      await onReload();
    } catch (e: any) {
      setMensaje({ tipo: 'error', texto: e.response?.data?.error || 'Error al guardar' });
    } finally {
      setGuardando(false);
    }
  };

  const activos = estudiantes.filter(e => !e.estudiante.retirado);

  return (
    <div className="space-y-3">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      <div className="flex items-center gap-3 flex-wrap">
        <label className="text-sm text-gray-600">Competencia:</label>
        <select
          value={compSel}
          onChange={e => setCompSel(Number(e.target.value))}
          className="px-3 py-1.5 border rounded-lg text-sm font-medium"
        >
          {Array.from({ length: numCompetencias }, (_, i) => i + 1).map(n => (
            <option key={n} value={n}>C{n} · {NOMBRES_COMPETENCIAS_PRIM[n] || `Competencia ${n}`}</option>
          ))}
        </select>
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
              <th className="px-3 py-2 text-left font-medium text-gray-600 sticky left-0 bg-gray-50">Estudiante</th>
              {CAMPOS_PERIODOS.map(cp => (
                <Fragment key={cp.periodo}>
                  <th className="px-2 py-2 text-center font-medium text-gray-600">P{cp.periodo}</th>
                  {conRp && <th className="px-2 py-2 text-center font-normal text-gray-400 text-xs">RP{cp.periodo}</th>}
                </Fragment>
              ))}
              <th className="px-3 py-2 text-center font-medium text-blue-700">Final</th>
            </tr>
          </thead>
          <tbody>
            {activos.map(est => {
              const fin = finalEnVivo(est);
              const aprobado = fin != null && fin >= MINIMO_APROBATORIO_PRIMARIA;
              return (
                <tr key={est.estudiante.id} className="border-b hover:bg-gray-50">
                  <td className="px-3 py-1.5 font-medium text-gray-800 sticky left-0 bg-white">{est.estudiante.nombre_completo}</td>
                  {CAMPOS_PERIODOS.map(cp => {
                    const pVal = getValor(est, cp.p) !== '' ? Number(getValor(est, cp.p)) : null;
                    const _estado = estadoPeriodoDe(getComp(est, compSel), cp.periodo);
                    const rpOn = rpHabilitado(pVal) && _estado !== 'ne';
                    return (
                    <Fragment key={cp.periodo}>
                      <td className="px-1 py-1 text-center">
                        <input
                          type="number" min={0} max={100}
                          value={getValor(est, cp.p)}
                          onChange={e => handleChange(est.estudiante.id, cp.p, e.target.value)}
                          disabled={!puedeEditar || _estado === 'ne'}
                          placeholder={_estado === 'pendiente' ? '—' : ''}
                          title={ETIQUETA_ESTADO[_estado]}
                          className={`w-14 px-1 py-1 text-center border rounded text-sm focus:ring-1 focus:ring-blue-400 disabled:bg-gray-50 ${
                            _estado === 'ne' ? 'bg-slate-100 text-slate-400' :
                            _estado === 'pendiente' ? 'border-dashed text-gray-400' : ''}`}
                        />
                      </td>
                      {conRp && <td className="px-1 py-1 text-center">
                        <input
                          type="number" min={0} max={100}
                          value={rpOn ? getValor(est, cp.rp) : ''}
                          onChange={e => handleChange(est.estudiante.id, cp.rp, e.target.value)}
                          disabled={!puedeEditar || !rpOn}
                          placeholder={rpOn ? 'RP' : '—'}
                          title={rpOn ? AYUDA_RP_PRIMARIA : `RP se habilita solo si P${cp.periodo} < ${UMBRAL_RP_PRIMARIA}`}
                          className={`w-12 px-1 py-1 text-center border rounded text-xs focus:ring-1 focus:ring-amber-400 disabled:bg-gray-100 disabled:text-gray-300 ${rpOn ? 'bg-amber-50/40' : ''}`}
                        />
                      </td>}
                    </Fragment>
                    );
                  })}
                  <td className={`px-3 py-1.5 text-center font-bold ${fin == null ? 'text-gray-300' : aprobado ? 'text-green-600' : 'text-red-600'}`}>
                    {fin != null ? Math.round(fin) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-500">
        {conRp ? AYUDA_RP_PRIMARIA : AVISO_RP_CUALITATIVA}{' '}
        Final de competencia = promedio de los períodos evaluados. Aprueba con {MINIMO_APROBATORIO_PRIMARIA}.
      </p>
    </div>
  );
};
