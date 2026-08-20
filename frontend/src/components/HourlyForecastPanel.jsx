import { useEffect, useState } from "react";
import {
  Area, AreaChart, Brush, LabelList, ResponsiveContainer, XAxis, YAxis, Tooltip,
} from "recharts";
import {
  Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow,
  CloudSun, Droplets, Gauge, Loader2, Sun, Sunrise, Sunset, Thermometer, Wind, Zap,
} from "lucide-react";
import { api } from "@/lib/api";
// Les heures Open-Meteo (timezone=auto) sont DÉJÀ locales : simple extraction HH:MM
const hh = (iso) => (iso ? iso.split("T")[1]?.slice(0, 5) : "—");

function iconForCode(code, props) {
  if (code == null) return <Cloud {...props} />;
  if ([95, 96, 99].includes(code)) return <CloudLightning {...props} className={`${props.className} text-red-600`} />;
  if ([71, 73, 75, 77, 85, 86].includes(code)) return <CloudSnow {...props} className={`${props.className} text-sky-500`} />;
  if ([61, 63, 65, 80, 81, 82].includes(code)) return <CloudRain {...props} className={`${props.className} text-blue-600`} />;
  if ([51, 53, 55, 56, 57, 66, 67].includes(code)) return <CloudDrizzle {...props} className={`${props.className} text-blue-500`} />;
  if ([45, 48].includes(code)) return <CloudFog {...props} className={`${props.className} text-slate-400`} />;
  if (code === 0) return <Sun {...props} className={`${props.className} text-amber-500`} />;
  if ([1, 2].includes(code)) return <CloudSun {...props} className={`${props.className} text-amber-500`} />;
  return <Cloud {...props} className={`${props.className} text-slate-400`} />;
}

function uvLabel(uv) {
  if (uv == null) return "—";
  if (uv < 3) return "Faible";
  if (uv < 6) return "Modéré";
  if (uv < 8) return "Élevé";
  if (uv < 11) return "Très élevé";
  return "Extrême";
}

function compass(deg) {
  if (deg == null) return "";
  const dirs = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
  return dirs[Math.round(deg / 45) % 8];
}

