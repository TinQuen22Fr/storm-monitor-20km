import { api } from "@/lib/api";
import { toast } from "sonner";

const LS_ENABLED = "storm_push_enabled";

export function pushSupported() {
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

export async function subscribePush() {
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
  if (!pushSupported()) return false;
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

export async function sendTestPush() {
  try {
    const { data } = await api.post("/push/test");
    toast.success(`Test envoyé (${data.sent} appareils)`);
  } catch (e) {
    toast.error("Connectez-vous pour envoyer un test");
  }
}
