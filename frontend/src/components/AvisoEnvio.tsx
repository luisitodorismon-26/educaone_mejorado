import { useEffect, useRef, useState } from 'react';
import type { FalloEnvio } from '../utils/errorServidor';
import { crearControlConsultas } from '../utils/consultaVigente';

export interface ItemListaEnvio {
  id: string | number;
  texto: string;
  detalle?: string;
}

/**
 * Resultado de «Consultar lista». `items` es lo que se muestra en el aviso;
 * `aplicar` actualiza la lista de la página y SOLO se ejecuta si la consulta
 * sigue vigente al terminar (nunca con una respuesta vieja).
 */
export interface ResultadoConsultaLista {
  items: ItemListaEnvio[];
  aplicar?: () => void;
}

interface Props {
  /** Resultado de clasificarFalloEnvio, o un aviso local de validación (tipo 'rechazo'). */
  fallo: FalloEnvio | null;
  /** Texto extra solo para el caso incierto (p. ej. envío masivo). */
  nota?: string;
  /**
   * Lectura de la lista correspondiente. Nunca reenvía nada. Recibe una señal que
   * se cancela si la consulta deja de estar vigente. Debe LANZAR si la respuesta
   * no tiene el formato esperado (ver exigirLista): eso es un fallo de consulta.
   */
  consultar?: (signal: AbortSignal) => Promise<ResultadoConsultaLista>;
  /** Cómo se llama la lista que se consulta («Comunicados publicados»…). */
  descripcionLista?: string;
  /** Identifica el formulario (tipo de modal, nota en edición…). Si cambia, se invalida la consulta en vuelo. */
  contexto?: string;
}

const MAX_ITEMS = 5;

/**
 * Aviso de un envío fallido, pensado para ir DENTRO del formulario o modal.
 *
 *   · Rechazo: el servidor dijo que no; se muestra su explicación.
 *   · Incierto: el envío pudo haberse guardado. Ofrece «Consultar lista», que solo
 *     LEE la lista (no cierra el formulario, no borra el texto, no reenvía). Si la
 *     consulta falla o la respuesta tiene un formato inesperado, el aviso se mantiene.
 *
 * Una consulta en vuelo se invalida (y su petición se cancela) cuando cambia el
 * aviso, cambia el contexto del formulario, empieza otra consulta o el componente
 * se desmonta: su respuesta o su error ya no tocan el aviso ni la página.
 *
 * No reintenta. Ver un registro parecido en la lista no confirma por sí solo que
 * sea este envío; lo decide la persona.
 */
export const AvisoEnvio = ({ fallo, nota, consultar, descripcionLista = 'Últimos registros', contexto }: Props) => {
  const [estado, setEstado] = useState<'inicial' | 'consultando' | 'consultada' | 'fallo'>('inicial');
  const [items, setItems] = useState<ItemListaEnvio[]>([]);
  const [hora, setHora] = useState('');
  const control = useRef(crearControlConsultas());

  // Un aviso nuevo o un formulario distinto empiezan sin consulta, y la que
  // estuviera en vuelo deja de valer.
  useEffect(() => {
    control.current.invalidar();
    setEstado('inicial'); setItems([]); setHora('');
  }, [fallo, contexto]);

  // Al desmontar (cerrar el modal o el formulario), nada en vuelo debe aplicarse.
  useEffect(() => () => control.current.invalidar(), []);

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
    await control.current.ejecutar(consultar, (r) => {
      if (!r.ok) { setEstado('fallo'); return; }
      r.valor.aplicar?.();
      setItems(r.valor.items.slice(0, MAX_ITEMS));
      setHora(new Date().toLocaleTimeString('es-DO', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      setEstado('consultada');
    });
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
            <p data-lista-vacia>La lista no tiene registros.</p>
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
