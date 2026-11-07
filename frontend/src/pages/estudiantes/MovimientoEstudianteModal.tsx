import { useEffect, useMemo, useRef, useState } from 'react';
import api from '../../services/api';
import { Modal, Input, Select, Button } from '../../components/ui';

// TRAS-1 · Retirar, trasladar de curso/tanda o reactivar SIN perder historial.
// El servidor prepara todo (números, referencias, conflictos, asignaturas) y
// es quien valida; aquí solo se muestra y se confirma. Nunca se borra, mueve
// ni corrige ninguna nota o asistencia.

export type TipoMovimiento = 'traslado' | 'retiro' | 'reactivacion';

interface Props {
  estudiante: { id: number; nombre_completo: string } | null;
  tipo: TipoMovimiento;
  onClose: () => void;
  onDone: (mensaje: string) => void;
}

interface Conflicto {
  asistencia_id: number;
  fecha: string;
  curso: string;
  asignatura: string | null;
  estado: string;
  explicacion: string;
}

const TITULOS: Record<TipoMovimiento, string> = {
  traslado: 'Trasladar de curso o tanda',
  retiro: 'Retirar estudiante',
  reactivacion: 'Reactivar estudiante',
};

const fmt = (iso?: string | null) => (iso ? iso.split('-').reverse().join('/') : '—');

