const CACHE_NAME = 'mi-consultorio-v141';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/styles.css',
  '/static/js/app.js',
  '/static/js/tests_module.js',
  '/static/logo.png',
  '/static/manifest.json',
  '/static/notification.wav',
  'https://cdn.jsdelivr.net/npm/fullcalendar@6.1.15/index.global.min.js',
  'https://cdn.jsdelivr.net/npm/@fullcalendar/core@6.1.15/locales/es.global.min.js'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
        console.warn('[SW] Error precaching assets:', err);
      });
    })
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

  // APIs: Network-first, fallback to offline JSON response
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request, { cache: 'no-store' }).catch(() => {
        return new Response(JSON.stringify({ error: 'offline', offline: true }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        });
      })
    );
    return;
  }

  // Navegación (HTML principal): Network first, fallback to cached root '/'
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/'))
    );
    return;
  }

  // JS/CSS/Fonts/Images/CDN: Network-First con actualización y fallback a caché
  event.respondWith(
    fetch(event.request).then((networkResponse) => {
      if (networkResponse && networkResponse.status === 200) {
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseToCache));
      }
      return networkResponse;
    }).catch(() => {
      return caches.match(event.request).then(cached => cached || (url.pathname === '/' ? caches.match('/') : new Response('Offline', { status: 503 })));
    })
  );
});

// Push notifications en segundo plano
self.addEventListener('push', (event) => {
  let data = { title: 'Espacio Terapéutico', body: 'Tienes una nueva notificación.', icon: '/static/logo.png', url: '/' };
  if (event.data) {
    try {
      const parsed = event.data.json();
      
      if (parsed.notification || parsed.data) {
        // FCM payload format
        data.title = (parsed.notification && parsed.notification.title) || (parsed.data && parsed.data.title) || data.title;
        data.body = (parsed.notification && parsed.notification.body) || (parsed.data && parsed.data.body) || parsed.data?.mensaje || data.body;
        data.icon = (parsed.notification && parsed.notification.icon) || (parsed.data && parsed.data.icon) || data.icon;
        data.url = (parsed.data && parsed.data.url) || (parsed.data && parsed.data.link) || data.url;
        data.tag = (parsed.notification && parsed.notification.tag) || (parsed.data && parsed.data.tag) || data.tag;
      } else {
        // Standard VAPID format
        data.title = parsed.title || data.title;
        data.body = parsed.body || parsed.mensaje || data.body;
        data.icon = parsed.icon || data.icon;
        data.url = parsed.url || parsed.link || data.url;
        data.tag = parsed.tag || data.tag;
      }
    } catch (e) {
      data.body = event.data.text();
    }
  }

  // Generar tag determinista para colapsar duplicados
  const notifTag = data.tag || ('notif-' + (data.title || '') + '-' + (data.body || '')).replace(/\s+/g, '_').substring(0, 40);

  const options = {
    body: data.body,
    icon: data.icon,
    badge: '/static/badge.png',
    tag: notifTag,
    renotify: true,
    vibrate: [100, 50, 100],
    data: { url: data.url }
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
