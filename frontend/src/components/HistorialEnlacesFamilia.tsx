import { useEffect, useRef, useState } from 'react';
import { Ban, Loader2 } from 'lucide-react';
import api from '../services/api';
import { mensajeDeError } from '../utils/errorServidor';

/**
 * FAM-DOC-1 · Historial de enlaces compartidos con la familia de UN estudiante:
 * todas las versiones de cualquier año y período (también de estudiantes
 * retirados o sin curso actual), con fecha, estado y «Anular enlace».
 *
 * Lo usan el panel «Compartir reportes» (Notas por período) y la ficha del
 * estudiante. Lee `GET /api/documentos-familia/estudiante/{id}/versiones` y anula
 * con `POST /api/documentos-familia/{id}/anular`: mismos permisos que el panel
 * (dirección y coordinación, por colegio y división). Anular no borra el PDF.
 */
export interface VersionDoc {
  id: number; ano: string | null; periodo: number; version: number;
  estado: 'activo' | 'reemplazado' | 'anulado'; fecha_preparado: string | null; fecha_anulado: string | null; visitas: number;
}

const ESTADO_VERSION: Record<VersionDoc['estado'], string> = {
  activo: 'Enlace activo', reemplazado: 'Reemplazado (el enlace sigue abriendo)', anulado: 'Anulado',
};
const fecha = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('es-DO') : '—';

interface Props {
  estudianteId: number;
  nombre: string;
  /** Texto del botón que abre la lista. */
  textoAbrir?: string;
  /** Abre la lista al montarse (la ficha la muestra directamente). */
  abiertaAlInicio?: boolean;
  /** Cambiar este número recarga la lista si está abierta (p. ej. tras una versión nueva). */
  recarga?: number;
  /** Aviso al contenedor de que se anuló un documento. */
  onAnulado?: (docId: number) => void;
}

export const HistorialEnlacesFamilia = ({ estudianteId, nombre, textoAbrir = 'Versiones y enlaces anteriores',
  abiertaAlInicio = false, recarga = 0, onAnulado }: Props) => {
  const [abierta, setAbierta] = useState(abiertaAlInicio);
  const [lista, setLista] = useState<VersionDoc[] | null>(null);
  const [error, setError] = useState('');
  const [anulando, setAnulando] = useState<number | null>(null);
  // Respuestas de otro estudiante o tras desmontar se descartan.
  const generacion = useRef(0);
  const enCurso = useRef(false);

  const cargar = async () => {
    const g = ++generacion.current;
    setLista(null); setError('');
    try {
      const res = await api.get(`/documentos-familia/estudiante/${estudianteId}/versiones`);
      if (g === generacion.current) setLista(res.data.versiones || []);
    } catch (e: any) {
      if (g !== generacion.current) return;
      setLista([]);
      setError(await mensajeDeError(e, { porDefecto: 'No se pudieron cargar los enlaces de este estudiante.' }));
    }
  };

  useEffect(() => {
    if (abierta) cargar();
    return () => { generacion.current += 1; };
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [abierta, estudianteId, recarga]);

  const anular = async (v: VersionDoc) => {
    if (enCurso.current) return;
    if (!window.confirm(`¿Anular el enlace del período ${v.periodo} (${v.ano || '—'}, versión ${v.version}) de ${nombre}?\n\nQuien lo tenga dejará de poder abrirlo. El PDF no se borra.`)) return;
    enCurso.current = true; setAnulando(v.id); setError('');
    const g = generacion.current;
    try {
      await api.post(`/documentos-familia/${v.id}/anular`, { motivo: 'Anulado desde el historial de enlaces' });
      onAnulado?.(v.id);
      if (g === generacion.current) await cargar();
    } catch (e: any) {
      if (g === generacion.current) setError(await mensajeDeError(e, { porDefecto: 'No se pudo anular el enlace.', operacion: 'guardado' }));
    } finally { enCurso.current = false; setAnulando(null); }
  };

  if (!abierta) {
    return (
      <button onClick={() => setAbierta(true)} className="text-sm font-semibold text-blue-700 hover:underline" data-historial-enlaces>
        {textoAbrir}
      </button>
    );
  }
  return (
    <div className="space-y-2" data-historial-enlaces>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-gray-900">Enlaces compartidos · {nombre}</p>
        {!abiertaAlInicio && <button onClick={() => setAbierta(false)} className="text-xs text-gray-500 hover:underline">Ocultar</button>}
      </div>
      {lista === null && <p className="text-xs text-gray-500 flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Cargando…</p>}
      {error && <p className="text-xs text-red-700 whitespace-pre-line" role="alert">{error}</p>}
      {lista && lista.length === 0 && !error && <p className="text-xs text-gray-500">Todavía no se ha preparado ningún reporte para su familia.</p>}
      {lista && lista.length > 0 && (
        <ul className="divide-y rounded-lg border border-gray-200 text-sm">
          {lista.map(v => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-3 py-2">
              <div className="min-w-0">
                <p className="text-gray-900">{v.ano || '—'} · Período {v.periodo} · versión {v.version}</p>
                <p className="text-xs text-gray-500">Preparado el {fecha(v.fecha_preparado)} · {ESTADO_VERSION[v.estado]}{v.estado === 'anulado' ? ` el ${fecha(v.fecha_anulado)}` : ''}</p>
              </div>
              {v.estado !== 'anulado' && (
                <button onClick={() => anular(v)} disabled={anulando !== null}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:underline disabled:opacity-50 shrink-0">
                  <Ban size={12} /> {anulando === v.id ? 'Anulando…' : 'Anular enlace'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-gray-500">Anular no borra el PDF: solo deja de abrirse el enlace.</p>
    </div>
  );
};

export default HistorialEnlacesFamilia;
