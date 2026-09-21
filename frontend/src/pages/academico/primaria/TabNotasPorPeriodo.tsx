import { useState, useCallback, useMemo, Fragment } from 'react';
import api from '../../../services/api';
import { Save } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import {
  EstudiantePrimData, CampoEditable,
  NOMBRES_COMPETENCIAS_PRIM, UMBRAL_RP_PRIMARIA, rpEditable,
  ModalidadRecuperacion, admiteRpNumerica, AYUDA_RP_PRIMARIA, AVISO_RP_CUALITATIVA,
  estadoPeriodoDe, ETIQUETA_ESTADO, AYUDA_NE_PRIMARIA,
} from './tipos';
import { avisoPeriodoCerrado, mensajeAvisos } from './periodoCerrado';

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
  modalidadRecuperacion?: ModalidadRecuperacion | null;
  onReload: () => Promise<void>;
}

// draft key: "estudianteId-competencia" -> { campo: valor }
// El borrador guarda las notas como texto y el NE como booleano: son dos
// tipos de dato distintos y mezclarlos en un string obligaría a adivinar.
type CampoNE = 'ne1' | 'ne2' | 'ne3' | 'ne4';
type Draft = Record<string, Partial<Record<CampoEditable, string>>>;
type DraftNE = Record<string, Partial<Record<CampoNE, boolean>>>;

