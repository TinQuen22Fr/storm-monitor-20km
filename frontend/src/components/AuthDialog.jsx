import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { User, LogOut } from "lucide-react";

export default function AuthDialog() {
  const { user, login, register, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        toast.success("Connexion réussie");
      } else {
        await register(email, password, name);
        toast.success("Compte créé avec succès");
      }
      setOpen(false);
      setEmail("");
      setPassword("");
      setName("");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur d'authentification");
    } finally {
      setLoading(false);
    }
  };

  if (user) {
    return (
      <div className="flex items-center justify-between border border-slate-200 p-4 bg-white" data-testid="user-badge">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 bg-slate-900 text-white flex items-center justify-center font-mono text-sm shrink-0">
            {(user.name || user.email).slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="font-heading text-sm font-semibold text-slate-900 truncate">{user.name}</div>
            <div className="font-mono text-[10px] text-slate-400 truncate">{user.email}</div>
          </div>
        </div>
        <button
          onClick={logout}
          className="text-slate-400 hover:text-red-600 transition-colors p-1.5"
          data-testid="logout-button"
          aria-label="Déconnexion"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          className="w-full rounded-none border-slate-900 hover:bg-slate-900 hover:text-white font-mono text-xs uppercase tracking-[0.2em] h-11"
          data-testid="open-auth-dialog"
        >
          <User className="w-4 h-4 mr-2" />
          Se connecter
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-none border-slate-900 max-w-md p-0" data-testid="auth-dialog">
        <div className="p-8">
          <DialogHeader>
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-slate-400 mb-2">
              {mode === "login" ? "Authentification" : "Nouveau compte"}
            </div>
            <DialogTitle className="font-heading text-3xl font-black tracking-tight text-slate-900">
              {mode === "login" ? "Bon retour." : "Rejoindre."}
            </DialogTitle>
            <DialogDescription className="text-slate-500 mt-2">
              {mode === "login"
                ? "Accédez à vos lieux favoris sauvegardés."
                : "Créez un compte pour sauvegarder vos lieux favoris."}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={submit} className="mt-6 space-y-4" data-testid="auth-form">
            {mode === "register" && (
              <div>
                <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 block mb-1.5">
                  Nom
                </label>
                <Input
                  data-testid="auth-name-input"
                  type="text"
                  placeholder="Votre nom"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="rounded-none border-slate-300 h-11"
                />
              </div>
            )}
            <div>
              <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 block mb-1.5">
                Email
              </label>
              <Input
                data-testid="auth-email-input"
                type="email"
                required
                placeholder="vous@exemple.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-none border-slate-300 h-11 font-mono text-sm"
              />
            </div>
            <div>
              <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 block mb-1.5">
                Mot de passe
              </label>
              <Input
                data-testid="auth-password-input"
                type="password"
                required
                minLength={6}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-none border-slate-300 h-11 font-mono"
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full rounded-none h-11 bg-slate-900 hover:bg-slate-800 font-mono text-xs uppercase tracking-[0.2em]"
              data-testid="auth-submit-button"
            >
              {loading ? "…" : mode === "login" ? "Se connecter" : "Créer le compte"}
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-200 text-center">
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-500 hover:text-slate-900"
              data-testid="auth-toggle-mode"
            >
              {mode === "login" ? "Pas de compte ? Créer un compte →" : "← Déjà inscrit ? Se connecter"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
