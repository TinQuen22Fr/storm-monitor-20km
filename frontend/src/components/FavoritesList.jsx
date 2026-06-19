import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { createFavorite, deleteFavorite, geocodeSearch, listFavorites } from "@/lib/api";
import { toast } from "sonner";

function AddFavoriteForm({ onCreated, onClose }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);
  const [customName, setCustomName] = useState("");
  const debounceRef = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query || query.length < 2 || selected) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await geocodeSearch(query);
        setResults(r);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 350);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [query, selected]);

  const pick = (r) => {
    setSelected(r);
    setCustomName(r.name + (r.admin1 ? ` (${r.admin1})` : ""));
    setResults([]);
  };

  const save = async () => {
    if (!selected) {
      toast.error("Choisis un lieu dans la liste de suggestions");
      return;
    }
    if (!customName.trim()) {
      toast.error("Donne un nom au lieu");
      return;
    }
    try {
      const fav = await createFavorite({
        name: customName.trim(),
        lat: selected.latitude,
        lon: selected.longitude,
      });
      onCreated?.(fav);
      toast.success(`${customName.trim()} ajouté`);
      onClose?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur");
    }
  };

  return (
    <div className="p-5 border-b border-slate-100 bg-slate-50/50" data-testid="add-favorite-form">
      <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 block mb-1.5">
        Rechercher un lieu
      </label>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
        <Input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (selected) setSelected(null);
          }}
          placeholder="ex: Saint-Brieuc, France"
          className="rounded-none border-slate-300 h-9 pl-9"
          data-testid="favorite-search-input"
          autoFocus
        />
      </div>

      {searching && (
        <div className="mt-2 flex items-center gap-2 text-[11px] font-mono text-slate-500" data-testid="favorite-searching">
          <Loader2 className="w-3 h-3 animate-spin" /> recherche…
        </div>
      )}

      {!selected && results.length > 0 && (
        <ul className="mt-2 border border-slate-200 bg-white max-h-56 overflow-y-auto divide-y divide-slate-100" data-testid="geocode-results">
          {results.map((r) => (
            <li key={`${r.id}-${r.latitude}-${r.longitude}`}>
              <button
                onClick={() => pick(r)}
                className="w-full text-left px-3 py-2 hover:bg-slate-100 transition-colors"
                data-testid={`geocode-result-${r.id}`}
              >
                <div className="text-sm font-medium text-slate-900">
                  {r.name}
                  {r.admin1 && <span className="text-slate-400 font-normal"> · {r.admin1}</span>}
                </div>
                <div className="font-mono text-[10px] text-slate-400">
                  {(r.country || "")}{" "}
                  · {Number(r.latitude).toFixed(3)}, {Number(r.longitude).toFixed(3)}
                  {r.elevation != null && <> · {Math.round(r.elevation)} m</>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {!selected && !searching && query.length >= 2 && results.length === 0 && (
        <div className="mt-2 text-[11px] font-mono text-slate-400">Aucun lieu trouvé.</div>
      )}

      {selected && (
        <div className="mt-3 p-3 border border-emerald-200 bg-emerald-50" data-testid="favorite-selected">
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-emerald-800 mb-1">
            Lieu sélectionné
          </div>
          <div className="font-mono text-[11px] text-slate-700">
            {Number(selected.latitude).toFixed(4)}, {Number(selected.longitude).toFixed(4)}
          </div>
        </div>
      )}

      {selected && (
        <>
          <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 block mb-1.5 mt-4">
            Nom à afficher
          </label>
          <Input
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="ex: Maison"
            className="rounded-none border-slate-300 h-9 mb-3"
            data-testid="favorite-name-input"
          />
          <Button
            onClick={save}
            className="w-full rounded-none h-9 bg-slate-900 hover:bg-slate-800 font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="save-favorite-button"
          >
            Sauvegarder ce lieu
          </Button>
        </>
      )}
    </div>
  );
}

export default function FavoritesList({ onSelect, activeCenter }) {
  const { user } = useAuth();
  const [favs, setFavs] = useState([]);
  const [adding, setAdding] = useState(false);

  const load = async () => {
    if (!user) return;
    try {
      const d = await listFavorites();
      setFavs(d);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    load();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user) return null;

  const remove = async (id) => {
    try {
      await deleteFavorite(id);
      setFavs((f) => f.filter((x) => x.id !== id));
      toast.success("Lieu retiré");
    } catch {
      toast.error("Erreur");
    }
  };

  return (
    <div className="border border-slate-200 bg-white" data-testid="favorites-list">
      <div className="flex items-center justify-between p-5 border-b border-slate-100">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">Favoris</div>
          <div className="font-heading text-sm font-bold text-slate-900">Mes lieux</div>
        </div>
        <button
          onClick={() => setAdding((v) => !v)}
          className="w-7 h-7 border border-slate-300 flex items-center justify-center hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors"
          data-testid="toggle-add-favorite"
          aria-label="Ajouter"
        >
          <Plus className={`w-3.5 h-3.5 transition-transform ${adding ? "rotate-45" : ""}`} />
        </button>
      </div>

      {adding && (
        <AddFavoriteForm
          onCreated={(fav) => setFavs((f) => [...f, fav])}
          onClose={() => setAdding(false)}
        />
      )}

      <ul className="divide-y divide-slate-100">
        {favs.length === 0 && !adding && (
          <li className="p-5 text-xs text-slate-400 font-mono">Aucun lieu enregistré</li>
        )}
        {favs.map((f) => {
          const isActive =
            activeCenter && Math.abs(activeCenter.lat - f.lat) < 0.001 && Math.abs(activeCenter.lon - f.lon) < 0.001;
          return (
            <li key={f.id} className={`flex items-center justify-between px-5 py-3 group ${isActive ? "bg-slate-50" : "hover:bg-slate-50"}`}>
              <button
                onClick={() => onSelect?.({ lat: f.lat, lon: f.lon, name: f.name })}
                className="flex items-center gap-3 min-w-0 text-left flex-1"
                data-testid={`favorite-item-${f.id}`}
              >
                <MapPin className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-slate-900" : "text-slate-400"}`} />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-900 truncate">{f.name}</div>
                  <div className="font-mono text-[10px] text-slate-400">
                    {f.lat.toFixed(3)}, {f.lon.toFixed(3)}
                  </div>
                </div>
              </button>
              <button
                onClick={() => remove(f.id)}
                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 transition-all"
                data-testid={`delete-favorite-${f.id}`}
                aria-label="Supprimer"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
