import { useEffect, useRef } from 'react';

/**
 * EducaOne — refresco en vivo de una pantalla (v2.19.3-C).
 *
 * Dispara `alRefrescar` en los tres momentos en que los datos pueden haber
 * quedado viejos sin que el usuario haga nada:
 *
 *   1. El Service Worker recibió un Web Push y avisó con
 *      `{ tipo: 'educaone:refrescar' }`. Es el camino inmediato: el evento
 *      `push` llega al SW aunque la app esté abierta y enfocada.
 *   2. La pestaña vuelve a estar visible (`visibilitychange`).
 *   3. La ventana recupera el foco.
 *
 * NO reemplaza al polling de 30 s de MainLayout: ese sigue siendo la red de
 * seguridad para cuando no hay Push (permiso denegado, navegador sin soporte,
 * o un Service Worker viejo todavía sin actualizar).
 *
 * Detalles que importan:
 *
 * - El callback se guarda en un ref para que los listeners se registren UNA
 *   sola vez. Si dependiera del callback, que los componentes redefinen en
 *   cada render, estaríamos suscribiendo y desuscribiendo constantemente.
 * - `focus` y `visibilitychange` suelen dispararse juntos al volver a una
 *   pestaña. El intervalo mínimo evita que eso se convierta en dos llamadas
 *   idénticas a la API con milisegundos de diferencia.
 */

/** Tiempo mínimo entre dos refrescos, para colapsar eventos que llegan juntos. */
const MS_MINIMO_ENTRE_REFRESCOS = 1000;

export function useRefrescoEnVivo(alRefrescar: () => void) {
  const callbackRef = useRef(alRefrescar);
  const ultimoRef = useRef(0);

  // Mantener el ref apuntando siempre al callback más reciente.
  useEffect(() => {
    callbackRef.current = alRefrescar;
  });

  useEffect(() => {
    const disparar = () => {
      const ahora = Date.now();
      if (ahora - ultimoRef.current < MS_MINIMO_ENTRE_REFRESCOS) return;
      ultimoRef.current = ahora;
      try {
        callbackRef.current();
      } catch {
        /* un fallo al refrescar nunca debe romper la pantalla */
      }
    };

    const alMensajeDelServiceWorker = (evento: MessageEvent) => {
      if (evento.data?.tipo === 'educaone:refrescar') disparar();
    };

    const alCambiarVisibilidad = () => {
      if (document.visibilityState === 'visible') disparar();
    };

    const hayServiceWorker = typeof navigator !== 'undefined' && 'serviceWorker' in navigator;
    if (hayServiceWorker) {
      navigator.serviceWorker.addEventListener('message', alMensajeDelServiceWorker);
    }
    document.addEventListener('visibilitychange', alCambiarVisibilidad);
    window.addEventListener('focus', disparar);

    return () => {
      if (hayServiceWorker) {
        navigator.serviceWorker.removeEventListener('message', alMensajeDelServiceWorker);
      }
      document.removeEventListener('visibilitychange', alCambiarVisibilidad);
      window.removeEventListener('focus', disparar);
    };
  }, []);
}

export default useRefrescoEnVivo;