export function MovimientoEstudianteModal({ estudiante, tipo, onClose, onDone }: Props) {
  const [prep, setPrep] = useState<any>(null);
  const [destino, setDestino] = useState<string>('');
  const [desde, setDesde] = useState<string>('');
  const [numero, setNumero] = useState<string>('');
  const [motivo, setMotivo] = useState('');
  const [conflictos, setConflictos] = useState<Conflicto[]>([]);
  const [fechaSugerida, setFechaSugerida] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);
  // Una solicitud por apertura: el doble clic o el reintento no duplican.
  const solicitud = useRef<string>('');

  useEffect(() => {
    if (!estudiante) return;
    solicitud.current = (globalThis.crypto && 'randomUUID' in globalThis.crypto)
      ? globalThis.crypto.randomUUID()
      : `mov-${estudiante.id}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setPrep(null); setDestino(''); setNumero(''); setMotivo('');
    setConflictos([]); setFechaSugerida(null); setError('');
    setDesde('');
  }, [estudiante?.id, tipo]);

  useEffect(() => {
    if (!estudiante) return;
    const params = new URLSearchParams({ tipo });
    if (destino) params.set('curso_destino_id', destino);
    if (desde) params.set('desde', desde);
    let vivo = true;
    api.get(`/estudiantes/${estudiante.id}/movimiento/preparar?${params.toString()}`)
      .then(r => {
        if (!vivo) return;
        setPrep(r.data);
        setConflictos(r.data.conflictos || []);
        setFechaSugerida(r.data.fecha_sugerida || null);
        // Reactivar: la primera fecha válida (nunca dentro del retiro).
        if (tipo === 'reactivacion' && r.data.desde_sugerido && !desde) setDesde(r.data.desde_sugerido);
        if (r.data.destino && !numero) setNumero(String(r.data.destino.numero_propuesto));
      })
      .catch(e => vivo && setError(e.response?.data?.message || e.response?.data?.error || 'No se pudo preparar'));
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estudiante?.id, tipo, destino, desde]);

  const puedeConfirmar = useMemo(() => {
    if (!desde) return false;
    if (tipo === 'traslado' && (!destino || !numero)) return false;
    // Una fecha que contradice marcas existentes no se puede confirmar: el
    // servidor la rechaza para no dejar ninguna asistencia fuera de cuenta.
    if (conflictos.length > 0) return false;
    return true;
  }, [desde, destino, numero, conflictos, tipo]);

  if (!estudiante) return null;

  const confirmar = async () => {
    setGuardando(true);
    setError('');
    try {
      const body: any = { desde, motivo: motivo || undefined, client_request_id: solicitud.current };
      let r;
      if (tipo === 'traslado') {
        r = await api.post(`/estudiantes/${estudiante.id}/traslado`,
          { ...body, curso_destino_id: Number(destino), no_lista: Number(numero) });
      } else if (tipo === 'retiro') {
        r = await api.post(`/estudiantes/${estudiante.id}/retiro`, body);
      } else {
        if (numero) body.no_lista = Number(numero);
        r = await api.post(`/estudiantes/${estudiante.id}/reactivar`, body);
      }
      onDone(`${estudiante.nombre_completo}: ${r.data.message}`);
    } catch (e: any) {
      const d = e.response?.data || {};
      if (d.error === 'CONFLICTOS_CON_LA_FECHA') {
        setConflictos(d.conflictos || []);
        setFechaSugerida(d.fecha_sugerida || null);
      }
      if (d.numero_propuesto && tipo !== 'retiro') setNumero(String(d.numero_propuesto));
      setError(d.message || d.error || 'No se pudo registrar el movimiento');
    } finally {
      setGuardando(false);
    }
  };

  const destinoInfo = prep?.destino;
  const asig = prep?.asignaturas;
  const refs = prep?.referencias_asistencia;

  return (
    <Modal
      isOpen={!!estudiante}
      onClose={onClose}
      title={`${TITULOS[tipo]} · ${estudiante.nombre_completo}`}
      size="xl"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button variant={tipo === 'retiro' ? 'danger' : 'primary'} onClick={confirmar}
                  loading={guardando} disabled={!puedeConfirmar || guardando}>
            {tipo === 'traslado' ? 'Confirmar traslado' : tipo === 'retiro' ? 'Confirmar retiro' : 'Confirmar reactivación'}
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-blue-900">
          <p><span className="font-medium">Curso actual:</span> {prep?.curso_actual?.nombre || '—'}
            {prep?.curso_actual?.no_lista ? ` · n.º ${prep.curso_actual.no_lista}` : ''}</p>
          <p className="text-xs mt-1">
            Una sola ficha: no se crea otra ni se borra, mueve o corrige ninguna nota o asistencia.
            {prep?.regla_fecha ? ` ${prep.regla_fecha}` : ''}
          </p>
        </div>

        {tipo === 'traslado' && (
          <Select
            label="Curso o tanda de destino *"
            value={destino}
            onChange={e => { setDestino(e.target.value); setNumero(''); }}
            options={(prep?.cursos_posibles || []).map((c: any) => ({ value: c.id, label: c.nombre }))}
            placeholder="Seleccionar curso del mismo grado"
          />
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input type="date" label="Desde qué día *" value={desde} onChange={e => setDesde(e.target.value)}
                 min={prep?.ano_escolar?.inicio || undefined} max={prep?.ano_escolar?.fin || undefined} />
          {(tipo === 'traslado' || tipo === 'reactivacion') && (
            <Input type="number" min={1}
                   label={tipo === 'traslado' ? 'Número de lista en el destino *' : 'Número de lista (si el suyo está ocupado)'}
                   value={numero} onChange={e => setNumero(e.target.value)} />
          )}
        </div>

        {tipo === 'traslado' && destinoInfo && (
          <details className="bg-gray-50 border border-gray-200 rounded-lg p-3">
            <summary className="cursor-pointer font-medium text-gray-700">
              Número propuesto: {destinoInfo.numero_propuesto} · números ocupados o reservados en {destinoInfo.nombre}
            </summary>
            <p className="text-xs text-gray-500 mt-2">{destinoInfo.nota_numero}</p>
            <div className="flex flex-wrap gap-1 mt-2">
              {destinoInfo.numeros_ocupados.map((n: any) => (
                <span key={n.no_lista} title={`${n.nombre || ''} · ${n.estado}`}
                      className={`px-1.5 py-0.5 rounded text-xs ${n.estado === 'activo' ? 'bg-gray-200 text-gray-700' : 'bg-amber-100 text-amber-800'}`}>
                  {n.no_lista}{n.estado !== 'activo' ? ' (res.)' : ''}
                </span>
              ))}
            </div>
          </details>
        )}

        {prep?.numero_origen && tipo !== 'reactivacion' && (
          <p className="text-xs text-gray-600">
            Su n.º {prep.numero_origen.no_lista} en el curso actual: {prep.numero_origen.nota}
          </p>
        )}

        {refs && (
          <div className="text-xs text-gray-600 border-l-2 border-gray-300 pl-3">
            {refs.origen && <p>Curso actual: primera marca {fmt(refs.origen.primera)}, última {fmt(refs.origen.ultima)} ({refs.origen.marcas} marcas).</p>}
            {refs.destino && <p>Destino: primera marca {fmt(refs.destino.primera)}, última {fmt(refs.destino.ultima)}.</p>}
            <p className="italic">{refs.nota}</p>
          </div>
        )}

        {tipo === 'traslado' && asig && (asig.solo_origen.length > 0 || asig.solo_destino.length > 0) && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-900">
            <p className="font-medium">Asignaturas distintas entre los dos cursos</p>
            {asig.solo_origen.length > 0 && (
              <p className="text-xs mt-1">Solo en el curso actual: {asig.solo_origen.map((a: any) =>
                `${a.nombre}${a.competencias_con_nota ? ` (${a.competencias_con_nota} competencias con nota)` : ''}`).join(', ')}</p>
            )}
            {asig.solo_destino.length > 0 && (
              <p className="text-xs mt-1">Solo en el destino: {asig.solo_destino.map((a: any) => a.nombre).join(', ')}</p>
            )}
            <p className="text-xs mt-1">{asig.nota}</p>
          </div>
        )}

        {conflictos.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-900">
            <p className="font-medium">{conflictos.length} marca(s) de asistencia contradicen esa fecha</p>
            <p className="text-xs mt-1">Con esta fecha esas marcas quedarían fuera de su permanencia y dejarían de
              contar en porcentajes y documentos, así que no se registra el movimiento. Las marcas no se borran ni se
              corrigen: elija una fecha coherente con ellas o pida al docente que las corrija si son erróneas.</p>
            <ul className="text-xs mt-2 max-h-32 overflow-auto list-disc list-inside">
              {conflictos.slice(0, 30).map(c => (
                <li key={c.asistencia_id}>{fmt(c.fecha)} · {c.curso}{c.asignatura ? ` · ${c.asignatura}` : ''} · {c.estado}</li>
              ))}
            </ul>
            {fechaSugerida ? (
              <button type="button" onClick={() => setDesde(fechaSugerida)}
                      className="mt-2 text-xs font-medium text-blue-700 underline">
                Usar la fecha coherente con esas marcas: {fmt(fechaSugerida)}
              </button>
            ) : (
              <p className="mt-2 text-xs font-medium">Hay marcas en los dos cursos que se superponen: no existe una
                fecha que respete todas. Deben corregirse antes de registrar el movimiento.</p>
            )}
          </div>
        )}

        {tipo !== 'reactivacion' && (
          <Input label="Motivo (opcional)" value={motivo} onChange={e => setMotivo(e.target.value)}
                 placeholder={tipo === 'retiro' ? 'Ej. cambio de colegio, mudanza' : 'Ej. cambio de tanda'} />
        )}

        {prep?.tramos?.length > 1 && (
          <div className="text-xs text-gray-600">
            <p className="font-medium text-gray-700">Historial de cursos este año</p>
            <ul className="list-disc list-inside">
              {prep.tramos.map((t: any, i: number) => (
                <li key={i}>{t.curso} · n.º {t.no_lista ?? '—'} · {t.desde ? `desde ${fmt(t.desde)}` : 'desde el inicio'}
                  {t.hasta ? ` hasta ${fmt(t.hasta)}` : ' (vigente)'}</li>
              ))}
            </ul>
          </div>
        )}

        {error && <div className="bg-red-50 border border-red-300 text-red-800 rounded p-2 text-xs">{error}</div>}
      </div>
    </Modal>
  );
}

// Historial de cursos del año (expediente). Solo lectura.
export function HistorialCursos({ estudianteId }: { estudianteId: number }) {
  const [datos, setDatos] = useState<any>(null);
  useEffect(() => {
    let vivo = true;
    api.get(`/estudiantes/${estudianteId}/movimientos`).then(r => vivo && setDatos(r.data)).catch(() => {});
    return () => { vivo = false; };
  }, [estudianteId]);
  if (!datos || !datos.movimientos?.length) return null;
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm">
      <p className="font-medium text-gray-800 mb-1">Historial de cursos ({datos.ano_escolar})</p>
      <ul className="space-y-0.5 text-xs text-gray-700">
        {datos.tramos.map((t: any, i: number) => (
          <li key={i}>
            <span className="font-medium">{t.curso}</span> · n.º {t.no_lista ?? '—'} ·{' '}
            {t.desde ? `desde ${fmt(t.desde)}` : 'desde el inicio'}{t.hasta ? ` hasta ${fmt(t.hasta)}` : ' (vigente)'}
            {t.aviso_salida ? ` — ${t.aviso_salida}` : ''}
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-gray-500 mt-1">
        Registrado por: {datos.movimientos.map((m: any) => `${m.tipo} ${fmt(m.desde)} (${(m.registrado_en || '').slice(0, 16).replace('T', ' ')})`).join(' · ')}
      </p>
    </div>
  );
}