export const TabNotasPorPeriodo: React.FC<Props> = ({ estudiantes, asignaturaId, numCompetencias, puedeEditar, modalidadRecuperacion, onReload }) => {
  // En 1ro y 2do no hay columna RP: la recuperacion del periodo es cualitativa.
  const conRp = admiteRpNumerica(modalidadRecuperacion);
  const [periodo, setPeriodo] = useState(1);
  const [drafts, setDrafts] = useState<Draft>({});
  const [draftsNE, setDraftsNE] = useState<DraftNE>({});
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  const campoP = `p${periodo}` as CampoEditable;
  const campoRP = `rp${periodo}` as CampoEditable;
  const campoNE = `ne${periodo}` as CampoNE;
  const key = (estId: number, comp: number) => `${estId}-${comp}`;

  const getComp = (est: EstudiantePrimData, compNum: number) =>
    est.competencias.find(c => c.competencia_numero === compNum);

  // NE tal y como se vería tras guardar: lo del borrador si el docente ya
  // lo tocó, si no lo que dice el servidor.
  const getNE = (est: EstudiantePrimData, compNum: number): boolean => {
    const k = key(est.estudiante.id, compNum);
    const d = draftsNE[k]?.[campoNE];
    if (d !== undefined) return d;
    return Boolean(getComp(est, compNum)?.[campoNE]);
  };

  const estadoDe = (est: EstudiantePrimData, compNum: number) => {
    if (getNE(est, compNum)) return 'ne' as const;
    return estadoPeriodoDe(getComp(est, compNum), periodo);
  };

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

  // Celdas realmente modificadas.
  //
  // R2-A8.1: esto solo miraba `drafts`, así que desmarcar un NE ya guardado
  // —sin escribir ninguna nota— no encendía el botón Guardar: el docente
  // veía la casilla desmarcada y no tenía forma de asentarlo. Ahora es la
  // unión de notas y NE, con la misma celda contada una sola vez.
  //
  // Un NE se cuenta solo si DIFIERE de lo guardado: marcar y volver a
  // desmarcar deja la celda como estaba y no debería pedir que se guarde.
  const celdasSucias = useMemo(() => {
    const sucias = new Set<string>();
    for (const [k, d] of Object.entries(drafts)) {
      if (Object.keys(d).length > 0) sucias.add(k);
    }
    for (const [k, d] of Object.entries(draftsNE)) {
      const propuesto = d?.[campoNE];
      if (propuesto === undefined) continue;
      const [estId, compNum] = k.split('-').map(Number);
      const est = estudiantes.find(e => e.estudiante.id === estId);
      const guardado = Boolean(est && getComp(est, compNum)?.[campoNE]);
      if (propuesto !== guardado) sucias.add(k);
    }
    return sucias;
  }, [drafts, draftsNE, estudiantes, campoNE]);

  const cambios = celdasSucias.size;

  // Marcar NE NO toca los borradores de nota.
  //
  // R2-A8.2: antes metía `P=''` y `RP=''` para «ensear lo que va a pasar».
  // El problema es que esos borradores sobrevivían al arrepentimiento: marcar
  // NE, pensarlo mejor, desmarcarlo y guardar mandaba `p=null, rp=null` y
  // borraba unas notas que nadie quiso borrar.
  //
  // El backend ya mantiene la invariante (NE=true limpia pN y rpN), así que
  // el frontend no necesita fabricar nada: se limita a enseñar la celda como
  // NE y a deshabilitarla. Si el docente desmarca antes de guardar, sus notas
  // siguen exactamente donde estaban.
  const marcarNE = (estId: number, compNum: number, valor: boolean) => {
    const k = key(estId, compNum);
    setDraftsNE(prev => ({ ...prev, [k]: { ...(prev[k] || {}), [campoNE]: valor } }));
  };

  const guardar = async () => {
    setGuardando(true);
    setMensaje(null);
    try {
      const aGuardar = Array.from(celdasSucias);
      // El backend responde 200 aunque haya saltado un período cerrado: guarda
      // lo que puede y avisa de lo que no. Si no se mira esa respuesta, el
      // profesor ve "Guardado" y cree que su corrección entró cuando no entró.
      const avisos: string[] = [];
      for (const k of aGuardar) {
        const [estId, compNum] = k.split('-').map(Number);
        const payload: any = { estudiante_id: estId, asignatura_id: asignaturaId, competencia_numero: compNum };
        const estFila = estudiantes.find(e => e.estudiante.id === estId);
        const neFinal = estFila ? getNE(estFila, compNum) : Boolean(draftsNE[k]?.[campoNE]);
        // Con NE activo no se manda ninguna nota. No es que se manden en
        // blanco: no se mandan. Si se mandara `p=null` junto a `ne=true` el
        // backend no sabría distinguirlo de una limpieza deliberada, y si se
        // mandara un número ganaría la nota y el NE se caería —que es
        // justo lo contrario de lo que el docente acaba de marcar—.
        if (!neFinal) {
          for (const [campo, val] of Object.entries(drafts[k] || {})) {
            payload[campo] = val === '' ? null : Number(val);
          }
        }
        for (const [campo, val] of Object.entries(draftsNE[k] || {})) {
          payload[campo] = val;   // booleano: el backend lo exige así
        }
        const response = await api.post('/calificaciones-primaria', payload);
        const aviso = avisoPeriodoCerrado(response?.data);
        if (aviso) avisos.push(aviso);
      }
      setDrafts({});
      setDraftsNE({});
      setMensaje(avisos.length > 0
        ? { tipo: 'warning', texto: mensajeAvisos(avisos) }
        : { tipo: 'success', texto: `Guardado (${aGuardar.length} celda${aGuardar.length !== 1 ? 's' : ''})` });
      // Recargar en ambos casos: lo que quedó en el servidor es la verdad.
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
                <th key={n} colSpan={conRp ? 3 : 2} className="px-2 py-1.5 text-center font-medium text-gray-600 border-l">
                  C{n} · {NOMBRES_COMPETENCIAS_PRIM[n]?.split(',')[0] || `Comp ${n}`}
                </th>
              ))}
            </tr>
            <tr className="text-xs">
              {comps.map(n => (
                <Fragment key={n}>
                  <th className="px-1 py-1 text-center font-medium text-gray-500 border-l">P{periodo}</th>
                  {conRp && <th className="px-1 py-1 text-center font-normal text-gray-400">RP{periodo}</th>}
                  <th className="px-1 py-1 text-center font-normal text-gray-400" title={AYUDA_NE_PRIMARIA}>NE</th>
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
                  const ne = getNE(est, n);
                  // Un RP ya asentado es LA nota del período: no puede
                  // desaparecer de la pantalla porque la P suba de 65.
                  const rpOn = rpEditable(
                    pVal,
                    getComp(est, n)?.[campoRP] as number | null | undefined,
                    drafts[key(est.estudiante.id, n)]?.[campoRP],
                  ) && !ne;
                  const estado = estadoDe(est, n);
                  return (
                  <Fragment key={n}>
                    <td className="px-1 py-1 text-center border-l">
                      <input
                        type="number" min={0} max={100}
                        value={ne ? '' : getValor(est, n, campoP)}
                        onChange={e => handleChange(est.estudiante.id, n, campoP, e.target.value)}
                        disabled={!puedeEditar || ne}
                        placeholder={estado === 'pendiente' ? '—' : ''}
                        title={ETIQUETA_ESTADO[estado]}
                        className={`w-14 px-1 py-1 text-center border rounded text-sm focus:ring-1 focus:ring-blue-400 disabled:bg-gray-50 ${
                          estado === 'ne' ? 'bg-slate-100 text-slate-400' :
                          estado === 'pendiente' ? 'border-dashed text-gray-400' : ''}`}
                      />
                    </td>
                    {conRp && <td className="px-1 py-1 text-center">
                      <input
                        type="number" min={0} max={100}
                        value={rpOn ? getValor(est, n, campoRP) : ''}
                        onChange={e => handleChange(est.estudiante.id, n, campoRP, e.target.value)}
                        disabled={!puedeEditar || !rpOn}
                        placeholder={rpOn ? 'RP' : '—'}
                        title={rpOn ? AYUDA_RP_PRIMARIA
                          : ne ? 'Período marcado NE: no lleva nota'
                          : `Para ABRIR una recuperación, P${periodo} debe ser menor que ${UMBRAL_RP_PRIMARIA}. Una RP ya asentada siempre se puede corregir.`}
                        className={`w-12 px-1 py-1 text-center border rounded text-xs focus:ring-1 focus:ring-amber-400 disabled:bg-gray-100 disabled:text-gray-300 ${rpOn ? 'bg-amber-50/40' : ''}`}
                      />
                    </td>}
                    <td className="px-1 py-1 text-center">
                      <input
                        type="checkbox"
                        checked={ne}
                        onChange={e => marcarNE(est.estudiante.id, n, e.target.checked)}
                        disabled={!puedeEditar}
                        title={AYUDA_NE_PRIMARIA}
                        className="h-4 w-4 accent-slate-600 disabled:opacity-40"
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
        <span className="inline-flex items-center gap-1 mr-3">
          <span className="inline-block w-3 h-3 rounded-sm border border-dashed border-gray-400" />
          pendiente de evaluar
        </span>
        <span className="inline-flex items-center gap-1 mr-3">
          <span className="inline-block w-3 h-3 rounded-sm bg-slate-100 border border-slate-300" />
          NE — no evaluado (justificado)
        </span>
        <br />
        {AYUDA_NE_PRIMARIA}
        <br />
        {conRp
          ? `Cada celda: P${periodo} y su recuperación (RP${periodo}). ${AYUDA_RP_PRIMARIA}`
          : AVISO_RP_CUALITATIVA}
      </p>
    </div>
  );
};
