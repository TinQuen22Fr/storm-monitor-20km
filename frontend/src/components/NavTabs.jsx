import { NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart3 } from "lucide-react";

export default function NavTabs({ variant = "inline" }) {
  const base =
    variant === "floating"
      ? "fixed top-6 left-1/2 -translate-x-1/2 z-[1000] bg-white/95 backdrop-blur-md border border-slate-200 shadow-[0_2px_24px_rgba(0,0,0,0.06)]"
      : "w-full border border-slate-200 bg-white";
  return (
    <div className={`${base} flex p-1`} data-testid="nav-tabs">
      <NavLink
        to="/"
        end
        className={({ isActive }) =>
          `flex-1 flex items-center justify-center gap-2 px-3 h-9 font-mono text-[10px] uppercase tracking-[0.2em] transition-colors ${
            isActive
              ? "bg-slate-900 text-white"
              : "text-slate-600 hover:text-slate-900"
          }`
        }
        data-testid="nav-live"
      >
        <Activity className="w-3.5 h-3.5" strokeWidth={2} />
        Direct
      </NavLink>
      <NavLink
        to="/vigilance"
        className={({ isActive }) =>
          `flex-1 flex items-center justify-center gap-2 px-3 h-9 font-mono text-[10px] uppercase tracking-[0.2em] transition-colors ${
            isActive
              ? "bg-slate-900 text-white"
              : "text-slate-600 hover:text-slate-900"
          }`
        }
        data-testid="nav-vigilance"
      >
        <AlertTriangle className="w-3.5 h-3.5" strokeWidth={2} />
        Vigilance
      </NavLink>
      <NavLink
        to="/historique"
        className={({ isActive }) =>
          `flex-1 flex items-center justify-center gap-2 px-3 h-9 font-mono text-[10px] uppercase tracking-[0.2em] transition-colors ${
            isActive
              ? "bg-slate-900 text-white"
              : "text-slate-600 hover:text-slate-900"
          }`
        }
        data-testid="nav-history"
      >
        <BarChart3 className="w-3.5 h-3.5" strokeWidth={2} />
        Historique
      </NavLink>
    </div>
  );
}
