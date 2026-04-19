# PRD - Suivi d'Orage Lourdes

## Original Problem Statement
> "J'aurais besoin d'une application de suivi d'orage en direct dans un rayon de vingt kilomètres autour de Lourdes."

## User Choices
- API météo: Open-Meteo (gratuite, sans clé)
- Fonctionnalités: carte interactive avec impacts foudre, alertes, historique 24h, prévisions
- Auth: optionnelle (JWT) pour favoris
- Design: thème clair épuré

## Architecture
- **Backend**: FastAPI + MongoDB + httpx (Open-Meteo client) + JWT/bcrypt
- **Frontend**: React + Tailwind + Leaflet + Recharts + Shadcn UI
- **Design**: Swiss/Editorial light theme (Cabinet Grotesk + Outfit + IBM Plex Mono)

## User Personas
- Habitants/visiteurs de Lourdes
- Randonneurs/touristes des Pyrénées
- Professionnels (organisateurs, secours, agriculture)

## Core Requirements (Static)
- Centre carte: Lourdes (43.0951, -0.0434), rayon 20 km
- Détection orage temps réel + alertes visuelles
- Historique 24h des orages
- Prévisions court terme
- Favoris (auth JWT optionnelle)

## Implemented (2026-04-18)
- ✅ Backend Open-Meteo proxy: `/api/weather/{current,forecast,history}` + `/api/storms/zones` (grille 5x5)
- ✅ Auth JWT: register/login/me + favorites CRUD
- ✅ Dashboard React asymétrique 4/8 (sidebar + carte Leaflet)
- ✅ Bento conditions actuelles (T°, vent, humidité, pression)
- ✅ Jauge CAPE + indice LPI
- ✅ Histogramme historique 24h (Recharts) avec heures orageuses
- ✅ Aire prévision 24h (Recharts) probabilité précipitations
- ✅ Carte CartoDB Positron + cercle 20km + marqueurs zones (couleur + ping si orage)
- ✅ AuthDialog (Shadcn) + FavoritesList
- ✅ Auto-refresh 2 min + indicateur "EN DIRECT"

## Test Results (iteration_1)
- Backend: 17/17 tests OK (100%)
- Frontend: tous flux OK

## P1 Backlog
- Notifications push navigateur quand orage détecté
- Mode plein écran carte
- Export PDF du bulletin orage
- Comparaison historique multi-jours

## P2 Backlog
- Internationalisation (EN/ES)
- Source supplémentaire (Blitzortung pour vrais impacts)
- PWA installable

## Phase 2 Implemented (2026-04-18)
- ✅ **Blitzortung WebSocket** temps réel : écoute wss://ws{1-8}.blitzortung.org, décodeur LZW custom, filtre strikes dans 120km autour de Lourdes, stockage en mémoire (deque 5000 max), endpoint `/api/lightning/strikes` + `/api/lightning/status`
- ✅ **Notifications navigateur** : toggle "Activer les alertes" dans la sidebar, demande permission, déclenche `Notification(...)` sur détection d'orage ou impacts foudre fraîchement arrivés
- ✅ **Plein écran carte** : bouton top-right qui masque la sidebar (map col-span-12)
- ✅ **Géolocalisation** : bouton crosshair top-right qui recentre sur la position de l'utilisateur (Geolocation API)
- ✅ **Marqueurs foudre** sur la carte avec animation ping sur impacts récents (<60s)
- ✅ Badge "Impacts 1h" en bas-droite de la carte quand strikes présents

## Test Results (iteration_2)
- Backend: 21/21 tests OK (100%)
- Frontend: tous flux nouveaux OK

## P1 Backlog restant
- Export PDF bulletin orage
- PWA installable + Web Push serveur (persistent, même app fermée)
- Historique comparatif multi-jours

