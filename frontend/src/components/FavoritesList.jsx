import { useEffect, useState } from "react";
import { MapPin, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { createFavorite, deleteFavorite, listFavorites, LOURDES } from "@/lib/api";
import { toast } from "sonner";

export default function FavoritesList({ onSelect, activeCenter }) {
  const { user } = useAuth();
  const [favs, setFavs] = useState([]);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (!user) return null;

  const addCurrent = async () => {
    if (!name.trim()) {
      toast.error("Donnez un nom au lieu");
      return;
    }
    try {
      const fav = await createFavorite({
        name: name.trim(),
        lat: activeCenter?.lat ?? LOURDES.lat,
        lon: activeCenter?.lon ?? LOURDES.lon,
      });
      setFavs((f) => [...f, fav]);
      setName("");
      setAdding(false);
      toast.success("Lieu sauvegardé");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur");
    }
  };

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
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {adding && (
        <div className="p-5 border-b border-slate-100 bg-slate-50/50" data-testid="add-favorite-form">
          <label className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 block mb-1.5">
            Nom du lieu
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ex: Pic du Jer"
            className="rounded-none border-slate-300 h-9 mb-3"
            data-testid="favorite-name-input"
          />
          <div className="font-mono text-[10px] text-slate-500 mb-3">
            Coordonnées: {(activeCenter?.lat ?? LOURDES.lat).toFixed(4)},{" "}
            {(activeCenter?.lon ?? LOURDES.lon).toFixed(4)}
          </div>
          <Button
            onClick={addCurrent}
            className="w-full rounded-none h-9 bg-slate-900 hover:bg-slate-800 font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="save-favorite-button"
          >
            Sauvegarder
          </Button>
        </div>
      )}

      <ul className="divide-y divide-slate-100">
        {favs.length === 0 && !adding && (
          <li className="p-5 text-xs text-slate-400 font-mono">Aucun lieu enregistré</li>
        )}
        {favs.map((f) => (
          <li key={f.id} className="flex items-center justify-between px-5 py-3 hover:bg-slate-50 group">
            <button
              onClick={() => onSelect?.({ lat: f.lat, lon: f.lon, name: f.name })}
              className="flex items-center gap-3 min-w-0 text-left"
              data-testid={`favorite-item-${f.id}`}
            >
              <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
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
        ))}
      </ul>
    </div>
  );
}
