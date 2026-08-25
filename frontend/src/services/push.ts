import api from './api';

/**
 * EducaOne — Web Push en el navegador (Fase C).
 *
 * Reglas que sostienen este módulo:
 *
 * 1. NUNCA se pide el permiso por iniciativa propia. Solo cuando la persona
 *    pulsa "Activar notificaciones en este dispositivo". Un prompt automático
 *    al cargar la página hace que el usuario lo rechace por reflejo, y una vez
 *    denegado el navegador no vuelve a preguntar nunca más.
 *
 * 2. Si el permiso está denegado o el navegador no soporta push, EducaOne
 *    funciona igual: la campana interna y su refresco cada 30 s no dependen
 *    de nada de esto.
 *
 * 3. Al cerrar sesión se da de baja SOLO este dispositivo. El teléfono personal
 *    del profesor no se toca cuando cierra sesión en la PC del aula.
 */

export type EstadoPush =
  | 'no-soportado'     // el navegador no tiene Push API o Service Worker
  | 'no-disponible'    // el servidor no tiene VAPID configurado
  | 'denegado'         // la persona bloqueó las notificaciones
  | 'activadas'
  | 'no-activadas';

/** La VAPID public key viaja en base64url y pushManager la exige como Uint8Array. */
function base64UrlAUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const salida = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) {
    salida[i] = raw.charCodeAt(i);
  }
  return salida;
}

export function pushSoportado(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/** Suscripción de ESTE navegador, si ya existe. */
export async function obtenerSuscripcionActual(): Promise<PushSubscription | null> {
  if (!pushSoportado()) return null;
  try {
    const registro = await navigator.serviceWorker.ready;
    return await registro.pushManager.getSubscription();
  } catch {
    return null;
  }
}

/** Estado a mostrar en la UI. No dispara ningún prompt de permiso. */
export async function estadoPush(): Promise<EstadoPush> {
  if (!pushSoportado()) return 'no-soportado';
  if (Notification.permission === 'denied') return 'denegado';

  try {
    const { data } = await api.get('/push/clave-publica');
    if (!data?.disponible) return 'no-disponible';
  } catch {
    return 'no-disponible';
  }

  const sub = await obtenerSuscripcionActual();
  return sub ? 'activadas' : 'no-activadas';
}

/**
 * Activar en este dispositivo. Se llama SOLO desde el onClick del botón.
 *
 * Devuelve el estado resultante para que la UI lo muestre sin adivinar.
 */
export async function activarPush(): Promise<{ ok: boolean; estado: EstadoPush; error?: string }> {
  if (!pushSoportado()) {
    return { ok: false, estado: 'no-soportado', error: 'Este navegador no soporta notificaciones.' };
  }

  let clavePublica = '';
  try {
    const { data } = await api.get('/push/clave-publica');
    if (!data?.disponible || !data?.clave_publica) {
      return { ok: false, estado: 'no-disponible', error: 'El servidor no tiene las notificaciones configuradas.' };
    }
    clavePublica = data.clave_publica;
  } catch {
    return { ok: false, estado: 'no-disponible', error: 'No se pudo consultar la configuración de notificaciones.' };
  }

  // El permiso se pide acá, dentro del gesto del usuario.
  let permiso = Notification.permission;
  if (permiso === 'default') {
    permiso = await Notification.requestPermission();
  }
  if (permiso !== 'granted') {
    return {
      ok: false,
      estado: 'denegado',
      error: 'Las notificaciones quedaron bloqueadas. Puede habilitarlas desde la configuración del navegador.',
    };
  }

  try {
    const registro = await navigator.serviceWorker.ready;

    // Reutilizar la suscripción existente en vez de crear otra: pushManager
    // devolvería un endpoint distinto y el dispositivo quedaría duplicado.
    let sub = await registro.pushManager.getSubscription();
    if (!sub) {
      sub = await registro.pushManager.subscribe({
        // Obligatorio: garantiza que cada push produce una notificación visible.
        // Sin esto, Chrome rechaza la suscripción.
        userVisibleOnly: true,
        applicationServerKey: base64UrlAUint8Array(clavePublica) as BufferSource,
      });
    }

    // El backend identifica el dispositivo por el endpoint: si ya existía, lo
    // actualiza en vez de duplicarlo.
    await api.post('/push/suscribir', sub.toJSON());
    return { ok: true, estado: 'activadas' };
  } catch (e: any) {
    return {
      ok: false,
      estado: 'no-activadas',
      error: e?.response?.data?.error || 'No se pudo activar las notificaciones en este dispositivo.',
    };
  }
}

/** Desactivar en este dispositivo. No afecta a los otros dispositivos del usuario. */
export async function desactivarPush(): Promise<boolean> {
  const sub = await obtenerSuscripcionActual();
  if (!sub) return true;
  try {
    await api.post('/push/desuscribir', { endpoint: sub.endpoint });
  } catch {
    // Aunque el backend falle, seguimos: el navegador no debe quedar suscrito
    // a un servidor que ya no le va a responder.
  }
  try {
    await sub.unsubscribe();
  } catch {
    return false;
  }
  return true;
}

/**
 * Endpoint de este dispositivo, para mandarlo en el logout.
 *
 * El backend borra ÚNICAMENTE esa fila. Ver POST /api/auth/logout.
 */
export async function endpointDeEsteDispositivo(): Promise<string | null> {
  const sub = await obtenerSuscripcionActual();
  return sub ? sub.endpoint : null;
}

/**
 * Baja del dispositivo actual al cerrar sesión: primero avisamos al backend
 * (con el token todavía válido) y después soltamos la suscripción del
 * navegador. Nunca lanza: un logout jamás debe fallar por esto.
 */
export async function limpiarPushAlSalir(): Promise<void> {
  try {
    const sub = await obtenerSuscripcionActual();
    if (!sub) return;
    try {
      await api.post('/auth/logout', { push_endpoint: sub.endpoint });
    } catch {
      /* el logout se completa igual */
    }
    try {
      await sub.unsubscribe();
    } catch {
      /* el navegador ya la había soltado */
    }
  } catch {
    /* nunca bloquear el cierre de sesión */
  }
}
