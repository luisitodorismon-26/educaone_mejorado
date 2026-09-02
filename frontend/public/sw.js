// EducaOne — Service Worker
// v3 (2026): agrega Web Push (Fase C del sistema unificado de notificaciones).
//
// IMPORTANTE: al cambiar este archivo hay que subir CACHE_NAME. El navegador
// detecta el byte-diff e instala la versión nueva, y el `activate` de abajo
// borra los caches viejos. Con skipWaiting() + clients.claim() el cambio se
// propaga sin que el usuario tenga que cerrar todas las pestañas.
const CACHE_NAME = 'educaone-v3';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/api/')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && event.request.url.includes('/assets/')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(async () => {
        // Fallback: intentar cache, si no hay, devolver index.html (SPA fallback)
        const cached = await caches.match(event.request);
        if (cached) return cached;
        const fallback = await caches.match('/');
        if (fallback) return fallback;
        return new Response('Offline', { status: 503, statusText: 'Offline' });
      })
  );
});

// ====================================================================
// WEB PUSH (Fase C)
// ====================================================================

// El texto mostrado es EXACTAMENTE el que el backend ya guardó en la
// notificación. No se enriquece ni se completa con datos de la API: los avisos
// de Psicología vienen redactados a propósito sin nombre del estudiante ni
// motivo, porque este texto aparece en la pantalla bloqueada del teléfono.
// Solo se acepta una ruta INTERNA de EducaOne. El payload viaja firmado por
// VAPID, pero si alguna vez se filtrara la clave privada, un link malicioso
// convertiría la notificación en un vector de phishing con la marca del
// colegio. Se exige '/' inicial y se rechaza '//host' (que el navegador
// interpreta como protocolo relativo → sitio externo) y cualquier esquema.
function rutaInternaSegura(link) {
  if (typeof link !== 'string') return '/';
  const l = link.trim();
  if (!l.startsWith('/')) return '/';   // 'https://…', 'javascript:', 'data:'
  if (l.startsWith('//')) return '/';   // '//evil.com' = protocolo relativo
  if (l.startsWith('/\\')) return '/'; // '/\\evil.com' lo normalizan algunos navegadores
  return l;
}

self.addEventListener('push', (event) => {
  let datos = {};
  try {
    datos = event.data ? event.data.json() : {};
  } catch (e) {
    // Payload no-JSON: mostramos un aviso genérico en vez de perder el push.
    datos = {};
  }

  const titulo = datos.titulo || 'EducaOne';
  const cuerpo = datos.mensaje || 'Tiene una notificación nueva.';
  const link = rutaInternaSegura(datos.link);
  const prioridad = datos.prioridad || 'normal';

  const opciones = {
    body: cuerpo,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    // El link viaja en data para que notificationclick sepa a dónde ir.
    data: { link: link, notificacion_id: datos.notificacion_id || null },
    // Las urgentes no se descartan solas: quedan hasta que la persona las toca.
    requireInteraction: prioridad === 'urgente',
    // Agrupar por notificación evita que dos pushes del mismo evento se apilen.
    tag: datos.notificacion_id ? ('educaone-' + datos.notificacion_id) : 'educaone',
    renotify: prioridad === 'urgente'
  };

  // v2.19.3-C — Además de la notificación del sistema, avisar a las ventanas
  // de EducaOne que estén abiertas para que refresquen su interfaz al
  // instante, sin esperar al polling de 30 s y sin exigir F5.
  //
  // showNotification se mantiene SIEMPRE: el contrato userVisibleOnly de la
  // suscripción obliga a mostrar algo por cada push. Si la persona ya está
  // mirando la app verá las dos cosas —la notificación y la interfaz ya
  // actualizada—, que es la decisión tomada a favor de la fiabilidad.
  //
  // El postMessage no lleva contenido del mensaje: es solo una señal de
  // "hay algo nuevo, volvé a consultar". Los datos los pide el frontend con
  // el token del usuario, así que este canal no puede filtrar nada.
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(titulo, opciones),
      avisarAVentanasAbiertas({
        tipo: 'educaone:refrescar',
        notificacion_id: datos.notificacion_id || null,
        link: link
      })
    ])
  );
});

/**
 * Envía una señal a todas las ventanas de EducaOne abiertas.
 * Nunca rechaza: un fallo acá no debe impedir que se muestre la notificación.
 */
function avisarAVentanasAbiertas(payload) {
  return self.clients
    .matchAll({ type: 'window', includeUncontrolled: true })
    .then((clientes) => {
      clientes.forEach((cliente) => {
        try {
          cliente.postMessage(payload);
        } catch (e) {
          /* una ventana que ya se cerró no debe romper al resto */
        }
      });
    })
    .catch(() => {});
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const link = rutaInternaSegura(event.notification.data && event.notification.data.link);

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientes) => {
      // Si EducaOne ya está abierto se enfoca esa ventana y se navega ahí mismo,
      // en vez de abrir una pestaña nueva por cada notificación.
      for (const cliente of clientes) {
        if (cliente.url.indexOf(self.location.origin) === 0) {
          return cliente.focus().then((c) => {
            const destino = c || cliente;
            if ('navigate' in destino) {
              return destino.navigate(link).catch(() => destino);
            }
            // Safari/iOS no siempre expone navigate(): avisamos por mensaje y
            // el frontend hace el routing interno.
            destino.postMessage({ tipo: 'educaone:navegar', link: link });
            return destino;
          });
        }
      }
      // Sin ventanas abiertas: abrir directo en el link. La autenticación y los
      // permisos los sigue aplicando el frontend y el endpoint destino; este
      // link no saltea ninguna verificación.
      if (self.clients.openWindow) {
        return self.clients.openWindow(link);
      }
      return null;
    })
  );
});
