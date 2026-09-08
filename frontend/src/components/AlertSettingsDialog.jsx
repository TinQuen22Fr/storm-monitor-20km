import React, { useState, useEffect } from "react";
import { Sliders, Bell, Moon, Check, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function AlertSettingsDialog({ isOpen, onClose }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({
    enabled: true,
    radius_km: 20,
    min_strikes: 1,
    quiet_hours_enabled: false,
    quiet_hours_start: "23:00",
    quiet_hours_end: "07:00",
  });

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    api
      .get("/user/alert-settings")
      .then((res) => {
        if (res.data) setSettings(res.data);
      })
      .catch((err) => {
        console.error("Erreur chargement réglages:", err);
        toast.error("Impossible de charger les réglages d'alerte");
      })
      .finally(() => setLoading(false));
  }, [isOpen]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/user/alert-settings", settings);
      toast.success("Réglages d'alerte enregistrés !");
      onClose();
    } catch (err) {
      console.error("Erreur sauvegarde réglages:", err);
      toast.error("Échec de la mise à jour des réglages");
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md border border-slate-700 bg-slate-900 p-6 text-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Sliders className="h-5 w-5 text-red-500" />
            <h2 className="font-mono text-sm font-bold uppercase tracking-wider">
              Réglages des alertes orage
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white"
            aria-label="Fermer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-red-500" />
          </div>
        ) : (
          <div className="mt-4 space-y-5">
            {/* Activer / Désactiver les alertes orage */}
            <div className="flex items-center justify-between">
              <div>
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                  Alertes orage
                </label>
                <p className="text-[11px] text-slate-400">
                  Recevoir des notifications pour les orages détectés
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  setSettings((s) => ({ ...s, enabled: !s.enabled }))
                }
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                  settings.enabled ? "bg-red-600" : "bg-slate-700"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                    settings.enabled ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* Rayon d'alerte */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs font-mono">
                <span className="text-slate-300">Rayon de détection</span>
                <span className="font-bold text-red-400">
                  {settings.radius_km} km
                </span>
              </div>
              <input
                type="range"
                min="5"
                max="50"
                step="1"
                value={settings.radius_km}
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    radius_km: parseInt(e.target.value, 10),
                  }))
                }
                className="h-2 w-full cursor-pointer appearance-none rounded bg-slate-700 accent-red-600"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>5 km</span>
                <span>50 km</span>
              </div>
            </div>

            {/* Seuil d'impacts */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs font-mono">
                <span className="text-slate-300">Seuil minimal d'impacts</span>
                <span className="font-bold text-red-400">
                  {settings.min_strikes} impact{settings.min_strikes > 1 ? "s" : ""}
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="20"
                step="1"
                value={settings.min_strikes}
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    min_strikes: parseInt(e.target.value, 10),
                  }))
                }
                className="h-2 w-full cursor-pointer appearance-none rounded bg-slate-700 accent-red-600"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>1</span>
                <span>20</span>
              </div>
            </div>

            {/* Heures silencieuses */}
            <div className="border-t border-slate-800 pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Moon className="h-4 w-4 text-slate-400" />
                  <div>
                    <label className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                      Heures silencieuses
                    </label>
                    <p className="text-[11px] text-slate-400">
                      Ne pas envoyer de notification pendant la nuit
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setSettings((s) => ({
                      ...s,
                      quiet_hours_enabled: !s.quiet_hours_enabled,
                    }))
                  }
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                    settings.quiet_hours_enabled ? "bg-red-600" : "bg-slate-700"
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                      settings.quiet_hours_enabled ? "translate-x-4" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>

              {settings.quiet_hours_enabled && (
                <div className="flex items-center gap-4 pt-1">
                  <div className="flex-1">
                    <span className="block text-[10px] text-slate-400 mb-1">
                      Début
                    </span>
                    <input
                      type="time"
                      value={settings.quiet_hours_start}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          quiet_hours_start: e.target.value,
                        }))
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white focus:outline-none focus:border-red-500"
                    />
                  </div>
                  <div className="flex-1">
                    <span className="block text-[10px] text-slate-400 mb-1">
                      Fin
                    </span>
                    <input
                      type="time"
                      value={settings.quiet_hours_end}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          quiet_hours_end: e.target.value,
                        }))
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white focus:outline-none focus:border-red-500"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="mt-6 flex justify-end gap-2 border-t border-slate-800 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 text-xs font-mono uppercase tracking-wider text-slate-400 hover:text-white"
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 bg-red-600 px-4 py-1.5 text-xs font-mono font-semibold uppercase tracking-wider text-white hover:bg-red-500 disabled:opacity-50"
              >
                {saving ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Enregistrer
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
