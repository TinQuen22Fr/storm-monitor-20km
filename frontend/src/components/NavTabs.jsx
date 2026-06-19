import { NavLink } from "react-router-dom";
import { Activity, AlertTriangle, BarChart3, Cpu, PlayCircle, Shield } from "lucide-react";
import { useAuth } from "@/lib/auth";

const BASE_TABS = [
  { to: "/", end: true, icon: Activity, label: "Direct", testid: "nav-live" },
  { to: "/vigilance", icon: AlertTriangle, label: "Vigilance", testid: "nav-vigilance" },
  { to: "/replay", icon: PlayCircle, label: "Replay", testid: "nav-replay" },
  { to: "/detector", icon: Cpu, label: "Détecteur", testid: "nav-detector" },
  { to: "/historique", icon: BarChart3, label: "Historique", testid: "nav-history" },
];

export default function NavTabs({ variant = "inline" }) {
  const { user } = useAuth();
  const tabs = user?.is_admin
    ? [...BASE_TABS, { to: "/admin", icon: Shield, label: "Admin", testid: "nav-admin" }]
    : BASE_TABS;
  const cols = tabs.length;
  const base =
    variant === "floating"
      ? "fixed top-6 left-1/2 -translate-x-1/2 z-[1000] bg-white/95 backdrop-blur-md border border-slate-200 shadow-[0_2px_24px_rgba(0,0,0,0.06)]"
      : "w-full border border-slate-200 bg-white";

  const tabCls = ({ isActive }) =>
    `flex items-center justify-center gap-1.5 px-2 h-9 font-mono text-[10px] uppercase tracking-[0.16em] whitespace-nowrap transition-colors ${
      isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
    }`;

  return (
    <div
      className={`${base} grid grid-cols-3 gap-1 p-1`}
      style={{
        gridTemplateColumns: `repeat(3, minmax(0, 1fr))`,
      }}
      data-testid="nav-tabs"
    >
      {tabs.map(({ to, end, icon: Icon, label, testid }) => (
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
      <style>{`
        @media (min-width: 480px) {
          [data-testid="nav-tabs"] { grid-template-columns: repeat(${cols}, minmax(0, 1fr)) !important; }
        }
      `}</style>
    </div>
  );
}
