# Évolutions futures — Storm Monitoring Lourdes

> Propositions d'améliorations pour rendre l'outil plus professionnel, convivial et
> collaboratif. Rien ici n'est engagé : c'est un vivier d'idées à piocher selon les
> envies et les priorités. Mis à jour au fil des discussions.

---

## 🤝 Esprit collaboratif

### C1 — Alertes personnalisées par utilisateur *(déjà évoqué, prioritaire)*
Chaque utilisateur règle son propre rayon d'alerte et ses seuils (nb d'impacts,
distance minimale, plage horaire de notification). Les notifications push FCM
deviennent réellement personnelles au lieu d'être calées sur la zone admin.

### C2 — Observations terrain communautaires
Un bouton « Je vois / j'entends l'orage » (grêle, rafales, pluie forte) horodaté et
géolocalisé. Les observations s'affichent sur la carte en temps réel : la communauté
devient un réseau de capteurs humains complémentaire de Blitzortung. Modération
simple par l'admin.

### C3 — Galerie photos d'orages
Upload de photos d'éclairs/de ciel par les membres (avec zone + horodatage),
galerie publique triée par épisode orageux détecté. Fort pouvoir fédérateur pour
une communauté de passionnés.

### C4 — Rôles et espaces multi-zones
Aujourd'hui : 1 admin (Lourdes) + favoris personnels. Demain : des « référents de
zone » (ex. un passionné à Tarbes, un à Pau) qui gèrent leur communauté locale,
leurs seuils et leurs bulletins.

### C5 — Réseau de détecteurs AS3935 partagé *(branche Version_With_Detector)*
Plusieurs membres installent un détecteur matériel chez eux et poussent leurs
données via `/api/upload_storm`. Triangulation grossière possible dès 3 détecteurs,
carte « réseau de capteurs » avec statut en ligne/hors ligne de chacun.

---

## 📊 Données & analyse

### D1 — Statistiques saisonnières
Avec la persistance MongoDB 30 j (faite), étendre à une rétention agrégée illimitée :
compteurs journaliers compacts (nb impacts, heures orageuses) conservés pour
toujours (< 1 Ko/jour). Graphiques « saison 2026 vs 2027 », records (jour le plus
foudroyé, orage le plus long).

### D2 — Score de sévérité des épisodes
Classer automatiquement chaque épisode du Replay (faible/modéré/fort/sévère —
déjà esquissé) et l'archiver dans un « livre des orages » consultable, avec le
bulletin PDF de l'épisode généré automatiquement à la fin de celui-ci.

### D3 — Corrélation détecteur AS3935 vs Blitzortung
Quand le détecteur matériel sera en place : superposer ses détections aux impacts
Blitzortung pour évaluer sa fiabilité et calibrer son gain automatiquement.

### D4 — Export CSV des données
Bouton d'export des impacts/historiques en CSV pour les membres qui veulent faire
leurs propres analyses (esprit science participative).

---

## 📱 Confort & convivialité

### U1 — Alerte pluie imminente push *(suite logique du badge AROME)*
Notification quand le nowcast AROME 15 min détecte de la pluie arrivant sous
30 min sur la zone de l'utilisateur. Différencier pluie simple / orage.

### U2 — Partage bulletin WhatsApp / lien direct *(déjà en backlog)*
Un clic pour partager le bulletin PDF ou un lien public de la situation en cours.

### U3 — Mode sombre complet
Assortir le « mode soirée orage » au thème éclair : panneaux sombres translucides,
confort nocturne pendant les observations (usage réel : on regarde l'app la nuit
pendant l'orage).

### U4 — Widget / écran d'accueil Android
Widget Capacitor affichant le statut (CALME/ACTIF), le nb d'impacts 24 h et la
prochaine pluie — sans ouvrir l'app.

### U5 — Onboarding nouveau membre
Mini-parcours à la première connexion : choisir sa zone, son rayon, activer les
notifications. Trois écrans, gros gain de convivialité pour le côté collaboratif.

---

## 🔧 Technique & robustesse

### T1 — Correctifs sécurité *(en pause, à reprendre avant ouverture large)*
Injection Mongo sur unsubscribe, endpoints de test publics, rate-limit sur
subscribe, email admin exposé dans /api/health. **Indispensable avant d'ouvrir
l'inscription à des inconnus.**

### T2 — Page « état du système » publique
Uptime, connexion Blitzortung, fraîcheur Open-Meteo, dernier flush Mongo, quota
Xweather. Transparence pour la communauté + diagnostic rapide pour l'admin.

### T3 — Sauvegarde automatique MongoDB
mongodump quotidien vers un second emplacement du serveur (voire un stockage
distant), rotation 7 jours. Protège l'historique communautaire.

### T4 — Collecte Blitzortung France entière *(discuté le 26/07/2026 — reporté volontairement)*
**Contexte** : aujourd'hui la collecte couvre 300 km autour de Lourdes. Un membre
au Mans ou à Saint-Brieuc n'a donc pas accès au Replay (message « hors couverture »).
**Décision** : on garde 300 km tant que le Storm Monitor n'est pas diffusé largement —
l'outil est né pour un usage perso/pro autour de Lourdes et sa communauté actuelle
est Sud-Ouest. À réévaluer quand la diffusion (écosystème Sentinelle du Ciel) amènera
des membres hors Sud-Ouest.
**Plan technique prêt le jour venu** : remplacer le filtre rayon par un rectangle
France métropolitaine + Andorre (lat 41→51.5, lon −5.5→9.7), cohérent avec la page
Vigilance. Volume estimé au pire (grosse journée orageuse nationale) : 100 à 300 k
impacts/jour ≈ 1-2 Go max en base avec la purge 30 j — négligeable sur le SSD 500 Go.
Mémoire : ~10 Mo. Le flux réseau Blitzortung ne change pas. Prérequis conseillés :
T3 (sauvegardes) et D1 (agrégats saisonniers).

---

*Dernière mise à jour : 2026-07-26*
