import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtLocalTime } from "@/lib/timeFormat";

export default function ForecastChart({ hourly = [] }) {
  const data = hourly.slice(0, 24).map((h) => ({
    time: fmtLocalTime(h.time, { minute: undefined }),
    prob: h.precipitation_probability || 0,
    lp: h.lightning_potential || 0,
    cape: h.cape || 0,
  }));

  const peak = data.reduce((m, d) => Math.max(m, d.prob), 0);

  return (
    <div className="border border-slate-200 p-6 bg-white" data-testid="forecast-chart">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
            Prévision 24h
          </div>
          <div className="font-heading text-sm font-bold text-slate-900">
            Probabilité précipitations
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl font-medium text-slate-900 leading-none">
            {peak}
            <span className="text-sm text-slate-400">%</span>
          </div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 mt-1">
            pic
          </div>
        </div>
      </div>

      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="probFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0F172A" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#0F172A" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" vertical={false} />
            <XAxis
              dataKey="time"
              interval={3}
              tick={{ fontSize: 9, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
              axisLine={{ stroke: "#E2E8F0" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 9, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
              axisLine={false}
              tickLine={false}
              width={28}
              domain={[0, 100]}
            />
            <Tooltip
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
              formatter={(v) => [`${v}%`, "probabilité"]}
            />
            <Area
              type="monotone"
              dataKey="prob"
              stroke="#0F172A"
              strokeWidth={2}
              fill="url(#probFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
