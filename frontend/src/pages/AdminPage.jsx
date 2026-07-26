import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { CheckCircle, MailCheck, RefreshCw, Shield, ShieldOff, Trash2, UserX } from "lucide-react";
import { toast } from "sonner";
import NavTabs from "@/components/NavTabs";
import { useAuth } from "@/lib/auth";
import { adminDeleteUser, adminForceVerify, adminListUsers, adminToggleDisable } from "@/lib/api";
import { fmtLocal } from "@/lib/timeFormat";

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // all | verified | unverified | disabled
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminListUsers();
      setUsers(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user?.is_admin) load();
  }, [user, load]);

  if (authLoading) return null;
  if (!user || !user.is_admin) return <Navigate to="/" replace />;

  const filtered = users.filter((u) => {
    if (filter === "verified" && !u.email_verified) return false;
    if (filter === "unverified" && u.email_verified) return false;
    if (filter === "disabled" && !u.disabled) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!u.email.includes(q) && !(u.name || "").toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const counts = {
    total: users.length,
    verified: users.filter((u) => u.email_verified).length,
    unverified: users.filter((u) => !u.email_verified).length,
    disabled: users.filter((u) => u.disabled).length,
  };

  const handleDelete = async (u) => {
    if (!window.confirm(`Supprimer définitivement le compte ${u.email} et ses favoris ?`)) return;
    try {
      await adminDeleteUser(u.id);
      toast.success("Compte supprimé");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur");
    }
  };

  const handleVerify = async (u) => {
    try {
      await adminForceVerify(u.id);
      toast.success(`${u.email} forcé en vérifié`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur");
    }
  };

  const handleDisable = async (u) => {
    try {
      const res = await adminToggleDisable(u.id);
      toast.success(res.disabled ? "Compte désactivé" : "Compte réactivé");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur");
    }
  };

  return (
    <div className="min-h-screen w-full bg-slate-50/70" data-testid="admin-page">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-6 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-4 h-4 text-violet-700" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-violet-700 font-semibold">
                Administration
              </span>
            </div>
            <h1 className="font-heading text-3xl lg:text-4xl font-black tracking-tighter text-slate-900">
              Gestion des comptes
            </h1>
            <p className="text-sm text-slate-500 mt-2 max-w-xl">
              Réservé à l&apos;administrateur. Liste, vérification et modération des inscriptions.
            </p>
          </div>
          <div className="w-full lg:w-80 shrink-0">
            <NavTabs variant="inline" />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 lg:px-8 py-8 lg:py-10 space-y-6">
        {/* Stats */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-0 -m-px" data-testid="admin-stats">
          {[
            { label: "Total comptes", value: counts.total, key: "all" },
            { label: "Vérifiés", value: counts.verified, key: "verified" },
            { label: "Non vérifiés", value: counts.unverified, key: "unverified", accent: counts.unverified > 0 ? "border-amber-300 bg-amber-50" : "" },
            { label: "Désactivés", value: counts.disabled, key: "disabled" },
          ].map((s) => (
            <button
              key={s.key}
              onClick={() => setFilter(s.key)}
              className={`text-left border p-6 transition-colors ${
                filter === s.key ? "border-slate-900 bg-slate-900 text-white" : s.accent || "border-slate-200 bg-white hover:border-slate-400"
              }`}
              data-testid={`admin-stat-${s.key}`}
            >
              <div className={`text-[10px] font-mono uppercase tracking-[0.2em] mb-2 ${filter === s.key ? "text-slate-400" : "text-slate-400"}`}>
                {s.label}
              </div>
              <span className="font-mono text-4xl font-medium tabular-nums leading-none">
                {s.value}
              </span>
            </button>
          ))}
        </section>

        {/* Search + refresh */}
        <section className="flex flex-col md:flex-row gap-3 items-stretch md:items-center">
          <input
            type="search"
            placeholder="Filtrer par email ou nom…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 px-4 h-10 border border-slate-300 bg-white font-mono text-sm focus:outline-none focus:border-slate-900"
            data-testid="admin-search"
          />
          <button
            onClick={load}
            disabled={loading}
            className="px-4 h-10 border border-slate-300 bg-white hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-50 inline-flex items-center gap-2 justify-center"
            data-testid="admin-refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Rafraîchir
          </button>
        </section>

        {/* Users table */}
        <section className="border border-slate-200 bg-white overflow-x-auto" data-testid="admin-users-table">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-[10px] font-mono uppercase tracking-wider text-slate-400 border-b border-slate-200">
                <th className="text-left px-6 py-3 font-medium">Email</th>
                <th className="text-left px-4 py-3 font-medium">Nom</th>
                <th className="text-center px-3 py-3 font-medium">Statut</th>
                <th className="text-right px-3 py-3 font-medium">Favoris</th>
                <th className="text-left px-4 py-3 font-medium">Créé</th>
                <th className="text-right px-6 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && !loading && (
                <tr><td colSpan={6} className="text-center text-slate-400 py-10 font-mono text-xs">Aucun compte ne correspond.</td></tr>
              )}
              {filtered.map((u) => (
                <tr
                  key={u.id}
                  className={`border-t border-slate-100 ${u.disabled ? "bg-red-50/40" : "hover:bg-slate-50"}`}
                  data-testid={`admin-user-row-${u.id}`}
                >
                  <td className="px-6 py-3 font-mono text-slate-900 flex items-center gap-2">
                    {u.email}
                    {u.is_admin && (
                      <span className="font-mono text-[8px] uppercase tracking-[0.15em] px-1.5 py-0.5 bg-violet-100 text-violet-800">
                        Admin
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{u.name || "—"}</td>
                  <td className="px-3 py-3 text-center">
                    {u.disabled ? (
                      <span className="font-mono text-[9px] uppercase tracking-wider px-2 py-1 border border-red-300 bg-red-50 text-red-800">Désactivé</span>
                    ) : u.email_verified ? (
                      <span className="font-mono text-[9px] uppercase tracking-wider px-2 py-1 border border-emerald-300 bg-emerald-50 text-emerald-800">Vérifié</span>
                    ) : (
                      <span className="font-mono text-[9px] uppercase tracking-wider px-2 py-1 border border-amber-300 bg-amber-50 text-amber-800">En attente</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right font-mono tabular-nums text-slate-600">{u.favorites_count}</td>
                  <td className="px-4 py-3 text-[11px] text-slate-500 font-mono">{fmtLocal(u.created_at, { day: "2-digit", month: "short", year: "2-digit", hour: "2-digit", minute: "2-digit" })}</td>
                  <td className="px-6 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {!u.email_verified && (
                        <button
                          onClick={() => handleVerify(u)}
                          className="p-1.5 text-emerald-700 hover:bg-emerald-100 transition-colors"
                          title="Forcer la vérification"
                          data-testid={`admin-verify-${u.id}`}
                        >
                          <MailCheck className="w-4 h-4" />
                        </button>
                      )}
                      {!u.is_admin && (
                        <>
                          <button
                            onClick={() => handleDisable(u)}
                            className={`p-1.5 transition-colors ${u.disabled ? "text-emerald-700 hover:bg-emerald-100" : "text-amber-700 hover:bg-amber-100"}`}
                            title={u.disabled ? "Réactiver" : "Désactiver"}
                            data-testid={`admin-toggle-${u.id}`}
                          >
                            {u.disabled ? <CheckCircle className="w-4 h-4" /> : <ShieldOff className="w-4 h-4" />}
                          </button>
                          <button
                            onClick={() => handleDelete(u)}
                            className="p-1.5 text-red-700 hover:bg-red-100 transition-colors"
                            title="Supprimer"
                            data-testid={`admin-delete-${u.id}`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      {u.is_admin && <UserX className="w-4 h-4 text-slate-300" title="Compte admin protégé" />}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <footer className="pt-8 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
          Admin · {user.email}
        </footer>
      </main>
    </div>
  );
}
