import { NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart3, Cpu, PlayCircle } from "lucide-react";

export default function NavTabs({ variant = "inline" }) {
  const base =
    variant === "floating"
      ? "fixed top-6 left-1/2 -translate-x-1/2 z-[1000] bg-white/95 backdrop-blur-md border border-slate-200 shadow-[0_2px_24px_rgba(0,0,0,0.06)]"
      : "w-full border border-slate-200 bg-white";
  const tabCls = ({ isActive }) =>
    `flex-1 flex items-center justify-center gap-1.5 px-2 h-9 font-mono text-[10px] uppercase tracking-[0.18em] transition-colors ${
      isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
    }`;
  return (
    <div className={`${base} flex p-1`} data-testid="nav-tabs">
      <NavLink to="/" end className={tabCls} data-testid="nav-live">
        <Activity className="w-3.5 h-3.5" strokeWidth={2} />
        Direct
      </NavLink>
      <NavLink to="/vigilance" className={tabCls} data-testid="nav-vigilance">
        <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} />
        Vigilance
      </NavLink>
      <NavLink to="/replay" className={tabCls} data-testid="nav-replay">
        <PlayCircle className="w-3.5 h-3.5" strokeWidth={2} />
        Replay
      </NavLink>
      <NavLink to="/detector" className={tabCls} data-testid="nav-detector">
        <Cpu className="w-3.5 h-3.5" strokeWidth={2} />
        Détecteur
      </NavLink>
      <NavLink to="/historique" className={tabCls} data-testid="nav-history">
        <BarChart3 className="w-3.5 h-3.5" strokeWidth={2} />
        Historique
      </NavLink>
    </div>
  );
}
