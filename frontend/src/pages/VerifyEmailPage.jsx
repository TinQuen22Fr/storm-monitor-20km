import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { authVerifyEmail } from "@/lib/api";

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState("loading"); // loading | success | error
  const [user, setUser] = useState(null);
  const [errMsg, setErrMsg] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrMsg("Aucun jeton de vérification fourni dans l'URL.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await authVerifyEmail(token);
        if (cancelled) return;
        if (data.token) {
          localStorage.setItem("storm_token", data.token);
          setUser(data.user);
        }
        setStatus("success");
      } catch (err) {
        if (cancelled) return;
        setErrMsg(err?.response?.data?.detail || "Lien invalide ou expiré.");
        setStatus("error");
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  return (
    <div className="min-h-screen w-full bg-slate-50 flex items-center justify-center px-6" data-testid="verify-email-page">
      <div className="max-w-md w-full border border-slate-200 bg-white p-10">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-slate-400 mb-3">
          Storm Monitoring
        </div>

        {status === "loading" && (
          <>
            <Loader2 className="w-10 h-10 text-slate-400 mb-4 animate-spin" strokeWidth={1.5} />
            <h1 className="font-heading text-2xl font-black text-slate-900 mb-2">
              Vérification en cours…
            </h1>
            <p className="text-sm text-slate-500">Patiente une seconde.</p>
          </>
        )}

        {status === "success" && (
          <>
            <CheckCircle2 className="w-10 h-10 text-emerald-600 mb-4" strokeWidth={2} />
            <h1 className="font-heading text-3xl font-black text-slate-900 mb-2 tracking-tighter" data-testid="verify-success-title">
              Compte activé !
            </h1>
            <p className="text-sm text-slate-600 leading-relaxed mb-6">
              {user
                ? `Bienvenue ${user.name}. Tu es connecté et peux maintenant utiliser Storm Monitoring.`
                : "Ton compte est activé. Tu peux te connecter."}
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-5 h-11 bg-slate-900 text-white hover:bg-slate-800 font-mono text-[10px] uppercase tracking-[0.2em]"
              data-testid="verify-success-cta"
            >
              Accéder à l&apos;application
              <ArrowRight className="w-4 h-4" />
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <XCircle className="w-10 h-10 text-red-600 mb-4" strokeWidth={2} />
            <h1 className="font-heading text-3xl font-black text-slate-900 mb-2 tracking-tighter" data-testid="verify-error-title">
              Lien invalide.
            </h1>
            <p className="text-sm text-slate-600 leading-relaxed mb-6">
              {errMsg} Si tu pense qu&apos;il s&apos;agit d&apos;une erreur, redemande un mail de vérification depuis l&apos;écran de connexion.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-5 h-11 border border-slate-300 hover:bg-slate-900 hover:text-white font-mono text-[10px] uppercase tracking-[0.2em] transition-colors"
              data-testid="verify-error-cta"
            >
              Retour à l&apos;accueil
            </Link>
          </>
        )}

        <div className="mt-10 pt-6 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 text-center">
          Build &amp; Idea by Quentin Dumont
        </div>
      </div>
    </div>
  );
}
