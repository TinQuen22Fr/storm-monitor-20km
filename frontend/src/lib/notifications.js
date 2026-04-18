import { toast } from "sonner";

const LS_KEY = "storm_notif_enabled";

export function notificationSupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

export function getPermission() {
  if (!notificationSupported()) return "unsupported";
  return Notification.permission;
}

export function isEnabled() {
  return notificationSupported() && localStorage.getItem(LS_KEY) === "1" && Notification.permission === "granted";
}

export async function enable() {
  if (!notificationSupported()) {
    toast.error("Notifications non supportées par ce navigateur");
    return false;
  }
  let perm = Notification.permission;
  if (perm === "default") perm = await Notification.requestPermission();
  if (perm !== "granted") {
    toast.error("Autorisation refusée");
    localStorage.setItem(LS_KEY, "0");
    return false;
  }
  localStorage.setItem(LS_KEY, "1");
  toast.success("Alertes orage activées");
  try {
    new Notification("Alertes orage activées", {
      body: "Vous serez notifié dès qu'un orage est détecté dans la zone.",
      icon: "/favicon.ico",
      silent: true,
    });
  } catch { /* ignore */ }
  return true;
}

export function disable() {
  localStorage.setItem(LS_KEY, "0");
  toast.info("Alertes orage désactivées");
}

export function notify(title, body) {
  if (!isEnabled()) return;
  try {
    new Notification(title, {
      body,
      icon: "/favicon.ico",
      tag: "storm-alert",
      requireInteraction: false,
    });
  } catch { /* ignore */ }
}
