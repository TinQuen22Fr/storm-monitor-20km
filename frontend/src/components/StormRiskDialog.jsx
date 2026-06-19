import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { CalendarDays, CloudRain, Gauge, Thermometer, Wind, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { fmtLocalDate } from "@/lib/timeFormat";

function RiskBar({ score, color }) {
  return (
    <div className="w-full h-1.5 bg-slate-100 relative overflow-hidden">
      <div
        className="absolute left-0 top-0 h-full transition-all"
        style={{ width: `${score}%`, background: color }}
      />
    </div>
  );
}

function DayCard({ day, isToday, isTomorrow }) {
  const d = new Date(day.date + "T00:00");
  const label = isToday
    ? "Aujourd'hui"
    : isTomorrow
    ? "Demain"
    : fmtLocalDate(d, { weekday: "long", day: "2-digit", month: "short" });

  return (
    <div
      className="border border-slate-200 bg-white p-5 hover:border-slate-400 transition-colors"
      data-testid={`risk-day-${day.date}`}
    >
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
            {fmtLocalDate(d, { weekday: "short" })}
          </div>
          <div className="font-heading text-lg font-bold text-slate-900 leading-tight capitalize">
            {label}
          </div>
        </div>
        <div className="text-right">
          <div
            className="font-mono text-3xl font-medium leading-none tabular-nums"
            style={{ color: day.risk.color }}
          >
            {day.risk.score}
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.2em] mt-1 font-semibold"
            style={{ color: day.risk.color }}
          >
            {day.risk.label}
          </div>
        </div>
      </div>

      <RiskBar score={day.risk.score} color={day.risk.color} />

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5 text-[11px]">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-400 font-mono text-[10px] uppercase tracking-wider">
            <Zap className="w-3 h-3" /> CAPE
          </span>
          <span className="font-mono text-slate-900 tabular-nums">
            {Math.round(day.max_cape)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-400 font-mono text-[10px] uppercase tracking-wider">
            <Gauge className="w-3 h-3" /> LPI
          </span>
          <span className="font-mono text-slate-900 tabular-nums">
            {day.max_lightning_potential.toFixed(1)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-400 font-mono text-[10px] uppercase tracking-wider">
            <CloudRain className="w-3 h-3" /> Prob.
          </span>
          <span className="font-mono text-slate-900 tabular-nums">
            {day.peak_precip_probability}%
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-400 font-mono text-[10px] uppercase tracking-wider">
            <Wind className="w-3 h-3" /> Rafale
          </span>
          <span className="font-mono text-slate-900 tabular-nums">
            {Math.round(day.max_wind_gust)} km/h
          </span>
        </div>
        {day.max_temperature !== null && (
          <div className="col-span-2 flex items-center justify-between pt-2 border-t border-slate-100">
            <span className="flex items-center gap-1.5 text-slate-400 font-mono text-[10px] uppercase tracking-wider">
              <Thermometer className="w-3 h-3" /> Temp min / max
            </span>
            <span className="font-mono text-slate-900 tabular-nums">
              {day.min_temperature?.toFixed(0)}° / {day.max_temperature?.toFixed(0)}°
            </span>
          </div>
        )}
        {day.peak_hour && (
          <div className="col-span-2 flex items-center justify-between">
            <span className="text-slate-400 font-mono text-[10px] uppercase tracking-wider">
              Heure de pic
            </span>
            <span className="font-mono text-slate-900 tabular-nums">{day.peak_hour}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function StormRiskDialog({ lat, lon }) {
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .get("/forecast/storm-risk", { params: { lat, lon, days: 7 } })
      .then((r) => setDays(r.data?.days || []))
      .finally(() => setLoading(false));
  }, [open, lat, lon]);

  const today = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="mt-2 w-full flex items-center justify-between px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
          data-testid="open-storm-risk"
        >
          <span className="flex items-center gap-2">
            <CalendarDays className="w-4 h-4" strokeWidth={1.8} />
            Prévisions orage · 7 jours
          </span>
          <span className="font-mono text-sm">→</span>
        </button>
      </DialogTrigger>
      <DialogContent
        className="rounded-none border-slate-900 max-w-5xl p-0 max-h-[90vh] flex flex-col overflow-hidden"
        data-testid="storm-risk-dialog"
      >
        <div className="p-8 border-b border-slate-100 shrink-0">
          <DialogHeader>
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-slate-400 mb-2">
              Prévisions orage · Lourdes
            </div>
            <DialogTitle className="font-heading text-3xl font-black tracking-tight text-slate-900">
              Risque sur 7 jours.
            </DialogTitle>
            <DialogDescription className="text-slate-500 mt-2">
              Score pondéré basé sur CAPE, indice foudre (LPI), probabilité de précipitations et heures orageuses
              prévues pour chaque jour.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="p-8 overflow-y-auto flex-1 min-h-0" data-testid="storm-risk-scroll">
          {loading ? (
            <div className="text-center text-sm text-slate-400 font-mono py-12">
              Chargement…
            </div>
          ) : days.length === 0 ? (
            <div className="text-center text-sm text-slate-400 font-mono py-12">
              Aucune donnée disponible
            </div>
          ) : (
            <>
              {/* Scale legend */}
              <div className="mb-6 flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-slate-500">
                <span className="text-slate-400">Échelle :</span>
                {[
                  { label: "Nul", color: "#10B981" },
                  { label: "Faible", color: "#D97706" },
                  { label: "Modéré", color: "#EA580C" },
                  { label: "Élevé", color: "#DC2626" },
                  { label: "Extrême", color: "#991B1B" },
                ].map((l) => (
                  <span key={l.label} className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5" style={{ background: l.color }} />
                    {l.label}
                  </span>
                ))}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {days.map((day) => (
                  <DayCard
                    key={day.date}
                    day={day}
                    isToday={day.date === today}
                    isTomorrow={day.date === tomorrow}
                  />
                ))}
              </div>

              <div className="mt-6 pt-6 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                Source · Open-Meteo · modèle ICON-D2 / ARPEGE
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
