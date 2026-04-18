import { AlertTriangle, Compass, Gauge, Timer } from "lucide-react";

export default function ApproachAlert({ approach }) {
  if (!approach?.approaching) return null;
  const eta = Math.max(1, Math.round(approach.eta_min || 0));
  return (
    <div
      className="border border-red-600 bg-red-50 p-4 relative overflow-hidden"
      data-testid="approach-alert"
    >
      {/* Animated scan line */}
      <div
        className="absolute inset-0 pointer-events-none opacity-60"
        style={{
          background:
            "repeating-linear-gradient(45deg, transparent 0 10px, rgba(220,38,38,0.06) 10px 20px)",
        }}
      />
      <div className="relative flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" strokeWidth={2.5} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="live-dot" />
            <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-red-700 font-semibold">
              Orage en approche
            </span>
          </div>
          <div className="font-heading text-base font-black text-red-900 leading-tight tracking-tight">
            Arrivée estimée dans {eta}&nbsp;min
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] font-mono uppercase tracking-wider">
            <div className="flex flex-col">
              <span className="flex items-center gap-1 text-red-700/70">
                <Gauge className="w-3 h-3" /> Distance
              </span>
              <span className="text-red-900 font-medium text-sm mt-0.5">
                {approach.min_distance_km} km
              </span>
            </div>
            <div className="flex flex-col">
              <span className="flex items-center gap-1 text-red-700/70">
                <Timer className="w-3 h-3" /> Vitesse
              </span>
              <span className="text-red-900 font-medium text-sm mt-0.5">
                {approach.speed_kmh} km/h
              </span>
            </div>
            <div className="flex flex-col">
              <span className="flex items-center gap-1 text-red-700/70">
                <Compass className="w-3 h-3" /> Venant
              </span>
              <span className="text-red-900 font-medium text-sm mt-0.5">
                {approach.from_compass}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