## Phase 3 Implemented (2026-04-18)
- ✅ **Export PDF "bulletin orage"** : endpoint `/api/reports/bulletin.pdf` (ReportLab) avec conditions actuelles, historique 24h, prévision 12h, impacts foudre récents. Bouton "Bulletin PDF" dans la sidebar
- ✅ **Historique multi-jours** : endpoint `/api/weather/history-days?days=N` avec agrégation quotidienne (précipitations, CAPE max, heures orageuses, rafales max, T° min/max). Composant `HistoryDaysChart` avec barres colorées (rouge=orage, noir=pluie, gris=sec)
- ✅ **Web Push serveur (VAPID)** : 
  - `pywebpush` + VAPID keys en `.env`
  - Service worker `public/sw.js` gère push/notificationclick
  - Endpoints `/api/push/{vapid-public-key,subscribe,unsubscribe,test}`
  - Tâche de fond `_alert_watcher` (toutes les 45s) envoie push sur transition storm_active + impacts foudre nouveaux dans le rayon
  - Deux toggles distincts dans la sidebar : "Alertes in-app" (Notification API seule) vs "Push serveur (même fermé)"

## Test Results (iteration_3)
- Backend: 30/30 tests OK (100%)
- Frontend: tous flux Phase 3 OK

## Roadmap
- P2 : PWA manifest + icon set (installable)
- P2 : Dashboard admin pour gérer abonnés push
- P2 : i18n (EN/ES pour pèlerins internationaux)

## Phase 4 Implemented (2026-04-18)
- ✅ **Curseur de rayon de surveillance** (20 → 70 km, pas de 10 km, défaut 20 km) : Slider Shadcn + 6 boutons presets (20/30/40/50/60/70). La carte ajuste automatiquement son zoom (11→9) et redessine le cercle en pointillés. Tous les flux (zones, foudre, PDF, alertes) utilisent le rayon choisi
- ✅ **Grille adaptative** : `sampling_grid` passe de 5×5 (25 pts) à 7×7 (45 pts) pour les rayons > 25 km, step_km = radius/4
- ✅ **Cache TTL** pour tous les endpoints Open-Meteo (current 60s / forecast 120s / history 300s / history-days 600s / zones 90s) — évite les 429 et rend les interactions quasi instantanées

## Test Results (iteration_4)
- Backend: 40/40 tests OK (100%)
- Frontend: tous flux Phase 4 OK

## Phase 6 Implemented (2026-04-18)
- ✅ **API sécurisée `/api/upload_storm`** : accepte `{distance, energy, timestamp}` en POST JSON, exige header `X-API-Key`. 401 sinon. Clé dans `.env` : `UPLOAD_API_KEY`
- ✅ **Stockage local persistant** : fichier `/app/backend/storm_data.json` (async-safe via asyncio.Lock, écriture atomique via tmp+rename). Endpoint `GET /api/storm_uploads?limit=N` pour lecture publique
- ✅ **Page Historique** (`/historique`) : 4 tuiles stats (événements / énergie totale / énergie max / distance moy) + 3 graphiques Recharts (aire Énergie/temps, scatter Distance×Énergie, histogramme par tranche 10km) + tableau des 25 derniers événements
- ✅ **Navigation** : `NavTabs` segmented control (Direct | Historique) monté en haut de la sidebar du moniteur live et dans le header de la page Historique. Routes React Router v7

## Test Results (iteration_5)
- Backend: 49/49 tests OK (100%)
- Frontend: tous flux Phase 6 OK

## Clés & URLs
- App : https://storm-monitor-20km.preview.emergentagent.com
- Page live : `/`
- Page historique : `/historique`
- Clé API upload : `lourdes-storm-upload-2026-xV7p9Qm3RtA8Ks` (header `X-API-Key`)
- Compte test : `test@lourdes.fr` / `storm123`

