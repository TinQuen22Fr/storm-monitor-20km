import { useEffect, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { App as CapApp } from "@capacitor/app";
import { Power, X } from "lucide-react";

export const NativeAppExit = () => {
  const isNative = Capacitor.isNativePlatform();
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!isNative) return;
    const sub = CapApp.addListener("backButton", ({ canGoBack }) => {
      if (canGoBack) window.history.back();
      else CapApp.exitApp();
    });
    return () => { sub.then((h) => h.remove()); };
  }, [isNative]);

  useEffect(() => {
    if (!confirming) return;
    const t = setTimeout(() => setConfirming(false), 3500);
    return () => clearTimeout(t);
  }, [confirming]);

  if (!isNative) return null;

  return (
    <div className="fixed bottom-20 right-3 z-[1500] flex items-center gap-2">
      {confirming && (
        <button
          data-testid="native-exit-confirm-button"
          onClick={() => CapApp.exitApp()}
          className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-lg animate-in fade-in slide-in-from-right-2"
        >
          Quitter l'application ?
        </button>
      )}
      <button
        data-testid="native-exit-button"
        aria-label="Quitter l'application"
        onClick={() => setConfirming((v) => !v)}
        className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-900/85 text-white shadow-lg backdrop-blur-sm border border-white/15 active:scale-95 transition-transform"
      >
        {confirming ? <X size={20} /> : <Power size={20} />}
      </button>
    </div>
  );
};
