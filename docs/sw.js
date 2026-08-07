self.addEventListener('push', event => {
  const data = event.data?.json() || { title: 'Alert', body: 'Check your stocks' };
  const options = { body: data.body, icon: '/icon.png', badge: '/badge.png' };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/stock-circuit-alert/'));
});
