# PRD — Suivi d'orage en temps réel (Lourdes)

## Problème original
Application de suivi d'orage en direct dans un rayon de 20 km autour de Lourdes, avec :
- Carte interactive (impacts foudre Blitzortung + météo Open-Meteo)
- Notifications push (VAPID)
- Historique multi-jours + prévisions risque orage 7 jours
- Export PDF "bulletin orage" en heure locale
- Curseur rayon ajustable (20–70 km)
- Route API `/api/upload_storm` sécurisée + page historique avec graphiques
- Branche `Version_With_Detector` pour intégration matériel AS3935
- Auth + validation email (Resend) + Dashboard Admin

## Architecture
```
/app
├── backend/  (FastAPI : server.py, severe.py, weather.py, reports.py, lightning.py)
├── frontend/ (React CRA : Dashboard, GrelePage, PrevisionsPage, AdminPage…)
├── install.sh + upgrade.sh + DEPLOY.md
```

## Stack
React CRA, FastAPI, MongoDB, Leaflet, Leaflet WMS (EUMETSAT Meteosat MSG), Canvas IDW, Open-Meteo, Blitzortung, MeteoAlarm, Resend.

## ✅ Implémenté
- Multi-zones (combine plusieurs régions, focus auto sur changement)
- PDF multi-zones via `/api/reports/bulletin?z=...`
- Pages avancées `/grele` et `/previsions` (48h variables Jet/Shear/VV/T° 850hPa)
- FranceMapPanel (Canvas IDW Windy-style) + VerticalProfileChart
- Synergie hail = Blitzortung surges + Open-Meteo wind shear
- Couche nuages EUMETSAT Meteosat MSG géostationnaire (15 min)
- Scripts `install.sh` (full reset) + `upgrade.sh` (git pull + rsync rapide)
- **[2026-02-28] Phase 36 — 4 patches chirurgicaux GEMINI verrouillés dans le repo (branche Version_With_Detector)** :
  1. `server.py:_degraded('severe-grid')` retourne maintenant la forme exacte du bulk endpoint (`lats/lons/times/per_param/units/grid_cols/grid_rows`) → plus de "Snapshot bulk invalide" même si Open-Meteo plante.
  2. `severe.py:GRID_COLS=10`, `GRID_ROWS=8` → grille 80 points (vs 192 avant), payload Open-Meteo 60% plus léger.
  3. `severe.py:BULK_TTL_S = 7200.0` (2h vs 10min) → ≤12 hits Open-Meteo/jour par IP VPS, hors quota.
  4. `install.sh` : `systemctl daemon-reload && systemctl enable && systemctl restart storm-monitor.service` (l'ancien `enable --now` ne redémarrait PAS si déjà actif → uvicorn restait sur l'ancien code en RAM, c'est pour ça que les fixes précédents ne prenaient pas effet sur le Kimsufi).
  4bis. `install.sh` + `upgrade.sh` créent `backend/cache/` chown RUN_USER + chmod 755 → www-data peut écrire `grid_bulk.json`.
  - **Validé testing agent (iteration_31.json) — 100% backend (16/16 pytest)** + live evidence des 7 clés présentes dans `_degraded`, `france_grid_len=80`, `BULK_TTL_S=7200.0`, `bash -n` OK sur les deux scripts.

- **[2026-02-28] Phase 35bis — Frontend bulk fetch + écriture disque non-bloquante (fix 504 Kimsufi)** :
  - **Bug** : iteration_28 avait mis en place le bulk côté backend, mais `FranceMapPanel.jsx` continuait à appeler `getSevereGrid(param, hour)` dans un `useEffect([param, hour])`. À chaque mouvement du slider sur l'Intel Atom Kimsufi → cascade de micro-requêtes (?hour=5, hour=6...) → backend saturé pendant le premier bulk fetch → 504 Gateway Timeout nginx.
  - **Fix frontend** (`FranceMapPanel.jsx`) : remplacement du `useEffect([param, hour])` par (a) `useEffect([])` qui fetche `/api/weather/severe/grid/bulk` UNE SEULE FOIS au mount, (b) `useMemo([bulk, param, hour, ...])` qui slice le snapshot in-memory côté JS. Plus aucun appel API au mouvement du slider ou changement de param.
  - **Fix backend** (`severe.py`) : `_save_bulk_to_disk_async` wrappe l'écriture sync dans `asyncio.to_thread`, `_get_or_refresh_bulk` lance la persistance en `asyncio.create_task` (fire-and-forget) — la requête HTTP ne bloque jamais sur l'I/O disque (critique sur Atom). `_save_bulk_to_disk` catch explicitement `PermissionError` et `OSError` avec log warning, jamais raise — fallback gracieux en in-memory only si www-data n'a pas les droits sur `cache/`.
  - **Nouveau endpoint** : `GET /api/weather/severe/grid/bulk` retourne le snapshot complet (192 locs × 48h × 9 params, ~450 KB).
  - **Validé testing agent (iteration_29.json) — 100%** : mount = 1 seul appel bulk (legacy `grid?param=X&hour=Y` à 0), slider 8 positions = 0 nouveau appel, switch 5 params = 0 nouveau appel.

- **[2026-02-28] Phase 35 — Bulk Fetch & Local Storage (architecture stricte demandée par user)** :
  - **Cause racine définitivement réglée** : avant chaque mouvement de slider/param pouvait déclencher un appel Open-Meteo → rate-limit 429 récurrent. Maintenant : **1 seul appel** ramène TOUS les params × TOUTES les heures × TOUS les 192 points d'un coup (~448 KB JSON), persisté sur disque dans `/app/backend/cache/grid_bulk.json`. Les requêtes (param, hour) sont des pures slices in-memory.
  - **Nouveau dans `severe.py`** : `_fetch_bulk_impl`, `_get_or_refresh_bulk` (lock + double-check + fallback disque + stale fallback), `_compute_param_values`, `_slice_bulk`, `get_bulk_status`. Écriture atomique tempfile+rename. TTL 600s.
  - **Nouveau endpoint diagnostic** : `GET /api/weather/severe/grid/status` (âge, fraîcheur, in_memory/on_disk, n_hours, run_iso).
  - **Frontend NON modifié.**
  - **Validé testing agent (iteration_28.json)** : 100% backend + frontend.
    - Cold start : 1 appel upstream, 12 vars hourly
    - Burst 50 requêtes variées : **0 appel upstream**, avg 107.6ms / max 187.5ms
    - Restart backend avec cache disque : 0 upstream, 112ms
    - Frontend stress : 0 badge ambre, 0 ErrorBoundary, 0 console error

- **[2026-02-28] Fix racine rate-limit Open-Meteo (carte Prévisions vide passée H+4)** :
  - **Cause racine** : cache indexé par `(param, hour_offset)` → 9 × 48 = 432 clés distinctes. Chaque mouvement du slider = nouvel appel multi-location → Open-Meteo 429 → `_degraded` → carte vide. L'iteration_26 ne faisait que masquer le crash, pas régler la cause.
  - **Fix backend** (`severe.py`) : `fetch_severe_grid` refactoré — 1 seul appel par `param` qui ramène les 48 heures d'un coup, cache TTL 600s par `param` uniquement. Le `hour_offset` devient une simple indexation post-cache → après le premier appel, le user peut scrubber le slider H+0→H+47 sans aucun appel API supplémentaire. Idem `fetch_temp_profile` cache par `(lat,lon)`.
  - **Fix backend** (`weather.py`) : `get_with_retry` durci — retries 2→4, backoff exponentiel 1/2/4/8 s (worst case ~15s). Absorbe les 429 transients.
  - **Frontend NON modifié** (consigne stricte de l'user).
  - **Validé testing agent** (iteration_27.json) — 27/27 pytest backend + 100% frontend stress test. Vraies données 192 points pour les 9 params, valeurs physiques cohérentes, profil vertical -37°C à 300hPa. Plus de badge ambre.

- **[2026-02-28] Fix crash FranceMapPanel `lats is undefined` (preview overlay rouge + Kimsufi page blanche)** :
  - Backend `server.py:_degraded` étendu pour les cas `severe`, `severe-grid`, `severe-profile` → renvoie maintenant des arrays vides au lieu d'un payload sans clés.
  - Frontend `FranceMapPanel.jsx` : `valueAt` + rendu `IdwOverlay` + `.map(favorites)` guardés avec `Array.isArray(grid.lats) && grid.lats.length > 0`. Badge ambre `Données indisponibles pour ce paramètre/échéance` non-bloquant en cas de payload dégradé.
  - Nouveau `components/ErrorBoundary.jsx` wrappant `FranceMapPanel` et `VerticalProfileChart` dans `PrevisionsPage.jsx` → plus jamais de white screen en prod, fallback card avec bouton "Réessayer".
  - Validé par testing agent (iteration_26.json) — 100% backend + frontend, 2 régressions guard (arrays vides + clés manquantes) PASS.

- **[2026-02-28] Purge branche `Testing` + retrait `sudo`** : `install.sh` et `upgrade.sh` ont maintenant `BRANCH="Version_With_Detector"` **hardcodé** (plus de fallback `${BRANCH:-...}`, plus possible de redéployer sur `Testing` par accident). Tous les `sudo ` ont été retirés des scripts et de `DEPLOY.md` (Kimsufi/OVH est déjà root par défaut). Validé par testing agent (iteration_25.json) — 13/13 critères PASS, `bash -n` OK, git status scope-limited aux 3 fichiers.

- **[2026-02-28] Fix UX message d'erreur Prévisions** : amélioration de `PrevisionsPage.jsx`, `FranceMapPanel.jsx` et `VerticalProfileChart.jsx` pour distinguer un 404 (endpoint absent côté backend) d'une autre erreur. En cas de 404 sur `/api/weather/severe`, affichage de la procédure shell de remediation directement à l'écran. Validé par testing agent (iteration_24.json, 100%) — preview nominal OK + 404 simulé affiche le bon message.
  - **Diagnostic VPS Kimsufi** : le backend tournait sur la branche github `Testing` au lieu de `Version_With_Detector` → routes severe/grid/profile, reports/bulletin, share/snapshot etc absentes. **Fix utilisateur** : `sudo BRANCH=Version_With_Detector bash /opt/storm-monitor/upgrade.sh`.

- **[2026-02-27] Rollback calque nuages → NASA MODIS Terra** : Après plusieurs essais de filtres CSS sur Meteosat MSG (`blur` 3/5/18/30 px ± contrast), abandon du calque géostationnaire à cause de sa résolution native trop faible (~3 km/px) qui crée une grille de gros blocs inexploitables à l'échelle 20 km. Restauration du calque NASA GIBS MODIS Terra (polar orbit, ~250 m/px) : haute résolution spatiale, contours nuageux organiques, pas de pixelation. App.css entièrement nettoyé de tous les filtres `.meteosat-smooth-tile`. Cadence : ~1 pass/jour, timeline 5 jours navigables.

- **[2026-06] Application Android (Capacitor + GitHub Actions)** : Frontend React embarqué dans un APK natif via Capacitor 7 (`fr.quentinastro.stormmonitor`, nom "Storm Monitor"). Projet `frontend/android/` committé, icône éclair/orage générée à toutes les densités (launcher + round + adaptive foreground + splash screens fond navy #1A1A2E). Workflow `.github/workflows/android-build.yml` : build React avec `REACT_APP_BACKEND_URL=https://storm-monitor.quentin-astro.fr` → `cap sync` → Gradle (Java 21, ubuntu-latest) → artifacts `storm-monitor-debug` (toujours) + `storm-monitor-release` signé (si secrets `KEYSTORE_BASE64/KEYSTORE_PASSWORD/KEY_ALIAS/KEY_PASSWORD` configurés). Doc complète dans `/app/ANDROID.md`. Vérifié en sandbox : build CRA prod + cap sync OK, URL Kimsufi bien embarquée dans le bundle, YAML valide. Compilation APK finale à valider sur GitHub Actions (pas de SDK Android en sandbox). L'utilisateur pourra fournir sa propre image d'icône plus tard.

## 🟡 Backlog
- **P1** — Valider le 1er run GitHub Actions Android + installer l'APK sur téléphone
- **P2** — Remplacer l'icône générée par l'image personnelle de l'utilisateur (quand fournie)
- **P2** — Migration React CRA → Vite (élimine warnings `react-scripts`, ~2-4h)
- **P2** — Réseau collaboratif : permettre aux users de contribuer des données au réseau d'orage
- **P3** — Refactor optionnel : casser `server.py` en `/app/backend/routes/` modulaires
- **P3** — Envisager produit Meteosat HRV/RSS plus haute résolution (suggéré par testing agent) pour éviter le blur hack à long terme

## Credentials test
- Admin : `quentin.dumont.22@gmail.com` (voir `test_credentials.md`)

## API endpoints clés
- `GET /api/weather/severe` — calcul hail base
- `GET /api/weather/severe/grid` — grille multi-points (FranceMapPanel)
- `GET /api/weather/severe/profile` — profil vertical T°
- `GET /api/reports/bulletin?z=...` — PDF multi-zones
- `POST /api/upload_storm` — ingestion data détecteur AS3935

## Notes déploiement
La prochaine MAJ sur Kimsufi doit utiliser `install.sh` une fois pour initialiser, puis `upgrade.sh` pour les MAJ suivantes.
