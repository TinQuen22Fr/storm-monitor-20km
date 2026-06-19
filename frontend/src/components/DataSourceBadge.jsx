import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ExternalLink, ShieldCheck } from "lucide-react";

/**
 * Discrete credibility badge — displayed in the sidebar.
 * Opens a centered scrollable dialog explaining the scientific basis
 * (Blitzortung TOA network). Designed to silence sceptics who claim
 * the app is "not official".
 */
export default function DataSourceBadge({ compact = false }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1.5 border border-slate-300 bg-white hover:border-slate-900 hover:bg-slate-900 hover:text-white transition-colors font-mono uppercase tracking-[0.15em] ${
            compact ? "px-2 h-6 text-[9px]" : "px-3 h-7 text-[10px]"
          }`}
          data-testid="data-source-badge"
          aria-label="Sources de données"
        >
          <ShieldCheck className={compact ? "w-3 h-3" : "w-3.5 h-3.5"} strokeWidth={2.2} />
          <span>Données vérifiées</span>
        </button>
      </DialogTrigger>
      <DialogContent
        className="rounded-none border-slate-900 max-w-xl w-[min(92vw,640px)] p-0 max-h-[85vh] overflow-y-auto"
        data-testid="data-source-popover"
      >
        <DialogHeader className="p-6 lg:p-8 border-b border-slate-100">
          <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-slate-400 mb-2">
            Méthodologie · Transparence
          </div>
          <DialogTitle className="font-heading text-2xl lg:text-3xl font-black tracking-tight text-slate-900">
            Données scientifiques vérifiables.
          </DialogTitle>
          <DialogDescription className="text-slate-500 mt-2">
            Pourquoi vous pouvez faire confiance aux informations affichées par Storm Monitoring.
          </DialogDescription>
        </DialogHeader>

        <div className="p-6 lg:p-8 space-y-4 text-sm text-slate-700 leading-relaxed">
          <p>
            Les impacts foudre affichés sont des <strong>données brutes TOA</strong>{" "}
            (<em>Time Of Arrival</em>) issues du réseau{" "}
            <a
              href="https://www.blitzortung.org/fr/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-slate-900 underline underline-offset-2 hover:text-violet-700"
            >
              Blitzortung
              <ExternalLink className="w-3 h-3" />
            </a>
            {" "}— une coopérative scientifique européenne qui agrège en temps réel
            les signaux de plus de <strong>500 stations bénévoles</strong> dans le monde.
          </p>
          <p>
            La méthode <strong>TOA</strong> est la même technique de triangulation
            par temps d&apos;arrivée que celle utilisée par les observatoires
            météorologiques de référence et les opérateurs commerciaux du secteur.
            Précision géographique typique de l&apos;ordre du{" "}
            <strong>kilomètre</strong>, latence inférieure à 30 secondes.
          </p>
          <p>
            Les données présentées ici sont <strong>non agrégées, non filtrées
            commercialement, et libres</strong>. Cet outil sert à la diffusion publique
            et coopérative de ces informations scientifiques pour la sécurité des
            personnes et la prévention des risques liés à la foudre.
          </p>
        </div>

        <div className="px-6 lg:px-8 py-3 bg-slate-50 border-t border-slate-100 flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-700 shrink-0" strokeWidth={2.2} />
          <p className="text-[11px] font-mono text-slate-600 leading-snug">
            Méthodologie publique · Sources libres · Non commercial
          </p>
        </div>

        <div className="px-6 lg:px-8 py-5 border-t border-slate-100 grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="font-heading text-2xl font-black text-slate-900 tabular-nums leading-none">
              500+
            </div>
            <div className="mt-1 text-[9px] font-mono uppercase tracking-wider text-slate-400">
              Stations
            </div>
          </div>
          <div>
            <div className="font-heading text-2xl font-black text-slate-900 leading-none">TOA</div>
            <div className="mt-1 text-[9px] font-mono uppercase tracking-wider text-slate-400">
              Triangulation
            </div>
          </div>
          <div>
            <div className="font-heading text-2xl font-black text-slate-900 tabular-nums leading-none">
              ~1 km
            </div>
            <div className="mt-1 text-[9px] font-mono uppercase tracking-wider text-slate-400">
              Précision
            </div>
          </div>
        </div>

        <div className="px-6 lg:px-8 py-3 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 text-center">
          Storm Monitoring · Build &amp; Idea by Quentin Dumont
        </div>
      </DialogContent>
    </Dialog>
  );
}
