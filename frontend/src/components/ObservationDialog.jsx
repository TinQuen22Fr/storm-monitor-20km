import React, { useEffect, useState } from "react";
import {
  X,
  Loader2,
  MapPin,
  Crosshair,
  CloudLightning,
  Zap,
  CloudHail,
  CloudRain,
  Wind,
  Send,
  AlertTriangle,
} from "lucide-react";
import { postObservation } from "@/lib/api";
import { toast } from "sonner";

const OBSERVATION_TYPES = [
  { key: "thunder", label: "Tonnerre", icon: CloudLightning },
  { key: "lightning", label: "Éclairs", icon: Zap },
  { key: "hail", label: "Grêle", icon: CloudHail },
  { key: "rain_heavy", label: "Pluie intense", icon: CloudRain },
  { key: "wind_gust", label: "Fortes rafales", icon: Wind },
];

const COMMENT_MAX = 140;

export default function ObservationDialog({ isOpen, onClose, defaultCoords, onSuccess }) {
  const [selectedTypes, setSelectedTypes] = useState([]);
  const [comment, setComment] = useState("");
  const [coords, setCoords] = useState(defaultCoords || { lat: 0, lon: 0 });
  const [gpsStatus, setGpsStatus] = useState("idle"); // idle | loading | success | error
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  // Réinitialise le formulaire à chaque ouverture, calé sur les coords par défaut fournies
  useEffect(() => {
    if (isOpen) {
      setSelectedTypes([]);
      setComment("");
      setCoords(defaultCoords || { lat: 0, lon: 0 });
      setGpsStatus("idle");
      setErrorMsg(null);
    }
  }, [isOpen, defaultCoords]);

  if (!isOpen) return null;

  const toggleType = (key) => {
    setSelectedTypes((prev) =>
      prev.includes(key) ? prev.filter((t) => t !== key) : [...prev, key]
    );
  };

  const handleUseGps = () => {
    if (!navigator.geolocation) {
      setGpsStatus("error");
      toast.error("Géolocalisation non disponible sur cet appareil");
      return;
    }
    setGpsStatus("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setGpsStatus("success");
      },
      (err) => {
        console.error("Erreur GPS:", err);
        setGpsStatus("error");
        toast.error("Impossible d'obtenir votre position GPS");
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const handleCommentChange = (e) => {
    setComment(e.target.value.slice(0, COMMENT_MAX));
  };

  const handleSubmit = async () => {
    if (selectedTypes.length === 0 || submitting) return;
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const newObs = await postObservation({
        lat: coords.lat,
        lon: coords.lon,
        types: selectedTypes,
        comment: comment.trim() ? comment.trim() : undefined,
      });
      toast.success("Observation envoyée, merci pour votre signalement !");
      setSelectedTypes([]);
      setComment("");
      onSuccess?.(newObs);
      onClose();
    } catch (err) {
      console.error("Erreur envoi observation:", err);
      if (err?.response?.status === 429) {
        const detail =
          err.response.data?.detail || "Merci de patienter avant de publier une nouvelle observation.";
        setErrorMsg(detail);
      } else {
        const detail = err?.response?.data?.detail || "Échec de l'envoi de l'observation.";
        setErrorMsg(detail);
        toast.error(detail);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit = selectedTypes.length > 0 && !submitting;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md border border-slate-700 bg-slate-900 p-6 text-white shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <CloudLightning className="h-5 w-5 text-red-500" />
            <h2 className="font-mono text-sm font-bold uppercase tracking-wider">
              Signaler une observation
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white"
            aria-label="Fermer"
            data-testid="observation-dialog-close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-4 space-y-5">
          {/* Bandeau d'erreur (ex: rate-limit 429) */}
          {errorMsg && (
            <div
              className="flex items-start gap-2 border border-red-800 bg-red-950/60 px-3 py-2 text-xs text-red-300"
              data-testid="observation-error-banner"
            >
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-red-500" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Types de phénomènes */}
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-200">
              Que se passe-t-il ?
            </label>
            <div className="grid grid-cols-2 gap-2">
              {OBSERVATION_TYPES.map(({ key, label, icon: Icon }) => {
                const active = selectedTypes.includes(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleType(key)}
                    data-testid={`obs-type-${key}`}
                    className={`flex items-center gap-2 border px-3 py-2 text-xs font-medium transition-colors ${
                      active
                        ? "border-red-600 bg-red-600/20 text-red-300"
                        : "border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-500"
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Position géographique */}
          <div className="space-y-2 border-t border-slate-800 pt-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                Position
              </label>
              <button
                type="button"
                onClick={handleUseGps}
                disabled={gpsStatus === "loading"}
                data-testid="obs-use-gps"
                className="flex items-center gap-1.5 border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-200 hover:border-slate-500 disabled:opacity-60"
              >
                {gpsStatus === "loading" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Crosshair
                    className={`h-3.5 w-3.5 ${gpsStatus === "success" ? "text-green-400" : ""}`}
                  />
                )}
                Utiliser ma position GPS
              </button>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span>
                {coords.lat.toFixed(3)}, {coords.lon.toFixed(3)}
              </span>
              {gpsStatus === "success" && (
                <span className="text-green-400">· position GPS utilisée</span>
              )}
              {gpsStatus === "error" && (
                <span className="text-red-400">· échec GPS, position par défaut conservée</span>
              )}
            </div>
          </div>

          {/* Commentaire */}
          <div className="space-y-1 border-t border-slate-800 pt-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                Commentaire (optionnel)
              </label>
              <span className="text-[10px] font-mono text-slate-500">
                {comment.length}/{COMMENT_MAX}
              </span>
            </div>
            <textarea
              value={comment}
              onChange={handleCommentChange}
              maxLength={COMMENT_MAX}
              rows={2}
              placeholder="Ex: grêlons de 2cm, vent très fort..."
              data-testid="obs-comment-input"
              className="w-full resize-none bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-red-600"
            />
          </div>

          {/* Bouton d'envoi */}
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            data-testid="obs-submit-button"
            className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold uppercase tracking-wider transition-colors ${
              canSubmit
                ? "bg-red-600 text-white hover:bg-red-500"
                : "bg-slate-800 text-slate-500 cursor-not-allowed"
            }`}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Envoyer l'observation
          </button>
        </div>
      </div>
    </div>
  );
}
