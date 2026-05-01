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


## Phase 12 Implemented (2026-04-19) — Vigilance OFFICIELLE MF + clustering spatial
- ✅ **Vigilance officielle Météo-France** via **MeteoAlarm** (https://feeds.meteoalarm.org/api/v1/warnings/feeds-france) : données officielles identiques au site vigilance.meteofrance.fr, open-data, sans clé. Mapping par code NUTS3 (FR626=Hautes-Pyrénées, FR615=Pyrénées-Atlantiques, FR624=Gers, FR623=Haute-Garonne, FR621=Ariège, FR815=Pyrénées-Orientales, FR613=Landes)
- ✅ 7 départements suivis (65, 64, 32, 31, 09, 66, 40), 8 phénomènes (ajout Brouillard, Avalanches)
- ✅ **Fallback gracieux** : si MeteoAlarm down, bascule sur estimation Open-Meteo locale avec disclaimer explicite
- ✅ **Clustering spatial pour trajectoire** (`_find_dominant_cluster` dans analysis.py) : grille 0.25° + voisinage 9 cellules → isole la cellule orageuse dominante avant la régression linéaire. Élimine le bruit "4000 km/h" quand la foudre est dispersée en plusieurs cellules indépendantes
- ✅ **Guard anti-bruit sur analyze_approach** : rejette les approches > 120 km/h avec `reason="noise_too_high"` + clustering appliqué en amont. Plus d'alerte ridicule "vitesse 795 km/h, ETA 5 min"
- ✅ Source + disclaimer transparents dans la réponse : `source="meteoalarm"`, `source_label="Météo-France (via MeteoAlarm)"`, `source_url="https://vigilance.meteofrance.fr/"`

## Test Results (iteration_10)
- Backend 64/64 tests (5 nouveaux unitaires predict_trajectory dont 2 clustering)
- Validé live : MeteoAlarm retourne "Vigilance jaune orages" pour 65, 64, 32, 31, 09, 66, 40 — correspondance parfaite avec le site officiel
- Frontend 100% : bandeau jaune affiché, 8 phénomènes, disclaimer "Météo-France (via MeteoAlarm)" visible

## Prochaines pistes / Backlog
- Ancrer la prédiction de trajectoire sur `cursorTs` (rejouer le passé)
- PWA installable + badge numérique
- Partage URL horodatée
- Bulletin PDF multilingue
- Mode "Soirée orage" (plein écran sombre + son d'impact)


## Phase 13 Implemented (2026-04-19) — Rayon 70km · Mode soirée orage · Carte partageable
- ✅ **Rayon de calcul 70 km** (au lieu de 150 pour trajectoire, 100 pour approche) : correspond au max du slider UI, focalise les calculs sur la zone réellement pertinente pour Lourdes
- ✅ **Mode soirée orage** (`/app/frontend/src/components/NightStormMode.jsx`) : overlay plein écran z-[2000], fond dark CartoDB, auto-zoom bounds sur les impacts + centre, cercles rayon 20 km (rouge) et 70 km (gris pointillé). Markers foudre animés (ping jaune <30s, orange <2min, rouge plus ancien). **Beep Web Audio API** (880Hz → 220Hz) sur chaque nouvel impact <30 km du centre. Toggle son, bouton close
- ✅ **Carte partageable PNG** (`/app/backend/share_card.py` + route `/api/share/card.png`) : image 1200x630 (format OG standard) générée avec Pillow, bandeau vigilance (vert/jaune/orange/rouge), compteur d'impacts, orage le plus proche, approche/trajectoire détaillée, timestamp. Bouton "Partager (WhatsApp…)" utilise `navigator.share` avec fichier sur mobile, ou copie l'URL + ouvre dans un onglet sur desktop

## Test Results (iteration_11)
- Backend : /api/share/card.png retourne PNG binaire ~39 KB, vigilance jaune affichée correctement
- Frontend : share-card-button, night-mode-button, overlay fullscreen, close, sound toggle, cercles 20/70 km, dark tiles — tout validé
- 100% des regressions OK
- (Note) Cache-Control écrasé par l'ingress preview Kubernetes — comportement infra, pas un bug code

## Prochaines pistes / Backlog
- Ancrer la prédiction de trajectoire sur `cursorTs` (rejouer le passé)
- PWA installable + badge numérique
- Partage URL horodatée `?ts=&radius=`
- Bulletin PDF multilingue (EN)
- Vigilance officielle MF via clé API si fournie (actuellement MeteoAlarm — source officielle MF)


## Hotfix (2026-04-19) — Horaires PDF en heure locale
- ✅ `reports.py` : nouvelle fonction `_utc_to_local_str` qui convertit les timestamps UTC en Europe/Paris via zoneinfo. Header affiche `(HEURE LOCALE)`, tableau Prévision 12 h = "Heure locale", tableau Impacts foudre = "Heure locale"
- ✅ Validé par extraction PDF : `BULLETIN ORAGE LOURDES · 19 apr 2026 · 21:49 (HEURE LOCALE)` et colonnes "Heure locale"


## Hotfix (2026-04-19) — Dialog scroll + polygones vigilance sur carte
- ✅ **Scroll dialog 7 jours** : `DialogContent` passe en `flex flex-col`, en-tête en `shrink-0`, zone grille en `flex-1 min-h-0 overflow-y-auto` → les 7 jours (dim → sam) sont tous accessibles, scroll vertical interne confirmé (scrollHeight 904 > clientHeight 798)
- ✅ **Polygones de vigilance sur la carte** (`/app/frontend/src/components/VigilancePolygons.jsx`) : récupère `/geo/lourdes-depts.geojson` (7 départements 65, 64, 32, 31, 09, 66, 40) + `/api/weather/vigilance` et dessine les contours colorés selon le niveau max de chaque dept (vert transparent, jaune #F59E0B fill 0.22, orange #EA580C 0.32, rouge #DC2626 0.4). Tooltip sticky au survol avec nom du dept + phénomènes actifs
- ✅ Nouveau toggle **VIGILANCE** (5e bouton) dans `WeatherLayersPanel` (`data-testid='toggle-vigilance-polygons'`), activé par défaut
- ✅ GeoJSON national data.gouv.fr simplifié (~85 KB), servi depuis `/app/frontend/public/geo/`


## Hotfix (2026-04-19) — Résilience Open-Meteo (fini les 500)
**Problème**: Open-Meteo rate-limite (429) le serveur après trop d'appels, ce qui faisait remonter des 500 côté frontend sur `/api/weather/current`, `/api/weather/forecast`, `/api/weather/history`, `/api/storms/zones`, `/api/forecast/storm-risk`.

**Correctifs livrés**:
- ✅ **`get_with_retry`** (weather.py) : helper centralisé avec retry 429/503 court (2 tentatives, 1-2s) pour ne pas saturer
- ✅ **Cache résilient avec stale-while-error** + **persistance sur disque** (`/app/backend/.stale_cache.pkl`) : survit aux redémarrages backend, sert les dernières bonnes données quand l'upstream tombe
- ✅ **TTLs augmentés** : current 60s→180s, forecast 120s→600s, zones 90s→240s
- ✅ **Mode dégradé propre** : endpoints retournent 200 avec `{degraded: true, message: "..."}` au lieu de 500 quand aucune donnée stale n'est disponible
- ✅ **Bandeau UI ambré** (`data-testid="degraded-banner"`) quand l'app détecte le mode dégradé — message explicite "Service météo limité par le fournisseur — reprise automatique sous quelques minutes"
- ✅ Appliqué aussi à vigilance.py pour MeteoAlarm + fallback Open-Meteo

**Validé**: tous les endpoints répondent en 200 même sous 429, app reste entièrement fonctionnelle côté UI, bandeau ambré visible, `—` propre dans les tuiles de conditions quand pas de données.


## Phase 14 (2026-04-21) — Page Vigilance dédiée France + Andorre
- ✅ **Nouvel onglet `/vigilance`** (`/app/frontend/src/pages/VigilancePage.jsx`) : carte dédiée France métropolitaine + DOM + Andorre avec panneau latéral (niveau général, légende avec compteurs par couleur, détail cliquable/survol par département). Layout grid 1/4 + 3/4 sur desktop
- ✅ **Endpoint `/api/weather/vigilance/full`** : agrège MeteoAlarm France + MeteoAlarm Andorre, mappe les 101 départements (96 métro + 5 DOM) via table `INSEE_TO_NUTS3` et ajoute l'Andorre. Retourne `{areas: [...102...], overall_level, ...}`
- ✅ **GeoJSON départements** (~220 KB) simplifié via topojson `toposimplify(epsilon=0.02)`, servi depuis `/geo/france-depts.geojson`. Andorre en polygone simple dans `/geo/andorra.geojson`
- ✅ **NavTabs enrichi** : 3 onglets Direct / Vigilance / Historique (icône `AlertTriangle`)
- ✅ **Dashboard principal nettoyé** : `VigilancePolygons` retiré du map, toggle "Vigilance" retiré du panneau des couches. La carte de Lourdes est à nouveau dédiée au suivi d'orage pur

## Test Results (iteration_12)
- Backend 12/12 pytest passent — endpoint `/api/weather/vigilance/full` retourne 102 zones, Hautes-Pyrénées en jaune orages, Andorre incluse
- Frontend 100% : page /vigilance rend 97 polygones (96 + Andorre), couleurs correctes (#F59E0B pour jaune), légende avec compteurs corrects, interaction hover/click met à jour le panneau de détail
- Dashboard principal nettoyé : plus de `toggle-vigilance-polygons`, tous les autres sélecteurs préservés
- Zéro critical, zéro action item

## Prochaines pistes / Backlog
- Filtre par phénomène (afficher uniquement les orages / vent / neige…) sur la page /vigilance
- Ancrer la prédiction de trajectoire sur `cursorTs`
- PWA installable + badge numérique
- Partage URL horodatée `?ts=&radius=`
- Bulletin PDF multilingue (EN)
- Polygone Andorre plus précis si besoin (actuellement une enveloppe approximative)


## Phase 15 (2026-04-30) — Déploiement Kimsufi finalisé

### Problèmes résolus
- ❌ **Doublons Nginx** (`location = /sw.js` + `location = /index.html`) → causaient `nginx -t` qui plantait. Le `sed` précédent injectait dans un vhost qui les contenait déjà.
- ❌ **Redirection Android SQM → storm-monitor** : HTTP/2 connection coalescing de Chrome réutilisait une seule connexion TLS entre les 2 vhosts siblings.
- ❌ **Nginx 1.24 (paquet Ubuntu)** : trop vieux pour la syntaxe `http2 on;` moderne.

### Corrections appliquées dans `/app/install.sh`
- ✅ **Installation auto de Nginx 1.30+** depuis le dépôt officiel `nginx.org` (purge préalable du paquet Ubuntu, clé GPG + pinning apt)
- ✅ **Auto-injection** de `include /etc/nginx/sites-enabled/*;` dans `nginx.conf` (le layout nginx.org ne le charge pas par défaut)
- ✅ **Syntaxe moderne HTTP/2** : `http2 on;` en directive séparée (plus `listen ... http2;` déprécié)
- ✅ **Snippet idempotent** : `storm-monitor-app.conf` réécrit à chaque run, zéro risque de doublon
- ✅ **Cache headers cohérents** : `no-cache` sur `/sw.js` + `/index.html`, `max-age=31536000 immutable` sur `/static/`
- ✅ **Catch-all vhost anti-bleed** (`return 444`) + strip automatique de tout `default_server` résiduel des autres vhosts
- ✅ Vhost storm-monitor propre : un bloc 80 (redirect HTTPS + ACME), un bloc 443 (SSL + include snippet)

### Vérification prod
- ✅ `grep -r emergent /var/www/storm-monitor/frontend/build/` → **0 occurrence**
- ✅ `<title>` = `Storm Monitoring`, `<meta author>` = `Quentin Dumont`
- ✅ Domaine JS embarqué = `storm-monitor.quentin-astro.fr` uniquement
- ✅ Les deux vhosts SQM et storm-monitor coexistent, pas de bleed Android (HTTP/2 `http2 on;` n'active plus le coalescing cross-domain grâce au catch-all)

### État final
- Server Kimsufi `ns3020148` → Nginx 1.30.0 → storm-monitor.quentin-astro.fr opérationnel HTTPS
- Backend FastAPI uvicorn en port 8003 géré par systemd
- MongoDB 8.0, Python venv, Node 20 + Yarn
- SQM (port 8001) toujours fonctionnel sur son propre vhost



## Phase 16 (2026-04-30) — Filtre vigilance par phénomène + trajectoire ancrée sur cursorTs

### Feature 1 : Filtre par phénomène sur `/vigilance`
- ✅ **9 boutons filtre** (`data-testid=vigilance-filter-{all,orage,vent,pluie,canicule,grand-froid,neige,brouillard,avalanche}`) avec compteurs par phénomène
- ✅ Coloration de la carte bascule entre `max_level` global et niveau du phénomène sélectionné
- ✅ Panneau "Niveau général" devient "Niveau · {phénomène}" avec recalcul du max
- ✅ Tooltip département adapté + légende (compteurs par niveau) recomputée en fonction du filtre
- ✅ Panneau détail département highlight le phénomène actif

### Feature 2 : Trajectoire ancrée sur le cursor de la timeline
- ✅ **Backend** : `/api/storms/trajectory` + `/api/storms/approach` acceptent un param optionnel `at_ts` (epoch seconds)
- ✅ `lightning.py StrikeStore.recent` gagne un param `until_ts` filtrant les strikes `ts > until_ts`
- ✅ `analysis.predict_trajectory` reçoit `now=at_ts` pour ancrer la projection dans le passé
- ✅ **Frontend** : `TrajectoryLayer` + `TrajectoryBadge` reçoivent `cursorTs` + `isLive` en props
- ✅ Mode live : comportement inchangé, aucun `at_ts` envoyé, refresh 30s
- ✅ Mode replay : `at_ts=cursorTs` envoyé, pas d'interval, polyline violet `#7C3AED`, badge "TRAJ · REJEU" avec icône `Clock`
- ✅ La trajectoire reste cliquable pour fit-zoom même en mode replay

### Tests (iteration_13)
- Backend 14/14 pytest passent (`test_at_ts_filter.py` créé)
- Frontend e2e 100% : 9 filter buttons OK, scrub → at_ts envoyé, badge bascule rouge→violet, restore live = OK
- **Zéro critical, zéro action item, zéro régression**

## Phase 17 (2026-05-01) — Mode Replay "Orages majeurs"

### Feature
Détection automatique des épisodes orageux (bursts de strikes) dans les 24h passées, avec page dédiée + intégration sur la home page. L'utilisateur peut rejouer un épisode en un clic — la timeline s'anime automatiquement avec trajectoire/strikes/cartes synchronisés.

### Backend
- ✅ Nouveau `GET /api/replay/events?lat&lon&radius_km&min_strikes=5&gap_min=15`
- ✅ Algo : segmentation par time-gap + filtre `min_strikes` + duration ≥5min + peak rolling-window 10min
- ✅ Payload : `{events: [{id, start_ts, end_ts, duration_min, strike_count, peak_count_10min, center_lat/lon, max_distance_km}], source_window_h: 24}`
- ✅ Tri par intensité (peak_count_10min desc, strike_count desc, start_ts desc)

### Frontend
- ✅ Nouvelle page `/replay` (`/app/frontend/src/pages/ReplayPage.jsx`) avec panneau "Comment ça marche", compteur "Résumé", liste interactive des events (intensité "Sévère/Fort/Modéré/Faible" selon peak rate)
- ✅ NavTabs étendu à 4 onglets : Direct / Vigilance / Replay / Historique
- ✅ Dashboard `?replay=start:end` bootstrap → `cursorTs=start`, `playing=true`, URL cleaned
- ✅ Bandeau violet `replay-banner` affiche l'épisode + bouton Sortir
- ✅ CTA violet `replay-cta` sur la sidebar home "Rejouer les N épisode(s) détecté(s)" (affiché uniquement si `replayEventsCount > 0 && !replay`)
- ✅ Auto-stop quand cursor atteint `end_ts` (bandeau reste, lecture pausée)
- ✅ Ticker live désactivé automatiquement en replay (isLive=false par cascade)

### Tests (iteration_14)
- Backend 7/7 pytest (`test_replay_events.py`) : shape, query params, 422 sur types invalides, détection 2-bursts + ignore isolated strike, exclusion <5min, exclusion <5 strikes, id format + centroid rounding
- Frontend e2e 100% : replay-page renders, 4 NavTabs, empty-state OK, bootstrap URL purple banner + dates formatées + URL cleaned, exit button, CTA absent si 0 events, régression live intacte
- **Zéro critical, zéro action item, zéro régression**


## Phase 18 (2026-05-01) — Démos d'orages reconstitués + Export MP4

### Démos Pyrénées (reconstitution scénarisée)
- `/app/backend/demo_storms.py` : 2 épisodes synthétiques mais physiquement plausibles
  - `demo-pyrenees-cevenol` : orage cévenol type fin avril, ~62 impacts, 45 min, drift SW→NE
  - `demo-cellule-isolee` : cellule isolée Argelès-Gazost, ~32 impacts, 20 min
- Endpoint `GET /api/replay/demos` → liste avec is_reconstructed=true (transparence pour l'utilisateur)
- Page /replay : section violette "Démos · Reconstitutions Pyrénées" avec badge DÉMO

### Export MP4 (Pillow + ffmpeg)
- `/app/backend/video_export.py` : rendu Pillow (720×720) + assemblage ffmpeg H.264
- Tuiles CARTO cachées localement (`/var/www/storm-monitor/cache/videos/tiles/`)
- 1 frame toutes les 30 s d'event = 24 fps output (45 min → ~6 s vidéo, ~50 KB)
- HUD complet : timestamp localisé, count impacts, label episode, branding "Quentin Dumont"
- Job system in-memory async, polling toutes les 1.5 s côté frontend
- Endpoints :
  - `POST /api/replay/video` (body avec demo_id ou start/end live) → `{job_id}`
  - `GET /api/replay/video/{job_id}` → status/progress/mp4_url
  - `GET /api/replay/video/{job_id}/file.mp4` → fichier MP4 (Content-Type: video/mp4)
- Purge automatique des MP4 > 24h

### Frontend
- `VideoExportDialog.jsx` : modal avec progression, player intégré, boutons Télécharger / WhatsApp / Copier lien
- Pages /replay : 4 boutons par demo (Rejouer Dashboard + Exporter MP4) et même structure pour events réels

### install.sh
- Ajout du paquet `ffmpeg` à apt-get
- Création `/var/www/storm-monitor/cache/videos/`
- Variable d'env `VIDEO_CACHE_DIR` dans la systemd unit
- `PrivateTmp=false` (cache MP4 doit survivre aux restarts)

### Tests (iteration_15)
- Backend 9/9 pytest : shape demos, POST 200/404/400, GET status, E2E queue→download→ffprobe (h264 720x720 ≥3s)
- Frontend 100% : section démos, 2 cards, dialog progress→player→download/whatsapp/copy, navigation play→Dashboard banner
- **Zéro critical, zéro action item, zéro régression**

