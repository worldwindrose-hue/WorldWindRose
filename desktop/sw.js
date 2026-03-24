/* ============================================================
   ROSA OS — Service Worker v1.0
   Caches static assets, handles offline, background sync
   ============================================================ */

const CACHE_VERSION = "rosa-v5.1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const API_CACHE = `${CACHE_VERSION}-api`;

const STATIC_ASSETS = [
  "/",
  "/style.css",
  "/app.js",
  "/manifest.json",
  "/icons/icon.svg",
  "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
  "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js",
  "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css",
];

const OFFLINE_PAGE = `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ROSA OS — Офлайн</title>
<style>
  :root { --bg: #212121; --accent: #10a37f; --text: #ececec; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: 100vh; gap: 16px; padding: 24px; text-align: center; }
  .rose { font-size: 80px; }
  h1 { font-size: 24px; }
  p { color: #8e8ea0; max-width: 320px; }
  button { background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 12px 24px; font-size: 16px; cursor: pointer; margin-top: 8px; }
</style>
</head>
<body>
<div class="rose">🌹</div>
<h1>Роза офлайн</h1>
<p>Нет соединения с сервером ROSA OS. Проверьте подключение к сети или убедитесь, что сервер запущен.</p>
<button onclick="location.reload()">Попробовать снова</button>
</body>
</html>`;

// ── INSTALL ───────────────────────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(async (cache) => {
      // Cache what we can; ignore CDN failures
      for (const url of STATIC_ASSETS) {
        try { await cache.add(url); } catch (_) {}
      }
      // Cache offline page
      const resp = new Response(OFFLINE_PAGE, { headers: { "Content-Type": "text/html" } });
      await cache.put("/__offline__", resp);
    }).then(() => self.skipWaiting())
  );
});

// ── ACTIVATE ──────────────────────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== STATIC_CACHE && k !== API_CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ── FETCH ─────────────────────────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET, WebSocket, and cross-origin requests we don't cache
  if (event.request.method !== "GET") return;
  if (url.pathname.startsWith("/api/ws/")) return;

  // API calls: network-first, no offline cache for dynamic data
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ error: "Офлайн", offline: true }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        })
      )
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then(async (resp) => {
          if (resp.ok && resp.type !== "opaque") {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(event.request, resp.clone());
          }
          return resp;
        })
        .catch(async () => {
          // Serve offline page for navigation requests
          if (event.request.mode === "navigate") {
            const cache = await caches.open(STATIC_CACHE);
            return cache.match("/__offline__");
          }
          return new Response("", { status: 503 });
        });
    })
  );
});

// ── BACKGROUND SYNC ───────────────────────────────────────────────────────

self.addEventListener("sync", (event) => {
  if (event.tag === "rosa-offline-messages") {
    event.waitUntil(syncOfflineMessages());
  }
});

async function syncOfflineMessages() {
  try {
    const db = await openIDB();
    const messages = await idbGetAll(db, "offline_queue");
    for (const msg of messages) {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg.content, session_id: msg.session_id }),
      });
      if (r.ok) await idbDelete(db, "offline_queue", msg.id);
    }
  } catch (_) {}
}

// ── PUSH NOTIFICATIONS ────────────────────────────────────────────────────

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data.json(); } catch (_) { data = { title: "ROSA", body: event.data?.text() || "" }; }

  const options = {
    body: data.body || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: data.tag || "rosa-notification",
    renotify: true,
    data: { url: data.url || "/" },
    vibrate: [200, 100, 200],
    actions: [
      { action: "open", title: "Открыть" },
      { action: "dismiss", title: "Закрыть" },
    ],
  };

  event.waitUntil(self.registration.showNotification(data.title || "🌹 ROSA", options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  if (event.action === "dismiss") return;
  const url = event.notification.data?.url || "/";
  event.waitUntil(clients.openWindow(url));
});

// ── IDB HELPERS ───────────────────────────────────────────────────────────

function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("rosa-sw", 1);
    req.onupgradeneeded = (e) => e.target.result.createObjectStore("offline_queue", { keyPath: "id" });
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = reject;
  });
}

function idbGetAll(db, store) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readonly");
    const req = tx.objectStore(store).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = reject;
  });
}

function idbDelete(db, store, id) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, "readwrite");
    const req = tx.objectStore(store).delete(id);
    req.onsuccess = resolve;
    req.onerror = reject;
  });
}
