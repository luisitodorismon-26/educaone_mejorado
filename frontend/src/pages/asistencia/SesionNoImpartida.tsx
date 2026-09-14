import { useState, useEffect } from 'react';
import api from '../../services/api';

/**
 * S1 — "No hubo clase".
 *
 * En el Registro Escolar en papel, cuando una clase prevista no se da, el
 * maestro no deja la columna vacía ni marca ausentes: conserva la fecha y
 * escribe la razón. Este panel es esa anotación.
 *
 * Mientras la sesión está declarada NO se puede pasar lista —el backend lo
 * rechaza con 409— así que el panel también apaga los botones de la tabla, para
 * que el profesor no descubra la regla a golpe de error.
 *
 * Solo Secundaria: en Primaria la asistencia es del curso, no de la materia, y
 * no hay una clase concreta que justificar.
 *
 * La granularidad es ASIGNATURA + FECHA, no bloque de horario: por eso no hay
 * selector de bloque y el POST no envía `horario_id`. Si la materia tiene
 * varias horas ese día, la justificación las cubre todas.
 */

export interface SesionNI {
  id: number;
  fecha: string;
  motivo_codigo: string;
  motivo: string;
  motivo_detalle: string | null;
  etiqueta: string;
  hora_inicio: string | null;
  hora_fin: string | null;
}

interface Motivo {
  codigo: string;
  nombre: string;
  etiqueta: string;
  requiere_detalle: boolean;
}

interface Props {
  cursoId: number;
  asignaturaId: number;
  fecha: string;
  puedeEditar: boolean;
  /** La sesión vigente de esta clase y fecha, o null. La dueña del estado es
   *  la página: necesita el mismo dato para apagar los botones de la tabla. */
  sesion: SesionNI | null;
  /** Se llama tras declarar o retirar, para que la página recargue. */
  onCambio: () => void;
}

export const SesionNoImpartidaPanel = ({
  cursoId, asignaturaId, fecha, puedeEditar, sesion, onCambio,
}: Props) => {
  const [motivos, setMotivos] = useState<Motivo[]>([]);
  const [abierto, setAbierto] = useState(false);
  const [codigo, setCodigo] = useState('');
  const [detalle, setDetalle] = useState('');
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    // El catálogo es una constante del sistema: se pide una sola vez y la UI no
    // inventa opciones que el backend luego rechazaría.
    api.get('/sesiones-no-impartidas/motivos')
      .then(r => setMotivos(r.data || []))
      .catch(() => setMotivos([]));
  }, []);

  useEffect(() => {
    setAbierto(false);
    setError('');
    setCodigo('');
    setDetalle('');
  }, [cursoId, asignaturaId, fecha]);

  const motivoElegido = motivos.find(m => m.codigo === codigo);
  const faltaDetalle = !!motivoElegido?.requiere_detalle && !detalle.trim();

  const declarar = async () => {
    if (!codigo || faltaDetalle) return;
    setGuardando(true);
    setError('');
    try {
      await api.post('/sesiones-no-impartidas', {
        curso_id: cursoId,
        asignatura_id: asignaturaId,
        fecha,
        motivo_codigo: codigo,
        motivo_detalle: detalle.trim() || undefined,
      });
      setAbierto(false);
      setCodigo('');
      setDetalle('');
      onCambio();
    } catch (err: any) {
      // El backend explica el caso concreto: la materia no toca ese día, o ya
      // hay asistencia capturada. Se muestra tal cual.
      setError(err.response?.data?.error || 'No se pudo registrar');
    } finally {
      setGuardando(false);
    }
  };

  const retirar = async () => {
    if (!sesion) return;
    setGuardando(true);
    setError('');
    try {
      await api.delete(`/sesiones-no-impartidas/${sesion.id}`);
      onCambio();
    } catch (err: any) {
      setError(err.response?.data?.error || 'No se pudo retirar');
    } finally {
      setGuardando(false);
    }
  };

  if (sesion) {
    return (
      <div className="bg-amber-50 border border-amber-300 rounded-lg p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-semibold text-amber-900">
              🚫 Esta clase no se impartió — {sesion.motivo}
            </p>
            {sesion.motivo_detalle && (
              <p className="text-sm text-amber-800 mt-1">{sesion.motivo_detalle}</p>
            )}
            <p className="text-xs text-amber-700 mt-2">
              La fecha conserva su columna en el Registro con la anotación
              «{sesion.etiqueta}», y no cuenta en el porcentaje de asistencia de
              ningún estudiante.
            </p>
          </div>
          {puedeEditar && (
            <button
              onClick={retirar}
              disabled={guardando}
              className="px-3 py-2 bg-white border border-amber-400 text-amber-900 rounded-lg hover:bg-amber-100 disabled:opacity-50 text-sm whitespace-nowrap"
            >
              {guardando ? 'Retirando…' : 'Sí hubo clase, retirar'}
            </button>
          )}
        </div>
        {error && <p className="text-sm text-red-700 mt-2">{error}</p>}
      </div>
    );
  }

  if (!puedeEditar) return null;

  if (!abierto) {
    return (
      <div>
        <button
          onClick={() => setAbierto(true)}
          className="px-3 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 text-sm"
        >
          🚫 No hubo clase este día
        </button>
        {error && <p className="text-sm text-red-700 mt-2">{error}</p>}
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-300 rounded-lg p-4 space-y-3">
      <p className="font-medium text-slate-800">¿Por qué no se impartió la clase?</p>
      {/* La justificación es de la ASIGNATURA en esa FECHA, no de un bloque
          suelto: si la materia tiene dos horas ese día, cubre las dos. */}
      <p className="text-xs text-slate-500 -mt-1">
        Use esta opción solamente si esta asignatura no se impartió en ningún
        momento de este día.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {motivos.map(m => (
          <button
            key={m.codigo}
            onClick={() => setCodigo(m.codigo)}
            className={`px-3 py-2 rounded-lg border text-sm text-left ${
              codigo === m.codigo
                ? 'bg-blue-600 border-blue-600 text-white'
                : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
            }`}
          >
            {m.nombre}
          </button>
        ))}
      </div>

      {motivoElegido?.requiere_detalle && (
        <div>
          <label className="block text-sm font-medium mb-1">Detalle</label>
          <input
            type="text"
            value={detalle}
            maxLength={255}
            onChange={e => setDetalle(e.target.value)}
            placeholder="Escriba brevemente el motivo"
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      {codigo && (
        <p className="text-xs text-slate-500">
          En el Registro esta fecha quedará anotada como
          «{motivoElegido?.etiqueta}».
        </p>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={declarar}
          disabled={!codigo || faltaDetalle || guardando}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {guardando ? 'Guardando…' : 'Registrar'}
        </button>
        <button
          onClick={() => { setAbierto(false); setError(''); }}
          className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
};
