/* Service worker for Lourdes Storm Tracker push notifications */
/* eslint-disable no-restricted-globals */

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: "Alerte orage", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "Alerte orage · Lourdes";
  const body = data.body || "Activité orageuse détectée.";
  const tag = data.tag || "storm";
  const url = data.url || "/";

  const options = {
    body,
    tag,
    icon: "/favicon.ico",
    badge: "/favicon.ico",
    data: { url },
    requireInteraction: false,
    vibrate: [120, 60, 120],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url.includes(url) && "focus" in c) return c.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
