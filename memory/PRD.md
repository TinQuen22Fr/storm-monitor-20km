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

- **[2026-06] Bouton Quitter natif + Release GitHub** : Fix workflow (yarn.lock + gradle-wrapper.jar jamais commités → cache CI plantait, corrigé + cache retiré). APK publié automatiquement en Release GitHub tag `android-latest` (téléchargeable depuis mobile, contrairement aux artifacts). Nouveau composant `NativeAppExit.jsx` : bouton flottant « Quitter » (Power → confirmation rouge 3.5s → exitApp) visible UNIQUEMENT dans l'APK (`Capacitor.isNativePlatform()`), + gestion du bouton/geste retour Android (`@capacitor/app` : historique back sinon exit). Vérifié : invisible sur web, plugin enregistré dans le projet Android.

- **[2026-06] Fix son mode soirée (jamais fonctionné depuis ~1,5 mois)** : Cause racine = `AudioContext` créé au moment de l'impact (hors geste utilisateur) → bloqué en état « suspended » par la politique autoplay des navigateurs/webview Android → silence total. Fix : nouveau `lib/thunderSound.js` avec AudioContext partagé + `unlockAudio()` appelé à l'ouverture du mode soirée et au clic sur l'icône son. Nouveau son de tonnerre réaliste synthétisé (craquement highpass + grondement lowpass ~1,6s) remplaçant le bip 880Hz. Son de confirmation immédiat quand on active l'icône son. Réparé aussi : encodage UTF-8 corrompu de NightStormMode.jsx (octet 0xb7). Vérifié : compile OK, mode soirée s'ouvre, toggle son OK, invisible régression web.

- **[2026-06] Notifications push natives Android (Firebase FCM)** : Nouveau `backend/fcm.py` (init lazy si `backend/firebase-admin.json` présent, sinon no-op silencieux ; envoi via `messaging.send_each_for_multicast` dans `asyncio.to_thread` pour Kimsufi Atom ; purge auto des tokens invalides — testé). `push.py send_to_all` relaie automatiquement toutes les alertes (transitions orage, impacts, test) vers FCM en plus du web push VAPID. Endpoints `POST /api/push/fcm/subscribe|unsubscribe`. Frontend `lib/push.js` : branche native Capacitor (`@capacitor/push-notifications`, canal Android « storm_alerts » importance max + son + vibration) derrière le même toggle « Push serveur (même fermé) ». `google-services.json` committée (config client, requise par le CI) ; clé admin dans `.gitignore` + exclusions rsync ajoutées à `install.sh`/`upgrade.sh` pour la préserver en prod. Testé e2e via curl : subscribe → envoi réel Firebase → purge token invalide OK. Doc Kimsufi dans ANDROID.md.

- **[2026-06] Root cause FCM "ne marche pas chez moi" identifiée** : `backend/firebase-admin.json` est gitignoré ET exclu du rsync d'`upgrade.sh` → il n'arrive JAMAIS sur le Kimsufi automatiquement. Le fichier n'existait qu'en sandbox. Procédure de déploiement manuel unique écrite dans `/app/PROCEDURE_FCM_KIMSUFI.md` (diagnostic `ls`, génération clé console Firebase, scp, chmod 600, upgrade.sh, vérif journalctl, nouvelle APK, test e2e bouton "Envoyer un test"). En attente d'exécution par l'utilisateur sur son serveur.

- **[2026-06] Diagnostic production "Test envoyé (0 appareils)"** : Vérifié en direct sur le Kimsufi via l'API publique → `fcm_available:false` = `firebase-admin.json` toujours absent du serveur (la chaîne téléphone→serveur fonctionne, tokens bien stockés/supprimés en base). Ajouts : endpoint public `GET /api/push/status` (fcm_available + compteurs tokens/subs) et toasts explicites dans `sendTestPush` (FCM désactivé serveur / aucun appareil / x/y délivrés). Action utilisateur restante : déposer la clé Firebase sur le Kimsufi (console Firebase → Comptes de service → scp → chmod 600 → restart).

