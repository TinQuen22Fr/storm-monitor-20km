import { Droplets, Gauge, Thermometer, Wind } from "lucide-react";

function Cell({ label, value, unit, icon: Icon, testId }) {
  return (
    <div className="border border-slate-200 p-5 bg-white hover:border-slate-400 transition-colors" data-testid={testId}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">{label}</span>
        <Icon className="w-4 h-4 text-slate-300" strokeWidth={1.5} />
      </div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-3xl font-medium text-slate-900 tracking-tight">
          {value ?? "—"}
        </span>
        <span className="font-mono text-xs text-slate-400">{unit}</span>
      </div>
    </div>
  );
}

export default function CurrentConditions({ current }) {
  const c = current?.current || {};
  const fmt = (v, d = 0) => (v === null || v === undefined ? null : Number(v).toFixed(d));

  return (
    <div className="grid grid-cols-2 gap-0 -m-px" data-testid="current-conditions">
      <Cell label="Température" value={fmt(c.temperature_2m, 1)} unit="°C" icon={Thermometer} testId="cond-temp" />
      <Cell label="Vent" value={fmt(c.wind_speed_10m, 0)} unit="km/h" icon={Wind} testId="cond-wind" />
      <Cell label="Humidité" value={fmt(c.relative_humidity_2m, 0)} unit="%" icon={Droplets} testId="cond-humidity" />
      <Cell label="Pression" value={fmt(c.pressure_msl, 0)} unit="hPa" icon={Gauge} testId="cond-pressure" />
    </div>
  );
}
