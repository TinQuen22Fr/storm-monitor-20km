import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { api, LOURDES } from "@/lib/api";

/**
 * Floating badge showing trajectory stats: speed, bearing, ETA.
 * Renders next to the strikes badge so the user sees the prediction
 * even when the polyline is outside the currently visible map area.
 */
export default function TrajectoryBadge({ center = LOURDES, enabled = true }) {
  const [traj, setTraj] = useState(null);

  useEffect(() => {
    if (!enabled) {
      setTraj(null);
      return;
    }
    let cancel = false;
    const load = async () => {
      try {
        const { data } = await api.get("/storms/trajectory", {
          params: { lat: center.lat, lon: center.lon, radius_km: 150, project_minutes: 45 },
        });
        if (!cancel) setTraj(data);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 30_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, [enabled, center.lat, center.lon]);

  if (!enabled || !traj) return null;

  const detected = traj.detected;
  const reasonText = {
    not_enough_strikes: "Pas assez d'impacts",
    static_centroid: "Cellule immobile",
    stationary: "Quasi-stationnaire",
    noise_too_high: `Dispersion trop élevée (${traj.computed_speed_kmh} km/h)`,
  };

  return (
    <div
      className="absolute top-[220px] right-6 z-[500] bg-white border border-slate-200 px-4 py-3 shadow-[0_2px_16px_rgba(0,0,0,0.04)] max-w-[220px]"
      data-testid="trajectory-badge"
    >
      <div className="flex items-center gap-3">
        <Activity
          className={`w-4 h-4 ${detected ? "text-red-600" : "text-slate-400"}`}
          strokeWidth={2}
        />
        <div className="min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
            Trajectoire
          </div>
          {detected ? (
            <>
              <div className="font-mono text-sm font-medium text-slate-900 tabular-nums leading-tight mt-0.5">
                {traj.speed_kmh} km/h · {traj.compass}
              </div>
              {traj.eta_min !== null && traj.eta_min !== undefined ? (
                <div className="font-mono text-[10px] text-red-600 mt-1">
                  ETA centre ~{Math.round(traj.eta_min)} min
                </div>
              ) : (
                <div className="font-mono text-[10px] text-slate-500 mt-1">
                  Plus proche à {traj.closest_distance_km} km
                </div>
              )}
            </>
          ) : (
            <div className="font-mono text-[10px] text-slate-500 mt-0.5 leading-tight">
              {reasonText[traj.reason] || "Non détectée"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
