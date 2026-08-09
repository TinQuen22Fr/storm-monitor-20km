import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";

/**
 * APK Android uniquement : si la WebView ne remonte pas env(safe-area-inset-top)
 * (édge-to-édge Android 15 avec vieux Chrome), on force un décalage de 32 px
 * pour que la carte ne s'affiche plus sous l'heure/batterie.
 */
export function SafeAreaTop() {
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;
    const v = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--safe-top")
    ) || 0;
    if (v < 8) {
      document.documentElement.style.setProperty("--safe-top", "32px");
    }
  }, []);
  return null;
}
