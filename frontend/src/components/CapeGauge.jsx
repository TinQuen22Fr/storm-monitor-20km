export default function CapeGauge({ cape = 0, lightningPotential = 0 }) {
  // CAPE thresholds: <500 weak, 500-1500 moderate, 1500-2500 strong, >2500 extreme
  const max = 3000;
  const pct = Math.min(100, (cape / max) * 100);
  const level =
    cape < 500 ? "Faible" : cape < 1500 ? "Modéré" : cape < 2500 ? "Fort" : "Extrême";
  const levelColor =
    cape < 500
      ? "text-emerald-600"
      : cape < 1500
      ? "text-amber-600"
      : cape < 2500
      ? "text-orange-600"
      : "text-red-600";

  return (
    <div className="border border-slate-200 p-6 bg-white" data-testid="cape-gauge">
      <div className="flex items-start justify-between mb-5">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
            Potentiel convectif
          </div>
          <div className="font-heading text-sm font-bold text-slate-900">CAPE · J/kg</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-3xl font-medium text-slate-900 tracking-tight leading-none">
            {Math.round(cape || 0)}
          </div>
          <div className={`text-[11px] font-mono uppercase tracking-wider mt-1 ${levelColor}`}>
            {level}
          </div>
        </div>
      </div>

      {/* Gradient bar */}
      <div className="relative h-3 w-full bg-slate-100">
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(to right, #FCD34D 0%, #F59E0B 40%, #EA580C 70%, #DC2626 100%)",
            clipPath: `inset(0 ${100 - pct}% 0 0)`,
          }}
        />
        {/* Tick indicator */}
        <div
          className="absolute top-[-4px] w-[2px] h-5 bg-slate-900"
          style={{ left: `calc(${pct}% - 1px)` }}
        />
      </div>

      <div className="flex justify-between font-mono text-[9px] uppercase tracking-wider text-slate-400 mt-2">
        <span>0</span>
        <span>500</span>
        <span>1500</span>
        <span>2500</span>
        <span>3000+</span>
      </div>

      <div className="mt-5 pt-5 border-t border-slate-100 flex items-baseline justify-between">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
          Indice foudre (LPI)
        </span>
        <span className="font-mono text-lg font-medium text-slate-900">
          {(lightningPotential || 0).toFixed(1)}
        </span>
      </div>
    </div>
  );
}
