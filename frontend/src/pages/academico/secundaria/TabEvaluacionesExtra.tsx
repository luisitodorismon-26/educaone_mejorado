import { useState } from 'react';
import api from '../../../services/api';
import { AlertTriangle, Save, CheckCircle, Pencil, X } from 'lucide-react';
import { Button, Alert } from '../../../components/ui';
import { EstudianteData } from './tipos';

// ════════════════════════════════════════════════════════════════════
// TAB EVALUACIONES EXTRA — v2.13.38
// Tabla desglosada como el registro oficial MINERD (pág. 176):
//   COMPLETIVA:      50%CF | C.E.C. | 50%C.E.C. | C.C.F.
//   EXTRAORDINARIA:  30%CF | C.E.EX | 70%C.E.EX | C.EX.F.
//   ESPECIAL:        C.F. + C.E. = Final
// El input de cada fase va EN SU CELDA, con el cálculo en vivo.
// El C.E. es COMPLEMENTARIO (puntos que se suman, máx = 100 - CF).
// ════════════════════════════════════════════════════════════════════

interface Props {
  estudiantes: EstudianteData[];
  asignaturaId: number;
  puedeEditar: boolean;
  onReload: () => Promise<void>;
  onAbrirFicha?: (estudianteId: number) => void;
}

type DraftState = Record<number, string>;
type Fase = 'completiva' | 'extraordinaria' | 'especial';

// ─── Helpers de cálculo (mismas fórmulas que el backend/tabla oficial) ───
const pct = (v: number | null | undefined, f: number): string =>
  v == null ? '—' : (Math.round(v * f * 10) / 10).toFixed(1).replace(/\.0$/, '');

const fmtInt = (v: number | null | undefined): string =>
  v == null ? '—' : Math.round(v).toString();

const ultimaFaseCargada = (ev: any): Fase | null => {
  if (ev.ce != null) return 'especial';
  if (ev.ceex != null) return 'extraordinaria';
  if (ev.cec != null) return 'completiva';
  return null;
};

