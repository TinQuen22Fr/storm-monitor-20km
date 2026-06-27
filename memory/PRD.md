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
- **[2026-02-28] Fix UX message d'erreur Prévisions** : amélioration de `PrevisionsPage.jsx`, `FranceMapPanel.jsx` et `VerticalProfileChart.jsx` pour distinguer un 404 (endpoint absent côté backend) d'une autre erreur. En cas de 404 sur `/api/weather/severe`, affichage de la procédure shell de remediation directement à l'écran. Validé par testing agent (iteration_24.json, 100%) — preview nominal OK + 404 simulé affiche le bon message.
  - **Diagnostic VPS Kimsufi** : le backend tournait sur la branche github `Testing` au lieu de `Version_With_Detector` → routes severe/grid/profile, reports/bulletin, share/snapshot etc absentes. **Fix utilisateur** : `sudo BRANCH=Version_With_Detector bash /opt/storm-monitor/upgrade.sh`.

- **[2026-02-27] Rollback calque nuages → NASA MODIS Terra** : Après plusieurs essais de filtres CSS sur Meteosat MSG (`blur` 3/5/18/30 px ± contrast), abandon du calque géostationnaire à cause de sa résolution native trop faible (~3 km/px) qui crée une grille de gros blocs inexploitables à l'échelle 20 km. Restauration du calque NASA GIBS MODIS Terra (polar orbit, ~250 m/px) : haute résolution spatiale, contours nuageux organiques, pas de pixelation. App.css entièrement nettoyé de tous les filtres `.meteosat-smooth-tile`. Cadence : ~1 pass/jour, timeline 5 jours navigables.

## 🟡 Backlog
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
