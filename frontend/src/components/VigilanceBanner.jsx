import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Vigilance banner (MeteoAlarm → Météo-France) centred on the currently
 * watched zone. When `lat` / `lon` are provided the banner shows the dept
 * containing the point plus its real bordering departements.
 */
export default function VigilanceBanner({ lat, lon, zoneName }) {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancel = false;
    const load = async () => {
      try {
        const params = {};
        if (typeof lat === "number" && typeof lon === "number") {
          params.lat = lat;
          params.lon = lon;
          if (zoneName) params.zone = zoneName;
        }
        const { data } = await api.get("/weather/vigilance", { params });
        if (!cancel) setData(data);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 15 * 60_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, [lat, lon, zoneName]);

  if (!data) return null;

  // The banner reflects the LEVEL OF THE WATCHED DEPARTEMENT — not the max
  // across neighbours. `primary_id` is set when the API is called with lat/lon;
  // otherwise we fall back to the historical Lourdes view (dept 65).
  const primaryId = data.primary_id || "65";
  const primary =
    data.departements.find((d) => d.id === primaryId) || data.departements[0];
  const level = primary.max_level;
  const color = primary.max_color;
  const label = primary.max_label;
  const zoneLabel = data.zone_name || zoneName || "Lourdes";

  // Never hide: even "vert" is shown so users know we checked
  const headerBg = level === 1 ? "#F0FDF4" : level === 2 ? "#FFFBEB" : level === 3 ? "#FFF7ED" : "#FEF2F2";
  const headerText = level >= 3 ? "#991B1B" : level === 2 ? "#78350F" : "#166534";

  return (
    <div
      className="border-b border-slate-200"
      data-testid="vigilance-banner"
      style={{ background: headerBg }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-6 py-3 text-left"
        data-testid="vigilance-toggle"
      >
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ background: color, boxShadow: `0 0 0 3px ${color}22` }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] font-semibold" style={{ color: headerText }}>
              Vigilance · {primary.max_level_fr}
            </span>
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-400 hidden sm:inline">
              {zoneLabel} · {primary.name}
            </span>
          </div>
          <div className="text-sm font-medium truncate" style={{ color: headerText }}>
            {label}
          </div>
        </div>
        {level >= 3 && <AlertTriangle className="w-5 h-5 shrink-0" style={{ color }} strokeWidth={2} />}
        {expanded ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}
      </button>

      {expanded && (
        <div className="px-6 pb-4 border-t border-slate-200/60 bg-white/40" data-testid="vigilance-expanded">
          {/* Phenomena grid for the watched departement */}
          <div className="mt-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500 mb-2">
              Phénomènes · {primary.name} ({primary.id})
            </div>
            <div className="grid grid-cols-3 gap-2">
              {primary.phenomena.map((p) => (
                <div
                  key={p.key}
                  className="border border-slate-200 bg-white p-2"
                  data-testid={`vigilance-phenomenon-${p.key}`}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ background: p.color }}
                    />
                    <span className="font-mono text-[9px] uppercase tracking-wider text-slate-500 truncate">
                      {p.label}
                    </span>
                  </div>
                  <div className="font-mono text-[10px] tabular-nums text-slate-700">
                    Auj. <span style={{ color: p.today >= 3 ? "#DC2626" : p.today === 2 ? "#CC9F00" : "#10B981" }}>{
                      ["-", "vert", "jaune", "orange", "rouge"][p.today]
                    }</span>
                  </div>
                  <div className="font-mono text-[10px] tabular-nums text-slate-700">
                    Dem. <span style={{ color: p.tomorrow >= 3 ? "#DC2626" : p.tomorrow === 2 ? "#CC9F00" : "#10B981" }}>{
                      ["-", "vert", "jaune", "orange", "rouge"][p.tomorrow]
                    }</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Neighbouring depts */}
          {data.departements.length > 1 && (
            <div className="mt-4">
              <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500 mb-2">
                Départements voisins
              </div>
              <div className="flex flex-wrap gap-2">
                {data.departements
                  .filter((d) => d.id !== primaryId)
                  .map((d) => (
                    <div
                      key={d.id}
                      className="flex items-center gap-2 border border-slate-200 bg-white px-2 py-1.5"
                      data-testid={`vigilance-dept-${d.id}`}
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{
                          background:
                            data.levels_meta.find((l) => l.level === d.max_level)?.color,
                        }}
                      />
                      <span className="font-mono text-[10px] text-slate-700">
                        {d.name} ({d.id})
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          <div className="mt-3 font-mono text-[9px] text-slate-400 leading-relaxed">
            {data.disclaimer}
          </div>
        </div>
      )}
    </div>
  );
}
