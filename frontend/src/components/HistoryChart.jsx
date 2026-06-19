import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtLocalTime } from "@/lib/timeFormat";

export default function HistoryChart({ hourly = [] }) {
  const data = hourly.map((h) => ({
    time: fmtLocalTime(h.time),
    precipitation: h.precipitation || 0,
    cape: h.cape || 0,
    lp: h.lightning_potential || 0,
    storm: h.is_storm,
  }));

  const storms = data.filter((d) => d.storm).length;

  return (
    <div className="border border-slate-200 p-6 bg-white" data-testid="history-chart">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
            Historique 24h
          </div>
          <div className="font-heading text-sm font-bold text-slate-900">Précipitations · mm</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl font-medium text-slate-900 leading-none">
            {storms}
          </div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mt-1">
            heures orageuses
          </div>
        </div>
      </div>

      <div className="h-40" data-testid="history-chart-inner">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" vertical={false} />
            <XAxis
              dataKey="time"
              interval={Math.max(1, Math.floor(data.length / 6))}
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
              labelStyle={{ color: "#94A3B8" }}
              itemStyle={{ color: "#fff" }}
              formatter={(v, n) => [`${Number(v).toFixed(2)} ${n === "precipitation" ? "mm" : ""}`, n]}
            />
            <Bar
              dataKey="precipitation"
              fill="#0F172A"
              radius={0}
              shape={(props) => {
                const { x, y, width, height, payload } = props;
                const fill = payload.storm ? "#DC2626" : "#0F172A";
                return <rect x={x} y={y} width={width} height={height} fill={fill} />;
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex gap-4 mt-3 text-[10px] font-mono uppercase tracking-wider text-slate-400">
        <span className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 bg-slate-900" /> Pluie
        </span>
        <span className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 bg-red-600" /> Orage
        </span>
      </div>
    </div>
  );
}
