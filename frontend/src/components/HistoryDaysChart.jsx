import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";

export default function HistoryDaysChart({ days = 7 }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .get("/weather/history-days", { params: { days } })
      .then((r) => {
        if (cancelled) return;
        const arr = (r.data?.days || []).map((d) => ({
          date: d.date,
          label: new Date(d.date + "T00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "2-digit" }),
          precipitation: d.precipitation_total,
          storm_hours: d.storm_hours,
          max_cape: d.max_cape,
          max_gust: d.max_wind_gust,
          max_temp: d.max_temperature,
          min_temp: d.min_temperature,
        }));
        setData(arr);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [days]);

  const totalStormDays = data.filter((d) => d.storm_hours > 0).length;
  const totalPrecip = data.reduce((s, d) => s + (d.precipitation || 0), 0);

  return (
    <div className="border border-slate-200 p-6 bg-white" data-testid="history-days-chart">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
            Historique {days} jours
          </div>
          <div className="font-heading text-sm font-bold text-slate-900">Précipitations · mm</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl font-medium text-slate-900 leading-none">
            {totalStormDays}
            <span className="text-sm text-slate-400">/{data.length}</span>
          </div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mt-1">
            jours orageux
          </div>
        </div>
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
              axisLine={{ stroke: "#E2E8F0" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 9, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            <Tooltip
              cursor={{ fill: "rgba(15,23,42,0.04)" }}
              contentStyle={{
                background: "#0F172A",
                border: "none",
                borderRadius: 0,
                fontFamily: "IBM Plex Mono",
                fontSize: 11,
                color: "#fff",
                padding: "8px 12px",
              }}
              itemStyle={{ color: "#fff" }}
              labelStyle={{ color: "#94A3B8" }}
              formatter={(v, n, { payload }) => {
                if (n === "precipitation") return [`${v.toFixed(1)} mm · ${payload.storm_hours}h orage`, "Jour"];
                return [v, n];
              }}
            />
            <Bar dataKey="precipitation" radius={0}>
              {data.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.storm_hours > 0 ? "#DC2626" : d.precipitation > 0 ? "#0F172A" : "#CBD5E1"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex justify-between font-mono text-[10px] uppercase tracking-wider text-slate-400 mt-3">
        <span>Total : {totalPrecip.toFixed(1)} mm</span>
        <span>
          {loading ? "…" : `${data.length} jours`}
        </span>
      </div>
    </div>
  );
}
