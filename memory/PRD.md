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
