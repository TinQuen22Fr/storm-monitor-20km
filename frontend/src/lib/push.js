import { Capacitor } from "@capacitor/core";
import { api } from "@/lib/api";
import { toast } from "sonner";

const LS_ENABLED = "storm_push_enabled";
const LS_FCM_TOKEN = "storm_fcm_token";

export function pushSupported() {
  if (Capacitor.isNativePlatform()) return true;
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

async function getRegistration() {
  let reg = await navigator.serviceWorker.getRegistration("/sw.js");
  if (!reg) reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  return reg;
}

async function getVapidKey() {
  const { data } = await api.get("/push/vapid-public-key");
  return data.key;
}

export function isPushEnabled() {
  return pushSupported() && localStorage.getItem(LS_ENABLED) === "1";
}

/** APK au premier plan : Android n'affiche PAS les notifications FCM dans la
 * barre système — on les rejoue en notification locale (canal storm_alerts)
 * pour qu'elles apparaissent sur le téléphone ET soient relayées à la montre. */
async function showForegroundNotification(n) {
  try {
    const { LocalNotifications } = await import("@capacitor/local-notifications");
    await LocalNotifications.schedule({
      notifications: [
        {
          id: Math.floor(Math.random() * 2147483646) + 1,
          title: n?.title || "Alerte orage",
          body: n?.body || "",
          channelId: "storm_alerts",
        },
      ],
    });
  } catch { /* ignore */ }
}

async function attachNativeListeners(PushNotifications, { onRegistration } = {}) {
  await PushNotifications.removeAllListeners();
  PushNotifications.addListener("pushNotificationReceived", (n) => {
    showForegroundNotification(n);
  });
  PushNotifications.addListener("registration", async ({ value }) => {
    try {
      const { data } = await api.post("/push/fcm/subscribe", { token: value });
      localStorage.setItem(LS_FCM_TOKEN, value);
      if (data.fcm_available === false) {
        toast.warning(
          "Token enregistré, mais FCM est désactivé côté serveur (firebase-admin.json)",
          { duration: 8000 }
        );
      }
      if (onRegistration) onRegistration(null, value);
    } catch (e) {
      if (onRegistration) onRegistration(e, value);
    }
  });
  PushNotifications.addListener("registrationError", () => {
    if (onRegistration) onRegistration(new Error("registrationError"), null);
  });
}

/** À appeler au démarrage de l'app : ré-arme les listeners natifs (perdus à
 * chaque relance) et re-lie le token FCM au compte connecté (header Authorization). */
export async function initNativePush() {
  if (!Capacitor.isNativePlatform()) return;
  if (localStorage.getItem(LS_ENABLED) !== "1") return;
  try {
    const { PushNotifications } = await import("@capacitor/push-notifications");
    const perm = await PushNotifications.checkPermissions();
    if (perm.receive !== "granted") return;
    await attachNativeListeners(PushNotifications);
    PushNotifications.register();
  } catch { /* ignore */ }
}

async function subscribeNative() {
  try {
    const { PushNotifications } = await import("@capacitor/push-notifications");
    let perm = await PushNotifications.checkPermissions();
    if (perm.receive !== "granted") perm = await PushNotifications.requestPermissions();
    if (perm.receive !== "granted") {
      toast.error("Autorisation refusée");
      return false;
    }
    await PushNotifications.createChannel({
      id: "storm_alerts",
      name: "Alertes orage",
      description: "Orages détectés ou en approche, impacts de foudre",
      importance: 5,
      sound: "default",
      vibration: true,
    });
    return await new Promise((resolve) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        toast.error("Délai d'enregistrement FCM dépassé");
        resolve(false);
      }, 15000);
      attachNativeListeners(PushNotifications, {
        onRegistration: (err) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          if (err) {
            toast.error("Échec de l'enregistrement du push");
            resolve(false);
            return;
          }
          localStorage.setItem(LS_ENABLED, "1");
          toast.success("Notifications push activées");
          resolve(true);
        },
      }).then(() => PushNotifications.register());
    });
  } catch {
    toast.error("Push natif indisponible");
    return false;
  }
}

async function unsubscribeNative() {
  const token = localStorage.getItem(LS_FCM_TOKEN);
  if (token) {
    try { await api.post("/push/fcm/unsubscribe", { token }); } catch { /* ignore */ }
  }
  try {
    const { PushNotifications } = await import("@capacitor/push-notifications");
    await PushNotifications.removeAllListeners();
  } catch { /* ignore */ }
  localStorage.setItem(LS_ENABLED, "0");
  localStorage.removeItem(LS_FCM_TOKEN);
  toast.info("Notifications push désactivées");
  return true;
}

export async function subscribePush() {
  if (Capacitor.isNativePlatform()) return subscribeNative();
  if (!pushSupported()) {
    toast.error("Push non supporté sur ce navigateur");
    return false;
  }
  let perm = Notification.permission;
  if (perm === "default") perm = await Notification.requestPermission();
  if (perm !== "granted") {
    toast.error("Autorisation refusée");
    return false;
  }

  const reg = await getRegistration();
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    const vapidKey = await getVapidKey();
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidKey),
    });
  }

  const payload = sub.toJSON();
  await api.post("/push/subscribe", {
    endpoint: payload.endpoint,
    keys: payload.keys,
  });
  localStorage.setItem(LS_ENABLED, "1");
  toast.success("Notifications push activées");
  return true;
}

export async function unsubscribePush() {
  if (Capacitor.isNativePlatform()) return unsubscribeNative();  if (!pushSupported()) return false;
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  if (!reg) {
    localStorage.setItem(LS_ENABLED, "0");
    return true;
  }
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    try {
      await api.post("/push/unsubscribe", { endpoint: sub.endpoint });
    } catch { /* ignore */ }
    await sub.unsubscribe();
  }
  localStorage.setItem(LS_ENABLED, "0");
  toast.info("Notifications push désactivées");
  return true;
}

/** Re-lie l'appareil au compte après login (le token FCM/subscription est
 * ré-envoyé avec le header Authorization → user_id renseigné côté serveur,
 * requis pour l'envoi de test unicast). */
export async function rebindToken() {
  if (localStorage.getItem(LS_ENABLED) !== "1") return;
  const fcmToken = localStorage.getItem(LS_FCM_TOKEN);
  if (fcmToken) {
    try { await api.post("/push/fcm/subscribe", { token: fcmToken }); } catch { /* ignore */ }
    return;
  }
  if (!Capacitor.isNativePlatform() && "serviceWorker" in navigator) {
    try {
      const reg = await navigator.serviceWorker.getRegistration("/sw.js");
      const sub = reg && (await reg.pushManager.getSubscription());
      if (sub) {
        const payload = sub.toJSON();
        await api.post("/push/subscribe", { endpoint: payload.endpoint, keys: payload.keys });
      }
    } catch { /* ignore */ }
  }
}

export async function sendTestPush() {
  let data;
  try {
    ({ data } = await api.post("/push/test"));
  } catch (e) {
    toast.error("Connectez-vous pour envoyer un test");
    return;
  }
  if (data.sent > 0) {
    toast.success(`Test envoyé (${data.sent}/${data.total} appareils)`);
    return;
  }
  if (data.fcm?.disabled) {
    toast.error(
      "Serveur : FCM désactivé — firebase-admin.json manquant sur le Kimsufi",
      { duration: 8000 }
    );
    return;
  }
  if (data.total === 0) {
    toast.warning("Aucun appareil enregistré côté serveur — réactive le push");
    return;
  }
  toast.error(`Échec d'envoi (${data.total} appareils enregistrés, 0 délivrés)`);
}
