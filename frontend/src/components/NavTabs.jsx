import { NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart3, Cpu, PlayCircle } from "lucide-react";

const TABS = [
  { to: "/", end: true, icon: Activity, label: "Direct", testid: "nav-live" },
  { to: "/vigilance", icon: AlertTriangle, label: "Vigilance", testid: "nav-vigilance" },
  { to: "/replay", icon: PlayCircle, label: "Replay", testid: "nav-replay" },
  { to: "/detector", icon: Cpu, label: "Détecteur", testid: "nav-detector" },
  { to: "/historique", icon: BarChart3, label: "Historique", testid: "nav-history" },
];

export default function NavTabs({ variant = "inline" }) {
  const base =
    variant === "floating"
      ? "fixed top-6 left-1/2 -translate-x-1/2 z-[1000] bg-white/95 backdrop-blur-md border border-slate-200 shadow-[0_2px_24px_rgba(0,0,0,0.06)]"
      : "w-full border border-slate-200 bg-white";

  // Grid layout: 3 cols at narrow widths, 5 cols at wider widths — no clipping ever.
  // 3 cols < 480px (sidebar inline) → 2 lignes (3 + 2)
  // 5 cols ≥ 480px (header desktop) → 1 ligne
  const tabCls = ({ isActive }) =>
    `flex items-center justify-center gap-1.5 px-2 h-9 font-mono text-[10px] uppercase tracking-[0.16em] whitespace-nowrap transition-colors ${
      isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
    }`;

  return (
    <div
      className={`${base} grid grid-cols-3 min-[480px]:grid-cols-5 gap-1 p-1`}
      data-testid="nav-tabs"
    >
      {TABS.map(({ to, end, icon: Icon, label, testid }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={tabCls}
          data-testid={testid}
        >
          <Icon className="w-3.5 h-3.5 shrink-0" strokeWidth={2} />
          <span className="truncate">{label}</span>
        </NavLink>
      ))}
    </div>
  );
}
