import { useEffect, useState } from 'react';
import type { FalloEnvio } from '../utils/errorServidor';

export interface ItemListaEnvio {
  id: string | number;
  texto: string;
  detalle?: string;
}

interface Props {
  /** Resultado de clasificarFalloEnvio, o un aviso local de validación (tipo 'rechazo'). */
  fallo: FalloEnvio | null;
  /** Texto extra solo para el caso incierto (p. ej. envío masivo). */
  nota?: string;
  /** Lectura de la lista correspondiente. Nunca reenvía nada. */
  consultar?: () => Promise<ItemListaEnvio[]>;
  /** Cómo se llama la lista que se consulta («Comunicados publicados»…). */
  descripcionLista?: string;
}

const MAX_ITEMS = 5;

/**
 * Aviso de un envío fallido, pensado para ir DENTRO del formulario o modal.
 *
 *   · Rechazo: el servidor dijo que no; se muestra su explicación.
 *   · Incierto: el envío pudo haberse guardado. Ofrece «Consultar lista», que solo
 *     LEE la lista (no cierra el formulario, no borra el texto, no reenvía). Si la
 *     consulta falla, el aviso se mantiene.
 *
 * No reintenta. Ver un registro parecido en la lista no confirma por sí solo que
 * sea este envío; lo decide la persona.
 */
export const AvisoEnvio = ({ fallo, nota, consultar, descripcionLista = 'Últimos registros' }: Props) => {
  const [estado, setEstado] = useState<'inicial' | 'consultando' | 'consultada' | 'fallo'>('inicial');
  const [items, setItems] = useState<ItemListaEnvio[]>([]);
  const [hora, setHora] = useState('');

  // Cada fallo nuevo empieza sin consulta previa.
  useEffect(() => { setEstado('inicial'); setItems([]); setHora(''); }, [fallo]);

  if (!fallo) return null;

  if (fallo.tipo === 'rechazo') {
    return (
      <div role="alert" data-aviso-envio="rechazo"
        className="p-3 bg-red-50 border border-red-300 text-red-700 rounded-lg text-sm whitespace-pre-line">
        {fallo.mensaje}
      </div>
    );
  }

  const consultarLista = async () => {
    if (!consultar || estado === 'consultando') return;
    setEstado('consultando');
    try {
      const lista = await consultar();
      setItems(lista.slice(0, MAX_ITEMS));
      setHora(new Date().toLocaleTimeString('es-DO', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      setEstado('consultada');
    } catch {
      setEstado('fallo');
    }
  };

  return (
    <div role="alert" data-aviso-envio="incierto"
      className="p-3 bg-amber-50 border border-amber-300 text-amber-900 rounded-lg text-sm space-y-2">
      <p className="font-medium">{fallo.mensaje}</p>
      {nota && <p>{nota}</p>}
      {consultar && (
        <button type="button" onClick={consultarLista} disabled={estado === 'consultando'} data-consultar-lista
          className="px-3 py-1.5 bg-white border border-amber-400 rounded-lg hover:bg-amber-100 disabled:opacity-50">
          {estado === 'consultando' ? 'Consultando…' : 'Consultar lista'}
        </button>
      )}
      {estado === 'fallo' && (
        <p data-consulta="fallo">
          No se pudo consultar la lista. El aviso sigue vigente: no vuelva a enviarlo hasta poder comprobarlo.
        </p>
      )}
      {estado === 'consultada' && (
        <div data-consulta="ok" className="space-y-1">
          <p>{descripcionLista} (consultado a las {hora}):</p>
          {items.length ? (
            <ul className="list-disc pl-5">
              {items.map((i) => (
                <li key={i.id}>{i.texto}{i.detalle ? <span className="text-amber-700"> — {i.detalle}</span> : null}</li>
              ))}
            </ul>
          ) : (
            <p>La lista no tiene registros.</p>
          )}
          <p className="text-amber-700">
            Que aparezca uno parecido no confirma por sí solo este envío: compare la fecha y el contenido antes de decidir si enviarlo de nuevo.
          </p>
        </div>
      )}
    </div>
  );
};

export default AvisoEnvio;
