const CACHE_NAME = 'mi-consultorio-v3';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/styles.css',
  '/static/js/app.js',
  '/static/logo.png',
  '/static/manifest.json',
  '/static/notification.wav'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch(() => {});
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // APIs always network-first
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(JSON.stringify({ error: 'Sin conexión a internet' }), {
          headers: { 'Content-Type': 'application/json' }
        });
      })
    );
    return;
  }

  // Static assets: Stale-While-Revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseToCache));
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});

// Soporte para Notificaciones Push Nativas VAPID en la barra de tareas y pantalla de bloqueo
self.addEventListener('push', (event) => {
  let data = { title: 'Espacio Terapéutico', body: 'Tienes una nueva actualización en tu consultorio.', url: '/' };
  if (event.data) {
    try {
      const parsed = event.data.json();
      data.title = parsed.title || parsed.notification?.title || data.title;
      data.body = parsed.body || parsed.notification?.body || data.body;
      data.url = parsed.url || parsed.data?.url || data.url;
    } catch (e) {
      data.body = event.data.text() || data.body;
    }
  }

  const options = {
    body: data.body,
    icon: '/static/logo.png',
    badge: '/static/logo.png',
    sound: '/static/notification.wav',
    vibrate: [300, 100, 300, 100, 300],
    tag: data.tag || 'miconsultorio-notification',
    renotify: true,
    requireInteraction: true,
    data: { url: data.url || '/' },
    actions: [
      { action: 'open', title: '👁️ Ver en la App' }
    ]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (let client of windowClients) {
        if (client.url.includes(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

