import { useState, useEffect } from 'react';
import { Bell, BellOff, Check, Loader2 } from 'lucide-react';
import { estadoPush, activarPush, desactivarPush, EstadoPush } from '../../services/push';

/**
 * Botón "Activar notificaciones en este dispositivo" (Fase C).
 *
 * Va dentro del panel de la campana: es el momento en que la persona ya está
 * pensando en notificaciones.
 *
 * El permiso del navegador se pide ÚNICAMENTE dentro del onClick. Nunca al
 * montar el componente: un prompt automático se rechaza por reflejo, y una vez
 * denegado el navegador no vuelve a preguntar.
 *
 * Si el push no está disponible (navegador viejo, servidor sin VAPID, permiso
 * denegado), el componente no se dibuja o muestra el motivo, y EducaOne sigue
 * funcionando con la campana interna.
 */
export default function BotonActivarNotificaciones() {
  const [estado, setEstado] = useState<EstadoPush | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    // Solo CONSULTA el estado. No dispara ningún prompt de permiso.
    estadoPush().then((e) => {
      if (vivo) setEstado(e);
    });
    return () => {
      vivo = false;
    };
  }, []);

  // Sin soporte o sin VAPID en el servidor: no mostramos nada. No tiene sentido
  // ofrecer algo que no se puede activar.
  if (estado === null || estado === 'no-soportado' || estado === 'no-disponible') {
    return null;
  }

  if (estado === 'denegado') {
    return (
      <div className="p-3 border-t bg-amber-50">
        <p className="text-[10px] text-amber-800 flex items-start gap-1.5">
          <BellOff size={12} className="flex-shrink-0 mt-0.5" />
          <span>
            Las notificaciones están bloqueadas en este navegador. Puede habilitarlas
            desde la configuración del sitio. Mientras tanto seguirá viendo todo acá.
          </span>
        </p>
      </div>
    );
  }

  const alActivar = async () => {
    setOcupado(true);
    setError(null);
    const r = await activarPush();
    setEstado(r.estado);
    if (!r.ok && r.error) setError(r.error);
    setOcupado(false);
  };

  const alDesactivar = async () => {
    setOcupado(true);
    setError(null);
    await desactivarPush();
    setEstado('no-activadas');
    setOcupado(false);
  };

  return (
    <div className="p-3 border-t bg-gray-50">
      {estado === 'activadas' ? (
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] text-green-700 font-medium flex items-center gap-1">
            <Check size={12} /> Activadas en este dispositivo
          </span>
          <button
            onClick={alDesactivar}
            disabled={ocupado}
            className="text-[10px] text-gray-500 hover:underline disabled:opacity-50"
          >
            Desactivar
          </button>
        </div>
      ) : (
        <button
          onClick={alActivar}
          disabled={ocupado}
          className="w-full flex items-center justify-center gap-1.5 text-[11px] font-medium text-blue-600 hover:text-blue-700 disabled:opacity-50"
        >
          {ocupado ? <Loader2 size={12} className="animate-spin" /> : <Bell size={12} />}
          {ocupado ? 'Activando…' : 'Activar notificaciones en este dispositivo'}
        </button>
      )}
      {error && <p className="text-[10px] text-red-600 mt-1.5">{error}</p>}
    </div>
  );
}
