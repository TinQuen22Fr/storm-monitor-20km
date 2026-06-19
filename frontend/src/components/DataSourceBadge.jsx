import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ShieldCheck } from "lucide-react";

/**
 * Discrete credibility badge — displayed next to the page title.
 * Opens a popover explaining the scientific basis (Blitzortung TOA network).
 * Designed to silence sceptics who claim the app is "not official".
 */
export default function DataSourceBadge({ compact = false }) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
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
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={8}
        className="w-[min(92vw,420px)] rounded-none border-slate-900 p-0 bg-white shadow-[0_8px_32px_rgba(0,0,0,0.08)]"
        data-testid="data-source-popover"
      >
        <div className="p-5 border-b border-slate-100">
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-slate-400 mb-1.5">
            Méthodologie
          </div>
          <h3 className="font-heading text-base font-bold text-slate-900">
            Données scientifiques vérifiables
          </h3>
        </div>
        <div className="p-5 space-y-3 text-[13px] text-slate-700 leading-relaxed">
          <p>
            Les impacts foudre affichés sont des <strong>données brutes TOA</strong>{" "}
            (<em>Time Of Arrival</em>) issues du réseau{" "}
            <a
              href="https://www.blitzortung.org/fr/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-900 underline underline-offset-2 hover:text-violet-700"
            >
              Blitzortung
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
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex items-center gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-700 shrink-0" strokeWidth={2.2} />
          <p className="text-[11px] font-mono text-slate-600 leading-snug">
            Méthodologie publique · Sources libres · Non commercial
          </p>
        </div>
        <div className="px-5 py-3 border-t border-slate-100 grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="font-heading text-sm font-bold text-slate-900 tabular-nums">500+</div>
            <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400">Stations</div>
          </div>
          <div>
            <div className="font-heading text-sm font-bold text-slate-900">TOA</div>
            <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400">Triangulation</div>
          </div>
          <div>
            <div className="font-heading text-sm font-bold text-slate-900">~1 km</div>
            <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400">Précision</div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
