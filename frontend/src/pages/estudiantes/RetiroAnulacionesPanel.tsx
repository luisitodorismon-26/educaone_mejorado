import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { Button, Input } from '../../components/ui';
import { TablaMarcas } from './MovimientoEstudianteModal';

// ════════════════════════════════════════════════════════════════════
// RET-R · Solo Dirección. Marcas anuladas por retiro (historial), su reversión
// auditada y la corrección de la fecha de retiro. Todo con vista previa del
// servidor; nada se restaura solo. El servidor vuelve a comprobarlo todo.
// ════════════════════════════════════════════════════════════════════

const fmt = (iso?: string | null) => (iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—');
const errorDe = (e: any, def: string) => e?.response?.data?.message || e?.response?.data?.error || def;

interface Anulada {
  asistencia_id: number; fecha: string; estado: string; curso: string | null; asignatura: string | null;
  anulada_en: string | null; motivo: string; retiro_desde: string | null;
  revertida_en: string | null; motivo_reversion: string | null;
  conflictos_reversion: { codigo: string; mensaje: string }[];
}

export function RetiroAnulacionesPanel({ estudianteId, retirado, onCambio }:
  { estudianteId: number; retirado: boolean; onCambio?: () => void }) {
  const [anuladas, setAnuladas] = useState<Anulada[] | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [motivoRev, setMotivoRev] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  // Corrección de la fecha de retiro.
  const [desde, setDesde] = useState('');
  const [motivoCorr, setMotivoCorr] = useState('');
  const [pv, setPv] = useState<any>(null);
  const [anular, setAnular] = useState(false);
  const [motivoAnul, setMotivoAnul] = useState('');
  const [confirmarPeriodos, setConfirmarPeriodos] = useState(false);
  // Reactivación que Dirección declara SOLO administrativa (delimita qué queda sin efecto).
  const [reacAdmin, setReacAdmin] = useState('');
  const [confirmarAdmin, setConfirmarAdmin] = useState(false);
  const [candidatas, setCandidatas] = useState<any[]>([]);
  const secRef = useRef(0);
  const solicitud = useRef('');

  const cargar = () => api.get(`/estudiantes/${estudianteId}/anulaciones`)
    .then(r => setAnuladas(r.data.anuladas || [])).catch(() => setAnuladas(null));
  useEffect(() => {
    setSel([]); setPv(null); setDesde(''); setReacAdmin(''); cargar();
    // Reactivaciones vigentes del año (las que podrían haber sido solo administrativas).
    api.get(`/estudiantes/${estudianteId}/movimientos`).then(r => setCandidatas(
      (r.data.movimientos || []).filter((m: any) => m.tipo === 'reactivacion' && !m.sin_efecto))).catch(() => setCandidatas([]));
  }, [estudianteId]);

  const revertir = async () => {
    if (!sel.length || !motivoRev.trim()) return;
    setOcupado(true); setMsg(null);
    try {
      await api.post(`/estudiantes/${estudianteId}/anulaciones/revertir`, { asistencia_ids: sel, motivo: motivoRev.trim() });
      setMsg({ ok: true, text: `Se revirtió la anulación de ${sel.length} marca(s): vuelven a contar.` });
      setSel([]); setMotivoRev(''); cargar(); onCambio?.();
    } catch (e: any) {
      setMsg({ ok: false, text: errorDe(e, 'No se pudo revertir') });
      cargar();
    } finally { setOcupado(false); }
  };

  const revisarCorreccion = async (fecha: string, reac: string = reacAdmin) => {
    const sec = ++secRef.current;
    setPv(null); setAnular(false); setConfirmarPeriodos(false); setConfirmarAdmin(false); setMsg(null);
    if (!fecha) return;
    try {
      const q = new URLSearchParams({ desde: fecha });
      if (reac) q.set('reactivacion_administrativa_id', reac);
      const r = await api.get(`/estudiantes/${estudianteId}/retiro/corregir/vista-previa?${q.toString()}`);
      if (sec !== secRef.current) return;                 // respuesta de otra fecha: se descarta
      setPv(r.data);
      solicitud.current = `corr-${estudianteId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    } catch (e: any) {
      if (sec === secRef.current) setMsg({ ok: false, text: errorDe(e, 'No se pudo revisar la fecha') });
    }
  };

  const corregir = async () => {
    if (!pv || pv.desde !== desde || String(pv.reactivacion_administrativa?.id || '') !== reacAdmin) return;
    setOcupado(true); setMsg(null);
    try {
      const body: any = { desde: pv.desde, motivo: motivoCorr.trim(), client_request_id: solicitud.current };
      if (pv.conflictos.length) {
        body.anular_marcas_posteriores = anular; body.motivo_anulacion = motivoAnul.trim();
        body.huella_vista_previa = pv.huella;
      }
      if (pv.notas_en_esos_periodos.length) body.confirmar_periodos_no_cursados = confirmarPeriodos;
      if (pv.reactivacion_administrativa) {
        body.reactivacion_administrativa_id = pv.reactivacion_administrativa.id;
        body.confirmar_reactivacion_administrativa = confirmarAdmin;
      }
      await api.post(`/estudiantes/${estudianteId}/retiro/corregir`, body);
      setMsg({ ok: true, text: `Fecha de retiro corregida: retirado desde el ${fmt(pv.desde)}.` });
      setPv(null); setDesde(''); setMotivoCorr(''); cargar(); onCambio?.();
    } catch (e: any) {
      setMsg({ ok: false, text: errorDe(e, 'No se pudo corregir') });
      revisarCorreccion(desde);
    } finally { setOcupado(false); }
  };

  if (anuladas === null) return null;                     // sin permiso (no es Dirección) o error
  const vigentes = anuladas.filter(a => !a.revertida_en);
  const puedeCorregir = !!pv && pv.desde === desde && motivoCorr.trim().length > 0
    && String(pv.reactivacion_administrativa?.id || '') === reacAdmin
    && (!pv.reactivacion_administrativa || confirmarAdmin)
    && (!pv.conflictos.length || (anular && motivoAnul.trim().length > 0))
    && (!pv.notas_en_esos_periodos.length || confirmarPeriodos);

  return (
    <div className="border border-amber-200 bg-amber-50/40 rounded-lg p-3 text-sm space-y-3" data-panel-anulaciones>
      {msg && (
        <div role="status" className={`text-xs rounded p-2 ${msg.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          {msg.text}
        </div>
      )}

      {anuladas.length > 0 && (
        <div>
          <p className="font-medium text-gray-800">Asistencias anuladas por retiro ({vigentes.length} vigentes)</p>
          <p className="text-xs text-gray-600">No cuentan en estadísticas, porcentajes, boletines ni Registro. Se conservan
            con su contenido, autor y fecha. Solo vuelven a contar con una reversión explícita.</p>
          <div className="max-h-52 overflow-auto mt-2">
            <table className="w-full text-xs">
              <thead><tr className="text-left text-gray-500">
                <th className="py-1 pr-2"></th><th className="pr-2">Fecha</th><th className="pr-2">Materia</th>
                <th className="pr-2">Marca</th><th className="pr-2">Anulada</th><th>Situación</th></tr></thead>
              <tbody>
                {anuladas.map(a => {
                  const bloqueada = !!a.revertida_en || a.conflictos_reversion.length > 0;
                  return (
                    <tr key={a.asistencia_id} className="border-t border-amber-100 align-top">
                      <td className="py-1 pr-2">
                        <input type="checkbox" disabled={bloqueada} checked={sel.includes(a.asistencia_id)}
                               aria-label={`Revertir ${fmt(a.fecha)}`}
                               onChange={e => setSel(s => e.target.checked ? [...s, a.asistencia_id]
                                 : s.filter(x => x !== a.asistencia_id))} />
                      </td>
                      <td className="pr-2 whitespace-nowrap">{fmt(a.fecha)}</td>
                      <td className="pr-2">{a.asignatura || 'General'}</td>
                      <td className="pr-2">{a.estado}</td>
                      <td className="pr-2">{fmt(a.anulada_en)} · {a.motivo}</td>
                      <td>{a.revertida_en ? `Revertida ${fmt(a.revertida_en)} (${a.motivo_reversion})`
                        : a.conflictos_reversion.length ? a.conflictos_reversion.map(c => c.mensaje).join(' ')
                        : 'Se puede revertir'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {sel.length > 0 && (
            <div className="flex flex-col sm:flex-row gap-2 mt-2 sm:items-end">
              <div className="flex-1">
                <Input label={`Motivo de la reversión (${sel.length} marca(s)) *`} value={motivoRev}
                       onChange={e => setMotivoRev(e.target.value)} />
              </div>
              <Button variant="secondary" onClick={revertir} disabled={!motivoRev.trim() || ocupado} loading={ocupado}>
                Revertir seleccionadas
              </Button>
            </div>
          )}
        </div>
      )}

      {retirado && (
        <div>
          <p className="font-medium text-gray-800">Corregir la fecha de retiro</p>
          <p className="text-xs text-gray-600">Para una fecha mal registrada, o una reactivación que fue solo
            administrativa (por ejemplo, para completar notas) y no un regreso a clases. Los movimientos anteriores se
            conservan como «sin efecto».</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
            <Input type="date" label="Retirado desde (inclusive) *" value={desde}
                   onChange={e => { setDesde(e.target.value); revisarCorreccion(e.target.value); }} />
            <Input label="Motivo de la corrección *" value={motivoCorr} onChange={e => setMotivoCorr(e.target.value)} />
          </div>
          {candidatas.length > 0 && (
            <div className="mt-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">
                ¿Alguna reactivación fue solo administrativa (no volvió a clases)?
              </label>
              <select className="w-full border rounded px-2 py-1.5 text-sm" value={reacAdmin} data-reac-admin
                      onChange={e => { setReacAdmin(e.target.value); revisarCorreccion(desde, e.target.value); }}>
                <option value="">No: solo corregir el retiro vigente (los regresos reales se conservan)</option>
                {candidatas.map((m: any) => (
                  <option key={m.id} value={m.id}>Reactivación desde {fmt(m.desde)}{m.motivo ? ` (${m.motivo})` : ''}</option>
                ))}
              </select>
            </div>
          )}
          {pv && pv.desde === desde && (
            <div className="mt-2 space-y-2 text-xs" data-vista-previa-correccion>
              <p>Último día de pertenencia: <strong>{fmt(pv.ultimo_dia)}</strong> (antes: {fmt(pv.fecha_retiro_actual)}).</p>
              {pv.deja_sin_efecto.length > 0 && (
                <p>Quedarán <strong>sin efecto</strong> (se conservan en el historial): {pv.deja_sin_efecto.map((m: any) =>
                  `${m.tipo} desde ${fmt(m.desde)}`).join(', ')}.</p>
              )}
              {pv.reactivacion_administrativa && (
                <label className="flex gap-2 bg-white border border-amber-300 rounded p-2">
                  <input type="checkbox" checked={confirmarAdmin} onChange={e => setConfirmarAdmin(e.target.checked)} />
                  <span>Confirmo que la reactivación desde {fmt(pv.reactivacion_administrativa.desde)} fue solo
                    administrativa: no volvió a clases.</span>
                </label>
              )}
              {pv.conflictos.length > 0 && (
                <div className="bg-white border border-red-200 rounded p-2">
                  <p className="font-medium text-red-800">{pv.conflictos.length} marca(s) quedarían fuera de su permanencia</p>
                  <p>{Object.entries(pv.resumen.por_estado).map(([k, v]) => `${k}: ${v}`).join(' · ')}</p>
                  <TablaMarcas marcas={pv.conflictos} />
                  <label className="flex gap-2 mt-1"><input type="checkbox" checked={anular}
                    onChange={e => setAnular(e.target.checked)} /> Confirmo su anulación.</label>
                  {anular && <Input label="Motivo de la anulación *" value={motivoAnul}
                                    onChange={e => setMotivoAnul(e.target.value)} />}
                </div>
              )}
              {pv.anuladas_que_quedarian_dentro.length > 0 && (
                <div className="text-amber-800">
                  <p>{pv.anuladas_que_quedarian_dentro.length} marca(s) anulada(s) quedarían dentro
                    de su permanencia: <strong>no se restauran solas</strong>; puede revertirlas después, una a una.</p>
                  <TablaMarcas marcas={pv.anuladas_que_quedarian_dentro} />
                </div>
              )}
              {pv.notas_en_esos_periodos.length > 0 && (
                <div className="bg-white border border-amber-300 rounded p-2">
                  <p className="font-medium">Con esta fecha, {pv.periodos_que_dejan_de_cursarse.map((p: number) => `P${p}`).join(', ')}
                    {' '}dejaría(n) de ser cursado(s) en este curso.</p>
                  <p>Notas ya registradas en ese período: {pv.notas_en_esos_periodos.length}. Se conservan en la base, pero
                    el boletín y el Registro no las imprimen como cursadas y no se pueden editar.</p>
                  <label className="flex gap-2 mt-1"><input type="checkbox" checked={confirmarPeriodos}
                    onChange={e => setConfirmarPeriodos(e.target.checked)} /> Lo confirmo.</label>
                </div>
              )}
              <Button variant="danger" onClick={corregir} disabled={!puedeCorregir || ocupado} loading={ocupado}>
                Confirmar corrección
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default RetiroAnulacionesPanel;
