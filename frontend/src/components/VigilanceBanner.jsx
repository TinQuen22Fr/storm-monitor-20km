import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Vigilance banner (Météo-France-style) computed locally from Open-Meteo.
 * Shows overall color for Lourdes dept + click-to-expand per-phenomenon grid.
 */
export default function VigilanceBanner() {
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancel = false;
    const load = async () => {
      try {
        const { data } = await api.get("/weather/vigilance");
        if (!cancel) setData(data);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 15 * 60_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, []);

  if (!data) return null;

  // La bannière reflète le NIVEAU DU DÉPARTEMENT SURVEILLÉ (65), pas le max
  // des voisins (un voisin orange ne doit pas afficher « orange » pour Lourdes)
  const lourdes = data.departements.find((d) => d.id === "65") || data.departements[0];
  const level = lourdes.max_level;
  const color = lourdes.max_color;
  const label = lourdes.max_label;

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
              Vigilance · {lourdes.max_level_fr}
            </span>
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-400 hidden sm:inline">
              Lourdes · Pyrénées
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
          {/* Phenomena grid for Lourdes (65) */}
          <div className="mt-3">
            <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500 mb-2">
              Phénomènes · {lourdes.name} ({lourdes.id})
            </div>
            <div className="grid grid-cols-3 gap-2">
              {lourdes.phenomena.map((p) => (
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
          <div className="mt-4">
            <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-500 mb-2">
              Départements voisins
            </div>
            <div className="flex flex-wrap gap-2">
              {data.departements
                .filter((d) => d.id !== "65")
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

          <div className="mt-3 font-mono text-[9px] text-slate-400 leading-relaxed">
            {data.disclaimer}
          </div>
        </div>
      )}
    </div>
  );
}
