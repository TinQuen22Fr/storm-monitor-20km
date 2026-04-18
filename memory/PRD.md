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
