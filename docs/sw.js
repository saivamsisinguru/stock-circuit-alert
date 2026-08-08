self.addEventListener('push', event => {
  const data = event.data?.json() || { title: 'Alert', body: 'Check your stocks' };
  const options = { body: data.body, icon: '/icon.png', badge: '/badge.png' };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow('/stock-circuit-alert/'));
});

// On activation, subscribe to the FCM topic via the Edge Function
self.addEventListener('activate', event => {
  event.waitUntil(
    fetch('https://xwuajufeclbgmepazoqm.supabase.co/functions/v1/push-notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Subscribed',
        body: 'You will receive circuit alerts',
        topic: 'circuit_alerts'
      })
    }).catch(() => {})
  );
});
