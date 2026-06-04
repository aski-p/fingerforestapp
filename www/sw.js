self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_error) {
    data = {};
  }
  const title = data.title || "fingerfruit";
  const options = {
    body: data.body || "새 알림이 있습니다.",
    tag: data.tag || "fruit-auto",
    renotify: false,
    icon: "/icons/app-icon-192.png?v=3.8.3",
    badge: "/icons/app-icon-192.png?v=3.8.3",
    data: {
      url: data.url || "/",
    },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client) {
          client.focus();
          return;
        }
      }
      return clients.openWindow(url);
    })
  );
});
