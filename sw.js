importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.1/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCUS3UkIl6J6lXfp6fZZqwvYyCgMNx-Lz4",
  authDomain: "stock-alert-pwa.firebaseapp.com",
  projectId: "stock-alert-pwa",
  storageBucket: "stock-alert-pwa.firebasestorage.app",
  messagingSenderId: "249296765321",
  appId: "1:249296765321:web:88a5b155b574058bbe2158"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: '/icon.png'
  };
  self.registration.showNotification(notificationTitle, notificationOptions);
});