function StatCard({ icon, label, value, sub, testid }) {
  return (
    <div className="border border-slate-200 bg-white p-4" data-testid={testid}>
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
        {icon}
        {label}
      </div>
      <div className="font-heading text-xl font-black text-slate-900 mt-1.5 leading-none tabular-nums">
        {value}
      </div>
      {sub && <div className="font-mono text-[10px] text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

export default function HourlyForecastPanel({ lat, lon, name }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    const load = async () => {
      setLoading(true);
      try {
        const { data: d } = await api.get("/weather/hourly", { params: { lat, lon } });
        if (!cancel) setData(d?.hourly ? d : null);
      } catch {
        if (!cancel) setData(null);
      } finally {
        if (!cancel) setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 10 * 60_000);
    return () => { cancel = true; clearInterval(t); };
  }, [lat, lon]);

  if (loading && !data) {
    return (
      <div className="border border-slate-200 bg-white p-10 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
      </div>
    );
  }
  if (!data) return null;

  const hourly = data.hourly || [];
  const now = hourly[0] || {};
  const daily = data.daily || {};
  const chartData = hourly.map((h, i) => ({
    ...h,
    label: i === 0 ? "Maint." : hh(h.time),
    tRound: h.temperature != null ? Math.round(h.temperature) : null,
  }));
  const stormHours = hourly.filter((h) => h.is_storm || (h.storm_prob ?? 0) >= 30);
  const peakStorm = stormHours.reduce((m, h) => ((h.storm_prob ?? 0) > (m?.storm_prob ?? -1) ? h : m), null);

  return (
    <div className="border border-slate-200 bg-white" data-testid="hourly-forecast-panel">
      <div className="px-5 pt-5 flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
            Prévisions horaires · 24 h
          </div>
          <div className="font-heading text-lg font-black tracking-tight text-slate-900 mt-0.5">
            {name}
          </div>
        </div>
        {peakStorm && (
          <div className="flex items-center gap-2 border border-red-200 bg-red-50 px-3 py-2" data-testid="hourly-storm-badge">
            <Zap className="w-3.5 h-3.5 text-red-600" strokeWidth={2.2} />
            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-red-700">
              Orage · pic {hh(peakStorm.time)} · {peakStorm.storm_prob}%
            </div>
          </div>
        )}
      </div>

      {/* Courbe de température */}
      <div className="px-2 mt-2">
        <ResponsiveContainer width="100%" height={120}>
          <AreaChart data={chartData} margin={{ top: 22, right: 14, left: 14, bottom: 0 }}>
            <defs>
              <linearGradient id="tempFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#F59E0B" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#F59E0B" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} interval={2} axisLine={false} tickLine={false} />
            <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
            <Tooltip
              contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
              labelStyle={{ color: "#94A3B8" }}
              formatter={(v, n) => (n === "temperature" ? [`${v?.toFixed(1)}°C`, "Température"] : [v, n])}
            />
            <Area type="monotone" dataKey="temperature" stroke="#F59E0B" strokeWidth={2.5} fill="url(#tempFill)" dot={false}>
              <LabelList dataKey="tRound" position="top" formatter={(v) => (v != null ? `${v}°` : "")} style={{ fontSize: 10, fontFamily: "monospace", fill: "#0F172A", fontWeight: 600 }} />
            </Area>
            {/* Zoom tactile : glisser/pincer les poignées pour agrandir une tranche horaire */}
            <Brush
              dataKey="label"
              height={18}
              travellerWidth={12}
              stroke="#94A3B8"
              fill="#F8FAFC"
              tickFormatter={() => ""}
            />
          </AreaChart>
        </ResponsiveContainer>
        <div className="px-3 pb-1 font-mono text-[9px] text-slate-400 text-center">
          Faites glisser les poignées ci-dessus pour zoomer sur une tranche horaire
        </div>
      </div>

      {/* Bande horaire défilable */}
      <div className="overflow-x-auto border-t border-slate-100" data-testid="hourly-strip">
        <div className="flex min-w-max">
          {chartData.map((h, i) => (
            <div
              key={h.time}
              className={`flex flex-col items-center gap-1.5 px-3 py-3 border-r border-slate-100 min-w-[68px] ${(h.is_storm || (h.storm_prob ?? 0) >= 60) ? "bg-red-50/70" : (h.storm_prob ?? 0) >= 30 ? "bg-amber-50/60" : i === 0 ? "bg-slate-50" : ""}`}
              data-testid={`hourly-cell-${i}`}
            >
              <div className="font-mono text-[10px] text-slate-500">{h.label}</div>
              {iconForCode(h.weather_code, { size: 20, strokeWidth: 1.8, className: "" })}
              <div className="font-mono text-sm font-semibold text-slate-900 tabular-nums">
                {h.temperature != null ? `${Math.round(h.temperature)}°` : "—"}
              </div>
              <div className={`flex items-center gap-0.5 font-mono text-[10px] tabular-nums ${h.is_storm ? "text-red-600 font-bold" : "text-blue-600"}`}>
                {h.precip_prob != null ? `${Math.round(h.precip_prob)}%` : "—"}
              </div>
              <div
                className={`flex items-center gap-0.5 font-mono text-[10px] tabular-nums ${
                  (h.storm_prob ?? 0) >= 60 ? "text-red-600 font-bold" : (h.storm_prob ?? 0) >= 30 ? "text-amber-600 font-semibold" : "text-slate-300"
                }`}
                title="Probabilité d'orage"
              >
                <Zap size={9} strokeWidth={2.5} />
                {h.storm_prob != null ? `${h.storm_prob}%` : "—"}
              </div>
              <div className="font-mono text-[9px] text-slate-400 tabular-nums">
                {h.wind_speed != null ? `${Math.round(h.wind_speed)} km/h` : ""}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Cartes conditions du moment */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 p-5 border-t border-slate-100">
        <StatCard
          icon={<Sun className="w-3.5 h-3.5 text-amber-500" />}
          label="UV"
          value={now.uv != null ? uvLabel(now.uv) : "—"}
          sub={`indice ${now.uv != null ? Math.round(now.uv * 10) / 10 : "—"} · max jour ${daily.uv_max != null ? Math.round(daily.uv_max * 10) / 10 : "—"}`}
          testid="stat-uv"
        />
        <StatCard
          icon={<Droplets className="w-3.5 h-3.5 text-blue-500" />}
          label="Humidité"
          value={now.humidity != null ? `${Math.round(now.humidity)}%` : "—"}
          testid="stat-humidity"
        />
        <StatCard
          icon={<Thermometer className="w-3.5 h-3.5 text-red-500" />}
          label="Ressenti"
          value={now.feels_like != null ? `${Math.round(now.feels_like)}°` : "—"}
          sub={`min ${daily.tmin != null ? Math.round(daily.tmin) : "—"}° · max ${daily.tmax != null ? Math.round(daily.tmax) : "—"}°`}
          testid="stat-feels"
        />
        <StatCard
          icon={<Wind className="w-3.5 h-3.5 text-slate-500" />}
          label="Vent"
          value={now.wind_speed != null ? `${Math.round(now.wind_speed)} km/h` : "—"}
          sub={now.wind_dir != null ? `direction ${compass(now.wind_dir)} (${Math.round(now.wind_dir)}°)` : ""}
          testid="stat-wind"
        />
        <StatCard
          icon={<Gauge className="w-3.5 h-3.5 text-slate-500" />}
          label="Pression"
          value={now.pressure != null ? `${Math.round(now.pressure)}` : "—"}
          sub="hPa surface"
          testid="stat-pressure"
        />
        <StatCard
          icon={<Sunrise className="w-3.5 h-3.5 text-amber-500" />}
          label="Soleil"
          value={
            <span className="flex flex-col gap-0.5 text-base">
              <span className="flex items-center gap-1.5"><Sunrise size={13} className="text-amber-500" /> {daily.sunrise ? hh(daily.sunrise) : "—"}</span>
              <span className="flex items-center gap-1.5"><Sunset size={13} className="text-orange-600" /> {daily.sunset ? hh(daily.sunset) : "—"}</span>
            </span>
          }
          sub="lever · coucher"
          testid="stat-sun"
        />
      </div>
    </div>
  );
}
