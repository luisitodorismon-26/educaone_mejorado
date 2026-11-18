import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { Button, Input, Alert } from '../../components/ui';

// ════════════════════════════════════════════════════════════════════
// ENT-B · Vacaciones por rango (fecha inicial y final, ambas incluidas).
// Primero se revisa (vista previa, sin escribir nada) y solo después se
// confirma. El servidor vuelve a comprobarlo todo al confirmar.
// ════════════════════════════════════════════════════════════════════

interface Rango { id: number; nombre: string; fecha_inicio: string; fecha_fin: string; dias: number }
interface Analisis {
  nombre: string; fecha_inicio: string; fecha_fin: string;
  dias_calendario: number; dias_lectivos_excluidos: number;
  ya_no_laborables: Array<{ fecha: string; nombre: string; tipo: string }>;
  conflictos_asistencia: Array<{ fecha: string; curso_id: number | null; curso: string; marcas: number }>;
  total_marcas: number;
  solapes: Rango[];
  ya_registrado: Rango | null;
  sesiones_no_impartidas: number;
  puede_confirmar: boolean;
}

const fmt = (f: string) => new Date(f + 'T12:00:00').toLocaleDateString('es-DO', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
const errorDe = (e: any, def: string) => e?.response?.data?.message || e?.response?.data?.error || def;

export const VacacionesRangoSection: React.FC<{ onCambio: () => void }> = ({ onCambio }) => {
  const [rangos, setRangos] = useState<Rango[]>([]);
  const [form, setForm] = useState({ nombre: '', fecha_inicio: '', fecha_fin: '' });
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error' | 'warning'; text: string } | null>(null);

  // Cada revisión tiene su número; cambiar el formulario también lo avanza.
  // Una respuesta que llega con un número viejo se descarta.
  const secRef = useRef(0);
  const confirmandoRef = useRef(false);
  const claveDe = (x: { nombre: string; fecha_inicio: string; fecha_fin: string }) =>
    [x.nombre.trim(), x.fecha_inicio, x.fecha_fin].join('|');
  // La vista previa solo vale para el contenido EXACTO que se revisó (el que
  // devolvió el servidor) y mientras el formulario siga diciendo lo mismo.
  const vigente = !!analisis && claveDe(analisis) === claveDe(form);

  const cargar = () => api.get('/vacaciones').then(r => setRangos(r.data || [])).catch(() => setRangos([]));
  useEffect(() => { cargar(); }, []);

  // Cambiar el formulario invalida la revisión anterior: hay que revisar de nuevo.
  const cambiar = (k: keyof typeof form, v: string) => {
    secRef.current += 1;
    setForm(f => ({ ...f, [k]: v }));
    setAnalisis(null);
    // Una revisión pendiente ya es obsoleta: no debe impedir revisar lo nuevo.
    if (!confirmandoRef.current) setOcupado(false);
  };

  const revisar = async () => {
    setMsg(null);
    if (!form.nombre.trim() || !form.fecha_inicio || !form.fecha_fin) {
      setMsg({ type: 'error', text: 'Indique nombre, fecha inicial y fecha final.' });
      return;
    }
    const sec = ++secRef.current;
    const enviado = { nombre: form.nombre.trim(), fecha_inicio: form.fecha_inicio, fecha_fin: form.fecha_fin };
    setAnalisis(null);
    setOcupado(true);
    try {
      const r = await api.post('/vacaciones/vista-previa', enviado);
      if (sec !== secRef.current) return;      // respuesta de una revisión anterior
      setAnalisis(r.data);
    } catch (e: any) {
      if (sec !== secRef.current) return;
      setAnalisis(null);
      setMsg({ type: 'error', text: errorDe(e, 'No se pudo revisar el rango') });
    } finally { if (sec === secRef.current) setOcupado(false); }
  };

  const confirmar = async () => {
    if (!analisis || !vigente || !analisis.puede_confirmar || ocupado) return;
    // Se confirma EXACTAMENTE el rango mostrado, no lo que diga el formulario.
    const mostrado = { nombre: analisis.nombre, fecha_inicio: analisis.fecha_inicio, fecha_fin: analisis.fecha_fin };
    const sec = ++secRef.current;
    confirmandoRef.current = true;
    setOcupado(true);
    setMsg(null);
    try {
      const r = await api.post('/vacaciones', mostrado);
      setMsg({ type: 'success', text: r.data?.ya_existia ? 'Ese rango ya estaba registrado; no se duplicó.' : `Vacaciones registradas: ${mostrado.nombre}.` });
      setAnalisis(null);
      if (sec === secRef.current) setForm({ nombre: '', fecha_inicio: '', fecha_fin: '' });
      cargar(); onCambio();
    } catch (e: any) {
      // Si algo cambió desde la revisión (una lista pasada, otro rango), se
      // muestra el análisis actualizado que devuelve el servidor, solo si el
      // formulario no cambió mientras tanto.
      if (sec === secRef.current && e?.response?.data?.analisis) setAnalisis(e.response.data.analisis);
      else setAnalisis(null);
      setMsg({ type: 'error', text: errorDe(e, 'No se pudo registrar el rango') });
    } finally { confirmandoRef.current = false; setOcupado(false); }
  };

  const quitar = async (r: Rango) => {
    if (!window.confirm(`¿Quitar «${r.nombre}» (${fmt(r.fecha_inicio)} – ${fmt(r.fecha_fin)})?\n\n` +
      'Esas fechas volverán a contar como días de clase y se podrá pasar asistencia en ellas.')) return;
    setOcupado(true);
    try {
      await api.delete(`/vacaciones/${r.id}`);
      setMsg({ type: 'success', text: `Se quitó «${r.nombre}».` });
      cargar(); onCambio();
    } catch (e: any) {
      setMsg({ type: 'error', text: errorDe(e, 'No se pudo quitar el rango') });
    } finally { setOcupado(false); }
  };

  return (
    <div className="mb-6 border rounded-lg p-4 bg-blue-50/40" data-seccion="vacaciones-rango">
      <h4 className="font-semibold text-gray-800 mb-1">🏖️ Vacaciones por rango</h4>
      <p className="text-sm text-gray-600 mb-3">
        Fecha inicial y final, ambas incluidas. En ese rango no se pasa asistencia y esos días no cuentan como
        días de clase en resúmenes, boletines y Registro. Las notas se siguen trabajando con sus permisos habituales.
      </p>

      {msg && <div className="mb-3"><Alert variant={msg.type} onClose={() => setMsg(null)}>{msg.text}</Alert></div>}

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
        <Input label="Nombre *" placeholder="Ej: Vacaciones de Navidad" value={form.nombre}
               onChange={e => cambiar('nombre', e.target.value)} />
        <Input label="Desde (incluida) *" type="date" value={form.fecha_inicio}
               onChange={e => cambiar('fecha_inicio', e.target.value)} />
        <Input label="Hasta (incluida) *" type="date" value={form.fecha_fin}
               onChange={e => cambiar('fecha_fin', e.target.value)} />
        <Button variant="secondary" onClick={revisar} loading={ocupado && !analisis}>Revisar rango</Button>
      </div>

      {analisis && vigente && (
        <div className="mt-4 border rounded-lg bg-white p-4 space-y-3" data-vista-previa>
          <p className="text-sm">
            <strong>{analisis.nombre}</strong>: del <strong>{fmt(analisis.fecha_inicio)}</strong> al{' '}
            <strong>{fmt(analisis.fecha_fin)}</strong> — {analisis.dias_calendario} día(s) de calendario;{' '}
            <strong>{analisis.dias_lectivos_excluidos}</strong> día(s) de clase dejarán de contarse.
          </p>
          {analisis.ya_no_laborables.length > 0 && (
            <p className="text-sm text-gray-600">
              Ya no laborables (se mantienen como están): {analisis.ya_no_laborables.map(d => `${fmt(d.fecha)} ${d.nombre}`).join('; ')}.
            </p>
          )}
          {analisis.sesiones_no_impartidas > 0 && (
            <p className="text-sm text-gray-600">
              {analisis.sesiones_no_impartidas} registro(s) de «No hubo clase» en el rango: se conservan sin cambios.
            </p>
          )}
          {analisis.ya_registrado && analisis.solapes.length === 0 && (
            <Alert variant="info">Este mismo rango ya está registrado. Confirmar no lo duplicará.</Alert>
          )}
          {analisis.solapes.length > 0 && (
            <div role="alert" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">
              <strong>Se solapa con otro rango:</strong>{' '}
              {analisis.solapes.map(r => `«${r.nombre}» (${fmt(r.fecha_inicio)} – ${fmt(r.fecha_fin)})`).join('; ')}.
              Ajuste las fechas o quite el otro rango.
            </div>
          )}
          {analisis.total_marcas > 0 && (
            <div role="alert" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3" data-conflictos>
              <strong>Hay {analisis.total_marcas} marca(s) de asistencia en el rango.</strong> No se puede registrar
              mientras existan; no se borrará ni anulará ninguna. Revíselas con quien las registró:
              <ul className="list-disc ml-5 mt-1 max-h-40 overflow-y-auto">
                {analisis.conflictos_asistencia.map(c => (
                  <li key={`${c.fecha}-${c.curso_id}`}>{fmt(c.fecha)} — {c.curso}: {c.marcas} marca(s)</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setAnalisis(null)} disabled={ocupado}>Cancelar</Button>
            <Button onClick={confirmar} disabled={!vigente || !analisis.puede_confirmar || ocupado} loading={ocupado}>
              Confirmar vacaciones
            </Button>
          </div>
        </div>
      )}

      {rangos.length > 0 && (
        <div className="mt-4 space-y-2" data-rangos>
          {rangos.map(r => (
            <div key={r.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white border border-blue-200 rounded-lg p-3">
              <div>
                <p className="font-medium text-gray-800">{r.nombre}</p>
                <p className="text-sm text-gray-500">{fmt(r.fecha_inicio)} – {fmt(r.fecha_fin)} · {r.dias} día(s)</p>
              </div>
              <Button variant="secondary" onClick={() => quitar(r)} disabled={ocupado}>Quitar</Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default VacacionesRangoSection;