export const TabEvaluacionesExtra: React.FC<Props> = ({ estudiantes, asignaturaId, puedeEditar, onReload, onAbrirFicha }) => {
  const [drafts, setDrafts] = useState<DraftState>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [corrigiendoId, setCorrigiendoId] = useState<number | null>(null);
  const [mensaje, setMensaje] = useState<{ tipo: 'success' | 'error' | 'warning'; texto: string } | null>(null);

  const conPendiente = estudiantes.filter(
    e => e.evaluacion_extra?.fase_pendiente && !e.estudiante.retirado
  );
  const conResuelta = estudiantes.filter(
    e => e.evaluacion_extra && !e.evaluacion_extra.fase_pendiente && !e.estudiante.retirado
  );

  const guardarExtra = async (estId: number, fase: Fase) => {
    const valorStr = drafts[estId];
    if (!valorStr) {
      setMensaje({ tipo: 'error', texto: 'Indique la nota de la evaluación' });
      return;
    }
    const notaNum = parseFloat(valorStr);
    if (Number.isNaN(notaNum) || notaNum < 0 || notaNum > 100) {
      setMensaje({ tipo: 'error', texto: 'La nota debe estar entre 0 y 100' });
      return;
    }
    setSavingId(estId);
    try {
      await api.post('/calificaciones-secundaria/evaluacion-extra', {
        estudiante_id: estId,
        asignatura_id: asignaturaId,
        tipo: fase,
        nota: notaNum,
      });
      setMensaje({ tipo: 'success', texto: `Evaluación ${fase} registrada` });
      setDrafts(prev => { const n = { ...prev }; delete n[estId]; return n; });
      setCorrigiendoId(null);
      await onReload();
    } catch (err: any) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.error || 'Error al guardar' });
    } finally {
      setSavingId(null);
    }
  };

  if (conPendiente.length === 0 && conResuelta.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border p-10 text-center">
        <CheckCircle size={48} className="mx-auto text-green-300 mb-3" />
        <p className="text-gray-700 font-medium">No hay evaluaciones extra en esta materia</p>
        <p className="text-sm text-gray-500 mt-1">
          Aparecerá aquí automáticamente cuando un estudiante tenga CF &lt; 70 con las 4 competencias completas.
        </p>
      </div>
    );
  }

  const renderNombre = (e: EstudianteData) => onAbrirFicha ? (
    <button
      type="button"
      onClick={() => onAbrirFicha(e.estudiante.id)}
      className="font-medium text-blue-700 hover:text-blue-900 hover:underline text-left"
    >
      {e.estudiante.nombre_completo}
    </button>
  ) : (
    <span className="font-medium">{e.estudiante.nombre_completo}</span>
  );

  // ─── Encabezado agrupado (como el boletín oficial) ───
  const HeaderOficial = ({ conAcciones }: { conAcciones: boolean }) => (
    <thead>
      <tr className="text-xs">
        <th rowSpan={2} className="px-2 py-1 text-left bg-gray-50 border">Estudiante</th>
        <th rowSpan={2} className="px-2 py-1 text-center bg-gray-100 border font-bold">C.F.</th>
        <th colSpan={4} className="px-2 py-1 text-center bg-amber-50 text-amber-800 border font-bold">CALIF. COMPLETIVA</th>
        <th colSpan={4} className="px-2 py-1 text-center bg-orange-50 text-orange-800 border font-bold">CALIF. EXTRAORDINARIA</th>
        <th colSpan={3} className="px-2 py-1 text-center bg-red-50 text-red-800 border font-bold">EVAL. ESPECIAL</th>
        <th rowSpan={2} className="px-2 py-1 text-center bg-gray-50 border">Situación</th>
        {conAcciones && <th rowSpan={2} className="px-2 py-1 text-center bg-gray-50 border">Acción</th>}
      </tr>
      <tr className="text-[11px] text-gray-600">
        <th className="px-1 py-1 text-center bg-amber-50 border">50% C.F.</th>
        <th className="px-1 py-1 text-center bg-amber-50 border">C.E.C.</th>
        <th className="px-1 py-1 text-center bg-amber-50 border">50% C.E.C.</th>
        <th className="px-1 py-1 text-center bg-amber-100 border font-bold">C.C.F.</th>
        <th className="px-1 py-1 text-center bg-orange-50 border">30% C.F.</th>
        <th className="px-1 py-1 text-center bg-orange-50 border">C.E.EX</th>
        <th className="px-1 py-1 text-center bg-orange-50 border">70% C.E.EX</th>
        <th className="px-1 py-1 text-center bg-orange-100 border font-bold">C.EX.F.</th>
        <th className="px-1 py-1 text-center bg-red-50 border">C.F.</th>
        <th className="px-1 py-1 text-center bg-red-50 border">C.E.</th>
        <th className="px-1 py-1 text-center bg-red-100 border font-bold">Final</th>
      </tr>
    </thead>
  );

  // ─── Fila de un estudiante con desglose completo ───
  const FilaDesglose = ({ est, editable }: { est: EstudianteData; editable: boolean }) => {
    const ev: any = est.evaluacion_extra!;
    const cf = ev.cf_original as number;
    const cfRed = Math.round(cf);
    const fase: Fase | null = ev.fase_pendiente || (corrigiendoId === est.estudiante.id ? ultimaFaseCargada(ev) : null);
    const draft = drafts[est.estudiante.id] || '';
    const draftNum = draft !== '' ? parseFloat(draft) : null;
    const maxCE = 100 - cfRed;

    // Valores en vivo: si hay draft en la fase activa, calcular preview
    const cecVal = fase === 'completiva' && draftNum != null ? draftNum : ev.cec;
    const ceexVal = fase === 'extraordinaria' && draftNum != null ? draftNum : ev.ceex;
    const ceVal = fase === 'especial' && draftNum != null ? draftNum : ev.ce;
    const ccfLive = cecVal != null ? Math.round(cf * 0.5 + cecVal * 0.5) : null;
    const cexfLive = ceexVal != null ? Math.round(cf * 0.3 + ceexVal * 0.7) : null;
    const espLive = ceVal != null ? Math.round(cfRed + ceVal) : null;
    const esPreview = draftNum != null && !Number.isNaN(draftNum);

    // Input embebido en la celda de la fase activa
    const inputCelda = (f: Fase, placeholder: string) => (
      <input
        type="number"
        min={0}
        max={f === 'especial' ? maxCE : 100}
        step={1}
        placeholder={placeholder}
        value={draft}
        autoFocus={corrigiendoId === est.estudiante.id}
        onChange={e => setDrafts(prev => ({ ...prev, [est.estudiante.id]: e.target.value }))}
        className="w-16 px-1 py-1 text-center border-2 border-blue-400 rounded text-sm bg-blue-50 font-bold"
        title={f === 'especial' ? `C.E. complementario: máximo ${maxCE} puntos (CF ${cfRed} + CE ≤ 100)` : `Nota de la evaluación ${f}`}
      />
    );

    const celdaValor = (v: string, extra = '') => (
      <td className={`px-1 py-1 text-center border ${extra}`}>{v}</td>
    );
    const preview = (v: number | null, guardado: number | null | undefined) => {
      if (esPreview && v != null) return <span className="text-blue-700 font-bold italic">{v}*</span>;
      return <span className="font-bold">{fmtInt(guardado)}</span>;
    };

    const situacion = () => {
      if (ev.fase_pendiente) {
        return <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800 uppercase whitespace-nowrap">{ev.fase_pendiente} pendiente</span>;
      }
      const aprobado = (ev.nota_final ?? 0) >= 70;
      return (
        <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap ${aprobado ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {(ev.condicion_final || '').replace(/_/g, ' ')} {ev.nota_final != null ? `(${fmtInt(ev.nota_final)})` : ''}
        </span>
      );
    };

    return (
      <tr className="border-b hover:bg-gray-50 text-sm">
        <td className="px-2 py-1 border">{renderNombre(est)}</td>
        <td className="px-2 py-1 text-center border font-bold text-red-600">{fmtInt(cf)}</td>
        {/* COMPLETIVA */}
        {celdaValor(pct(cf, 0.5), 'bg-amber-50/50')}
        <td className="px-1 py-1 text-center border bg-amber-50/50">
          {editable && fase === 'completiva' ? inputCelda('completiva', 'Nota') : fmtInt(ev.cec)}
        </td>
        {celdaValor(cecVal != null ? pct(cecVal, 0.5) : '—', 'bg-amber-50/50')}
        <td className="px-1 py-1 text-center border bg-amber-100/60">{fase === 'completiva' ? preview(ccfLive, ev.completiva_final) : <span className="font-bold">{fmtInt(ev.completiva_final)}</span>}</td>
        {/* EXTRAORDINARIA */}
        {celdaValor(ev.completiva_final != null || fase === 'extraordinaria' ? pct(cf, 0.3) : '—', 'bg-orange-50/50')}
        <td className="px-1 py-1 text-center border bg-orange-50/50">
          {editable && fase === 'extraordinaria' ? inputCelda('extraordinaria', 'Nota') : fmtInt(ev.ceex)}
        </td>
        {celdaValor(ceexVal != null ? pct(ceexVal, 0.7) : '—', 'bg-orange-50/50')}
        <td className="px-1 py-1 text-center border bg-orange-100/60">{fase === 'extraordinaria' ? preview(cexfLive, ev.extraordinaria_final) : <span className="font-bold">{fmtInt(ev.extraordinaria_final)}</span>}</td>
        {/* ESPECIAL */}
        {celdaValor(ev.extraordinaria_final != null || fase === 'especial' ? String(cfRed) : '—', 'bg-red-50/50')}
        <td className="px-1 py-1 text-center border bg-red-50/50">
          {editable && fase === 'especial' ? inputCelda('especial', `máx ${maxCE}`) : fmtInt(ev.ce)}
        </td>
        <td className="px-1 py-1 text-center border bg-red-100/60">{fase === 'especial' ? preview(espLive, ev.especial_final) : <span className="font-bold">{fmtInt(ev.especial_final)}</span>}</td>
        {/* Situación */}
        <td className="px-2 py-1 text-center border">{situacion()}</td>
        {/* Acción */}
        {editable && (
          <td className="px-2 py-1 text-center border">
            {fase ? (
              <div className="flex gap-1 justify-center">
                <Button
                  variant="success"
                  size="sm"
                  loading={savingId === est.estudiante.id}
                  onClick={() => guardarExtra(est.estudiante.id, fase)}
                  icon={<Save size={13} />}
                >
                  Guardar
                </Button>
                {corrigiendoId === est.estudiante.id && (
                  <Button variant="secondary" size="sm" icon={<X size={13} />}
                    onClick={() => { setCorrigiendoId(null); setDrafts(prev => { const n = { ...prev }; delete n[est.estudiante.id]; return n; }); }}
                  />
                )}
              </div>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                icon={<Pencil size={13} />}
                title="Corregir la última evaluación cargada"
                onClick={() => setCorrigiendoId(est.estudiante.id)}
              >
                Corregir
              </Button>
            )}
          </td>
        )}
      </tr>
    );
  };

  return (
    <div className="space-y-4">
      {mensaje && <Alert variant={mensaje.tipo} onClose={() => setMensaje(null)}>{mensaje.texto}</Alert>}

      {/* Pendientes */}
      {conPendiente.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-1 flex items-center gap-2">
            <AlertTriangle className="text-amber-600" />
            Pendientes ({conPendiente.length})
          </h3>
          <p className="text-xs text-gray-500 mb-3">
            Escriba la nota en la casilla azul de la fase pendiente — el cálculo se muestra en vivo (valor con *) antes de guardar.
            Cascada MINERD: si C.C.F. &lt; 70 pasa a extraordinaria; si C.EX.F. &lt; 70 pasa a especial (C.E. = puntos que se suman al C.F.).
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <HeaderOficial conAcciones={puedeEditar} />
              <tbody>
                {conPendiente.map(est => <FilaDesglose key={est.estudiante.id} est={est} editable={puedeEditar} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Resueltas */}
      {conResuelta.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border p-4">
          <h3 className="font-bold text-lg mb-1 flex items-center gap-2 text-gray-600">
            <CheckCircle className="text-gray-400" />
            Resueltas ({conResuelta.length})
          </h3>
          <p className="text-xs text-gray-500 mb-3">
            Historial con el desglose completo. Use "Corregir" si una nota fue cargada por error.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <HeaderOficial conAcciones={puedeEditar} />
              <tbody>
                {conResuelta.map(est => <FilaDesglose key={est.estudiante.id} est={est} editable={puedeEditar} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