## Phase 7 Implemented (2026-04-18)
- ✅ **Couche "Nuages"** (NASA GIBS MODIS Terra, gratuit sans clé) : imagerie satellite vraie-couleur animée sur les **5 derniers jours** pour voir l'évolution des masses nuageuses
- ✅ **Couche "Pluie"** (RainViewer radar, gratuit sans clé) : radar de précipitations animé sur les **2 dernières heures**
- ✅ **Panneau de contrôle flottant** bottom-right carte : 2 boutons de toggle (exclusifs) + play/pause + slider temporel + timestamp du frame courant + crédit source
- ✅ **Fix responsive** : carte maintenant visible sur écrans < 1024px (h-[60vh] en haut + sidebar dessous au lieu de h-full sur row auto qui s'écrasait à 0px)
- ✅ Pane Leaflet dédié `weatherPane` z-index 350 pour que les overlays soient entre la base map et les marqueurs

## Test Results (iteration_6)
- Frontend: 100% des flux Phase 7 OK
- Testé sur viewports desktop (1920px) et mobile (800px)

## Phase 8 Implemented (2026-04-19)
- ✅ **Couche "Vent"** (Open-Meteo hourly wind_speed_10m + wind_direction_10m) : endpoint `/api/weather/wind-grid` + composant `WindLayer` avec flèches SVG rotées (rotation = direction, couleur = vitesse, taille = intensité, chiffre affiché au centre)
- ✅ **Détection mobile** : hook `useIsMobile` (breakpoint 768px). Panneau de couches météo : full-width en bas sur mobile (bottom-4 left-4 right-4), compact bottom-right sur desktop
- ✅ **Zoom sans limite** : `minZoom={2}` sur la carte et la tuile base (on peut dézoomer jusqu'au monde entier sur mobile)
- ✅ **Auto-zoom sur Pluie** : quand on active "Pluie", la carte se recentre automatiquement au niveau 7 (vue sud-ouest France + nord Espagne) pour voir les bandes pluvieuses au-delà du rayon 20km
- ✅ **Radar pro "Foudre Pro"** : color scheme RainViewer passé de 2 (universal blue) à 4 (The Weather Channel — couleurs pro jaune/orange/rouge), smooth=1 + snow=1
- ✅ **Hauteur carte mobile** passée de 60vh → 70vh pour une meilleure visibilité

## Test Results
- Backend `/api/weather/wind-grid` : 25 arrows OK (max_speed 6.2 km/h actuellement)
- Frontend : toutes les 3 couches (Nuages, Pluie, Vent) fonctionnent avec auto-zoom pluie confirmé

## Phase 9 Implemented (2026-04-19) — Timeline 24h unifiée + Trajectoire prédite
- ✅ **Timeline 24h unifiée** (`/app/frontend/src/components/Timeline.jsx`) : slider 24h avec play/pause, badge "● EN DIRECT" ⇄ "↺ Rejeu · il y a X min", bouton "Retour au direct", tick marks -24h/-12h/-6h/-3h/now
- ✅ **Synchronisation tuiles météo** : `useWeatherLayersState({cursorTs,isLive})` choisit automatiquement la frame Nuages (NASA GIBS) ou Pluie (RainViewer) la plus proche de cursorTs ; auto-play suspendu quand on scrub
- ✅ **Filtrage des impacts** : `Dashboard.jsx` fetch les impacts sur 24h (`STRIKES_WINDOW_S = 24*3600`) et filtre l'affichage dans une fenêtre 1h centrée sur cursorTs (`DISPLAY_WINDOW_S = 3600`)
- ✅ **TrajectoryLayer** (`/app/frontend/src/components/TrajectoryLayer.jsx`) : polyline rouge + point de départ + tête sur la position prédite, alimentée par `/api/storms/trajectory` (régression linéaire lat/lon sur les 60 min récentes, projection jusqu'à +45 min par pas de 10 min)
- ✅ **Toggle Trajet** ajouté au panneau des couches météo (activé par défaut) ; panneau interne "frame-slider" masqué via prop `timelineDriven`

## Test Results (iteration_7)
- Backend : 53/53 tests passent (nouveau `/api/storms/trajectory` inclus, toutes régressions OK)
- Frontend : Timeline rend bien, scrub → badge Rejeu, reset-live OK, 4 toggles Nuages/Pluie/Vent/Trajet, frame-slider masqué quand `timelineDriven`
- Aucune action-item en attente, aucun retest nécessaire

## Prochaines pistes / Backlog
- Badge flottant vitesse/cap/ETA de la trajectoire au-dessus de la carte
- Option : ancrer la prédiction de trajectoire sur cursorTs (actuellement toujours "live") — pour voir ce que le modèle prévoyait il y a X minutes
- Export bulletin PDF multilingue (EN)
- PWA installable + badge icon number pour impacts en cours


## Phase 10 Implemented (2026-04-19) — Vigilance + stabilité tuiles + presets timeline
- ✅ **Vigilance "à la Météo-France"** (`/app/backend/vigilance.py` + `/api/weather/vigilance`) : calcul 4 niveaux (vert/jaune/orange/rouge) sur 6 phénomènes (orages, vent, pluie-inondation, canicule, grand froid, neige-verglas) pour Lourdes (65) + 4 départements voisins (64, 32, 31, 09). Source : Open-Meteo forecast+daily, cache 15 min. (L'API officielle Météo-France est protégée par Akamai/token depuis le sandbox — le disclaimer redirige vers vigilance.meteofrance.fr)
- ✅ **`<VigilanceBanner>`** (`/app/frontend/src/components/VigilanceBanner.jsx`) : bandeau couleur en haut du sidebar, click-to-expand → grille 6 phénomènes × (aujourd'hui/demain) + chips des départements voisins + disclaimer
- ✅ **Fix clignotement Nuages** : `playing = false` par défaut dans `useWeatherLayersState` → les tuiles restent figées sur la frame la plus récente (ou choisie). User peut relancer l'animation via le bouton play/pause interne
- ✅ **Slider de frames réactivé** : le slider `data-testid='frame-slider'` est à nouveau visible dans le `WeatherLayersPanel` pour choisir manuellement l'instant (clouds 5 jours / radar 2 h)
- ✅ **Presets Timeline** : chips "Maintenant / -30 min / -1 h / -3 h / -6 h / -12 h" (`data-testid='timeline-preset-{offset}'`) pour sauter rapidement à un instant antérieur ; le preset actif est surligné

## Test Results (iteration_8)
- Backend 57/57 tests (nouveau `/api/weather/vigilance` validé, structure complète, cache OK, toutes régressions)
- Frontend 100% : VigilanceBanner + expand, presets Timeline, plus de clignotement des nuages, frame-slider visible
- Aucune action-item en attente, aucun retest nécessaire

## Prochaines pistes / Backlog
- Badge flottant vitesse/cap/ETA de la trajectoire au-dessus de la carte
- Option : ancrer la prédiction de trajectoire sur cursorTs (au lieu de toujours live)
- Si un compte Météo-France API est fourni par l'utilisateur, brancher la vigilance officielle (token → `public-api.meteofrance.fr/.../cartevigilance/encours`)
- Bouton "Partager l'orage" (lien horodaté `?ts=&radius=`)
- PWA installable + badge numérique
- Export bulletin PDF multilingue (EN)


## Phase 11 Implemented (2026-04-19) — Click-to-fit trajectoire + push vigilance auto
- ✅ **TrajectoryBadge cliquable** : devient `<button>` avec icône `Maximize2`. Clic → `onFit()` → `fitSignal++` → `TrajectoryLayer` appelle `map.flyToBounds(waypoints + center, maxZoom:10, duration:0.8)` et cadre automatiquement la carte sur la trajectoire prédite. Désactivé (disabled + cursor-default) quand `!detected`
- ✅ **Filtre trajectoire "bruitée"** côté backend (`analysis.predict_trajectory`) : rejette les régressions > 120 km/h (`noise_too_high`) et < 3 km/h (`stationary`). Évite d'afficher des polylignes délirantes quand la foudre est spatialement dispersée (Pyrénées = cellules multiples)
- ✅ **Fix rate-limit Open-Meteo** pour vigilance : single-request multi-location (`latitude=43.0951,43.18,...&longitude=...`) au lieu de 5 requêtes parallèles
- ✅ **Push auto vigilance** dans `_alert_watcher` : toutes les 20 min vérifie `compute_vigilance()` pour Lourdes (65). Sur transition vers niveau ≥3 ET > niveau précédent, envoie push VAPID avec titre `⚠ Vigilance ORANGE/ROUGE · Lourdes` et liste les phénomènes concernés (orages, vent, pluie-inondation, etc.)

## Test Results (iteration_9)
- Backend 61/61 (57 intégration + 4 tests unitaires predict_trajectory : not_enough_strikes / stationary / noise_too_high / happy path)
- Frontend 100% : trajectory-badge est un `<button>` avec état disabled correct + reason text lisible
- Zéro critical, zéro action item

## Prochaines pistes / Backlog
- Ancrer la prédiction de trajectoire sur `cursorTs` (rejouer ce que le modèle prévoyait)
- PWA installable + badge numérique
- Partage URL horodatée (`?ts=&radius=`)
- Bulletin PDF multilingue (EN)
- Si clé Météo-France officielle fournie, remplacer la vigilance locale

