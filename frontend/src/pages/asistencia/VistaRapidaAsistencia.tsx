import { useEffect, useState } from 'react';
import api from '../../services/api';

/**
 * ASIS-DASH-1 · Vista rápida de la asistencia de un curso en una fecha, para
 * Dirección y Coordinación. SOLO LECTURA: no marca ni corrige nada.
 *
 * Primaria: la toma diaria del curso. Secundaria: una fila por materia con
 * clase ese día (según el horario), con su profesor y su propia toma. Faltar
 * a una materia nunca se presenta como "ausente del día".
 *
 * Sin marcas se muestra "Sin asistencia registrada": nunca se asume presente.
 */

interface PersonaLista { id: number; no_lista: number | null; nombre: string }
interface Toma {
  estado: 'registrada' | 'parcial' | 'sin_asistencia';
  total_estudiantes: number;
  presentes: number; ausentes: number; tardanzas: number; excusas: number; sin_marcar: number;
  lista_ausentes: PersonaLista[]; lista_tardanzas: PersonaLista[]; lista_excusas: PersonaLista[];
}
interface Bloque { hora_inicio: string; hora_fin: string; profesor: string | null }
interface Sesion extends Toma {
  asignatura_id: number; asignatura: string | null; profesor: string | null;
  bloques: Bloque[]; no_impartida: { motivo: string; detalle: string | null } | null;
  fuera_de_horario: boolean;
}
interface Respuesta {
  nivel: string; fecha: string; dia: string; dia_no_laborable: string | null;
  primaria?: Toma & { titular: string | null };
  secundaria?: { sesiones: Sesion[]; sin_clases_programadas: boolean };
}

const ETIQUETA: Record<Toma['estado'], { texto: string; clase: string }> = {
  registrada: { texto: 'Asistencia registrada', clase: 'bg-green-100 text-green-800' },
  parcial: { texto: 'Parcial', clase: 'bg-amber-100 text-amber-800' },
  sin_asistencia: { texto: 'Sin asistencia registrada', clase: 'bg-gray-200 text-gray-700' },
};

const Estado = ({ estado }: { estado: Toma['estado'] }) => (
  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ETIQUETA[estado].clase}`}>
    {ETIQUETA[estado].texto}
  </span>
);

const Conteos = ({ t }: { t: Toma }) => (
  <span className="text-sm text-gray-700">
    <b className="text-green-700">{t.presentes} P</b> / <b className="text-red-700">{t.ausentes} A</b> /{' '}
    <b className="text-yellow-700">{t.tardanzas} T</b> / <b className="text-blue-700">{t.excusas} E</b>
    {t.sin_marcar > 0 && <span className="text-gray-500"> · {t.sin_marcar} sin marcar</span>}
  </span>
);

const Listas = ({ t }: { t: Toma }) => {
  const grupos: [string, PersonaLista[], string][] = [
    ['Ausentes', t.lista_ausentes, 'text-red-700'],
    ['Tardanzas', t.lista_tardanzas, 'text-yellow-700'],
    ['Excusas', t.lista_excusas, 'text-blue-700'],
  ];
  if (!grupos.some(([, l]) => l.length)) return null;
  return (
    <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
      {grupos.map(([titulo, lista, color]) => lista.length > 0 && (
        <div key={titulo}>
          <div className={`font-semibold ${color}`}>{titulo} ({lista.length})</div>
          <ul className="text-gray-700">
            {lista.map(p => <li key={p.id}>{p.no_lista ? `${p.no_lista}. ` : ''}{p.nombre}</li>)}
          </ul>
        </div>
      ))}
    </div>
  );
};

export const VistaRapidaAsistencia = ({ cursoId, fecha, onAbrirMateria }: {
  cursoId: number; fecha: string; onAbrirMateria?: (asignaturaId: number) => void;
}) => {
  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let vigente = true;
    setDatos(null);
    setError('');
    api.get(`/asistencia/vista-rapida/${cursoId}?fecha=${fecha}`)
      .then(res => { if (vigente) setDatos(res.data); })
      .catch(err => { if (vigente) setError(err.response?.data?.error || 'No se pudo cargar la vista rápida'); });
    return () => { vigente = false; };
  }, [cursoId, fecha]);

  if (error) return <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{error}</div>;
  if (!datos) return <div className="p-3 text-sm text-gray-500">Cargando vista rápida…</div>;

  return (
    <div className="bg-white p-4 rounded-lg border shadow-sm space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-gray-800">📊 Vista rápida — {datos.dia} {datos.fecha.split('-').reverse().join('/')}</h2>
        {datos.dia_no_laborable && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-800">
            Día no laborable: {datos.dia_no_laborable}
          </span>
        )}
      </div>

      {datos.primaria && (
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Estado estado={datos.primaria.estado} />
            <Conteos t={datos.primaria} />
            {datos.primaria.titular && <span className="text-xs text-gray-500">· Titular: {datos.primaria.titular}</span>}
          </div>
          <Listas t={datos.primaria} />
          <p className="mt-2 text-xs text-gray-500">La lista completa del día está debajo.</p>
        </div>
      )}

      {datos.secundaria && (
        datos.secundaria.sesiones.length === 0 ? (
          <p className="text-sm text-gray-600">
            {datos.secundaria.sin_clases_programadas ? 'Este curso no tiene clases programadas este día.' : 'Sin asistencia registrada.'}
          </p>
        ) : (
          <ul className="divide-y">
            {datos.secundaria.sesiones.map(s => (
              <li key={s.asignatura_id} className="py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-gray-800">{s.asignatura || 'Asignatura'}</span>
                  <span className="text-sm text-gray-600">— {s.profesor || 'Sin profesor en horario'}</span>
                  {s.bloques.length > 0 && (
                    <span className="text-xs text-gray-500">
                      ({s.bloques.map(b => `${b.hora_inicio}–${b.hora_fin}`).join(', ')})
                    </span>
                  )}
                  {s.fuera_de_horario && <span className="text-xs text-purple-700">fuera de horario</span>}
                  {s.no_impartida
                    ? <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-800">No impartida: {s.no_impartida.motivo}</span>
                    : <><Estado estado={s.estado} />{s.estado !== 'sin_asistencia' && <Conteos t={s} />}</>}
                  {onAbrirMateria && (
                    <button type="button" onClick={() => onAbrirMateria(s.asignatura_id)}
                            className="ml-auto text-xs text-blue-600 hover:underline">
                      Ver lista completa →
                    </button>
                  )}
                </div>
                <Listas t={s} />
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
};

export default VistaRapidaAsistencia;