- **[2026-06] Fix root cause FCM + observabilité Kimsufi** : (1) Découvert que l'unit systemd prod redirige stdout/stderr vers `/var/log/storm-monitor.err.log` → journalctl était inutilisable, toutes les procédures corrigées. (2) Bug réel corrigé dans `fcm.py` : `_init_tried` cachait l'échec définitivement si la clé apparaissait après le boot — init désormais retentée à chaque appel, testé (dépôt du fichier détecté sans restart). (3) `fcm.diagnose()` + `GET /api/push/status` enrichi (path, file_exists, valid_json, project_id, sdk_installed, last_error nommant le problème exact) — testé sur 4 cas d'échec. (4) `upgrade.sh` force pip si `firebase_admin` absent du venv. (5) Toast subscribe natif avertit si FCM désactivé côté serveur. `PROCEDURE_FCM_KIMSUFI.md` réécrite (logs fichiers + diagnostic curl).

- **[2026-06] Fix crash build prod "Can't resolve @capacitor/core"** : la dépendance était bien dans package.json/yarn.lock depuis le début, mais `upgrade.sh` ne lançait `yarn install` que si package.json changeait dans le diff courant → node_modules de prod périmé (deps Capacitor jamais installées). Ajout d'un garde-fou : vérification que chaque dépendance de package.json existe dans node_modules, sinon yarn install forcé (testé : dep manquante → forcé ; env sain → pas de faux positif). Déblocage immédiat côté user : `yarn install --frozen-lockfile && yarn build` manuel.

## 🔴 CONSIGNE UTILISATEUR STRICTE (2026-06) — GEL DE LA PRODUCTION
L'utilisateur a finalisé lui-même la mise en production (install manuelle de firebase-admin dans le venv, build, nettoyage). Le système est 100% opérationnel.
- INTERDICTION de modifier le backend sans demande explicite de l'utilisateur.
- INTERDICTION d'appeler l'API de production (https://storm-monitor.quentin-astro.fr) pour des tests/diagnostics — aucun POST subscribe/test.
- Ne proposer AUCUNE "réparation" non sollicitée. Attendre ses demandes.
- Audit sécurité réalisé : 4 findings P2 documentés (injection Mongo unsubscribe, /push/test non admin, pas de rate-limit subscribe, email admin exposé dans /api/health) — corrections NON appliquées, en attente de décision utilisateur.

- **[2026-07] Ordre de mission utilisateur — unicast + protection venv (SOUMIS EN RELECTURE, non déployé)** : (1) Fix purge FCM : `Requested entity was not found` (UnregisteredError) désormais reconnu → tokens d'anciennes APK purgés au 1er envoi, fin de la pollution des logs. (2) `/push/test` en unicast (`send_to_user`, filtre user_id) — les alertes orage restent broadcast volontairement. (3) `rebindToken()` au login (frontend) pour lier le token de l'appareil au compte. (4) `upgrade.sh` : venv PROTÉGÉ (pip uniquement via flag explicite `--with-deps`, sinon message informatif), anti-OOM `NODE_OPTIONS=--max-old-space-size=1024` sur yarn build. Testé sandbox : unicast prouvé (total=1 sur 2 tokens), purge prouvée, syntax bash OK, frontend compile. RÈGLE : l'utilisateur relit, valide et déploie lui-même (aucun push auto).

- **[2026-07] Fix bug critique : mutation des points d'analyse au changement de rayon (SOUMIS EN RELECTURE)** : cause racine dans `weather.py` — `sampling_grid` avait un pas dépendant du rayon (`step=max(4, r/4)`) → grille recalculée à des positions différentes à chaque rayon + cache indexé par rayon. Correctif : grille maîtresse ABSOLUE (maillage fixe 14 km, couverture 70 km, cache unique `zones-master`), sévérité calculée une fois par point, le rayon = pur filtre spatial (haversine). Agrégats (storm_active, max_cape) calculés sur le sous-ensemble filtré → alertes push inchangées sémantiquement. Prouvé sandbox : 9/13/37/71 points à 20/30/50/70 km, sous-ensembles stricts, sévérités identiques. Bonus : moins d'appels Open-Meteo (1 fetch partagé entre tous les rayons). FCM non touché (vérifié). Backend uniquement, API contract identique.

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
