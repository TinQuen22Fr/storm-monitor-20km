import { useEffect, useState } from "react";
import { Activity, Clock, Maximize2 } from "lucide-react";
import { api, LOURDES } from "@/lib/api";

/**
 * Floating badge showing trajectory stats: speed, bearing, ETA.
 * When the timeline cursor is in the past, the badge reflects the replay moment
 * (purple accent + "↺ Rejeu" label) instead of a live trajectory.
 */
export default function TrajectoryBadge({
  center = LOURDES,
  enabled = true,
  onFit,
  cursorTs = null,
  isLive = true,
  inline = false,
}) {
  const [traj, setTraj] = useState(null);

  useEffect(() => {
    if (!enabled) {
      setTraj(null);
      return;
    }
    let cancel = false;
    const load = async () => {
      try {
        const params = { lat: center.lat, lon: center.lon, radius_km: 70, project_minutes: 45 };
        if (!isLive && cursorTs) params.at_ts = cursorTs;
        const { data } = await api.get("/storms/trajectory", { params });
        if (!cancel) setTraj(data);
      } catch { /* ignore */ }
    };
    load();
    // Scrubbing: refetch on cursor change only (no interval)
    if (!isLive) return () => { cancel = true; };
    const t = setInterval(load, 30_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, [enabled, center.lat, center.lon, cursorTs, isLive]);

  if (!enabled || !traj) return null;

  const detected = traj.detected;
  const reasonText = {
    not_enough_strikes: "Pas assez d'impacts",
    static_centroid: "Cellule immobile",
    stationary: "Quasi-stationnaire",
    no_dominant_cluster: "Pas de cellule dominante",
    noise_too_high: `Dispersion trop élevée (${traj.computed_speed_kmh} km/h)`,
  };

  const accent = isLive ? "text-red-600" : "text-violet-600";
  const borderHover = isLive ? "hover:border-red-600" : "hover:border-violet-600";

  return (
    <button
      onClick={detected && onFit ? onFit : undefined}
      disabled={!detected || !onFit}
      className={`${
        inline
          ? "w-full border border-transparent px-0 py-0 bg-transparent text-left"
          : `absolute top-[220px] right-6 z-[500] bg-white border border-slate-200 px-4 py-3 shadow-[0_2px_16px_rgba(0,0,0,0.04)] max-w-[220px] text-left ${
              detected && onFit ? `${borderHover} cursor-pointer` : "cursor-default"
            }`
      } transition-colors`}
      data-testid="trajectory-badge"
      title={detected ? "Cliquer pour cadrer la carte sur la trajectoire" : undefined}
    >
      <div className="flex items-center gap-3">
        {isLive ? (
          <Activity
            className={`w-4 h-4 ${detected ? accent : "text-slate-400"}`}
            strokeWidth={2}
          />
        ) : (
          <Clock
            className={`w-4 h-4 ${detected ? accent : "text-slate-400"}`}
            strokeWidth={2}
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
              {isLive ? "Trajectoire" : "Traj · Rejeu"}
            </span>
            {detected && onFit && <Maximize2 className="w-2.5 h-2.5 text-slate-400" strokeWidth={2} />}
          </div>
          {detected ? (
            <>
              <div className="font-mono text-sm font-medium text-slate-900 tabular-nums leading-tight mt-0.5">
                {traj.speed_kmh} km/h · {traj.compass}
              </div>
              {traj.eta_min !== null && traj.eta_min !== undefined ? (
                <div className={`font-mono text-[10px] ${accent} mt-1`}>
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
    </button>
  );
}
