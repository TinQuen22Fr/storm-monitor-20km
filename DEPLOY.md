# Storm Monitoring — Déploiement sur Kimsufi / VPS

Guide opérationnel pour installer, mettre à jour, et migrer la production sur un serveur Ubuntu/Debian.

**Repo** : https://github.com/TinQuen22Fr/storm-monitor-20km
**URL prod** : https://storm-monitor.quentin-astro.fr

---

## Architecture

Deux dossiers, deux rôles **strictement séparés** :

| Dossier | Rôle | Modifié par |
|---|---|---|
| `/opt/storm-monitor` | **WORK_DIR** — clone git, source de vérité pour `git pull` / `git checkout`. Aucun runtime ici. | Vous, à la main (`git`) |
| `/var/www/storm-monitor` | **APP_DIR** — runtime servi par Nginx + systemd. Contient `venv/`, `frontend/build/`, `backend/.env`, `cache/`, `storm_data.json`. | Le script `install.sh` (via `rsync`) |

Le script `install.sh` fait `git pull` dans `/opt`, puis `rsync` vers `/var/www` en **excluant** les fichiers runtime :
`.env`, `.env.backups/`, `venv/`, `storm_data.json`, `cache/`, `frontend/build/`, `frontend/node_modules/`, `frontend/.env`.

Conséquence : **vos secrets, votre venv Python, votre build front, vos données — rien n'est jamais écrasé par une mise à jour.**

---

## Branches Git

| Branche | Cible | Contient |
|---|---|---|
| `Testing` (défaut public) | Tout le monde, sans matériel | Web app pure : carte, alertes, vigilance, replay. Pas de firmware. |
| `Version_With_Detector` | Mon serveur Kimsufi | `Testing` + route `/api/upload_storm`, page `/detector`, autotune wizard, dossier `hardware/` (sketches Arduino AS3935). |

> Le firmware Arduino dans `hardware/` est temporairement cohabité dans le repo principal. À terme il sera extrait dans un repo dédié (`storm-monitor-firmware`). En attendant il est **uniquement présent sur `Version_With_Detector`**, la branche `Testing` reste générique.

Le script utilise la variable d'env `BRANCH` (défaut : `Version_With_Detector`) :

```bash
sudo BRANCH=Testing bash install.sh                 # version publique sans détecteur
sudo BRANCH=Version_With_Detector bash install.sh   # version perso avec détecteur (défaut)
```

---

## A) Installation propre (serveur vierge)

**Pré-requis** : Ubuntu 22.04 / 24.04 ou Debian 12, accès root SSH, nom de domaine pointant vers le serveur.

```bash
# 1. Cloner le repo dans /opt (WORK_DIR)
sudo mkdir -p /opt
sudo git clone -b Version_With_Detector \
  https://github.com/TinQuen22Fr/storm-monitor-20km.git \
  /opt/storm-monitor

# 2. Lancer l'install (clone -> rsync -> venv -> build -> nginx -> systemd)
cd /opt/storm-monitor
sudo bash install.sh
```

Le script va :
1. Installer Python 3.11+, Node 20, Yarn, MongoDB (8.0 si AVX, sinon 4.4), Nginx 1.30+ (depuis nginx.org), ffmpeg, rsync, curl HTTP/3 via snap.
2. Synchroniser `/opt/storm-monitor` → `/var/www/storm-monitor`.
3. Créer le venv Python + `pip install -r requirements.txt`.
4. Générer `/var/www/storm-monitor/backend/.env` avec des secrets aléatoires (JWT, VAPID, UPLOAD_API_KEY).
5. Builder le frontend.
6. Écrire le vhost Nginx (HTTP-only au début, HTTPS auto si certs déjà présents) + le service systemd `storm-monitor.service` sur port 8003.
7. Tout démarrer.

### Renseigner les clés tierces (Resend, webhooks)

Le `.env` généré contient des champs vides à remplir :

```bash
sudo nano /var/www/storm-monitor/backend/.env
```

À renseigner :

```env
RESEND_API_KEY="re_xxx"                            # https://resend.com/api-keys
ADMIN_EMAIL="quentin.dumont.22@gmail.com"          # compte super-admin

# Optionnels — webhooks d'alerte
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
TELEGRAM_BOT_TOKEN="..."
TELEGRAM_CHAT_ID="..."
```

Puis :

```bash
sudo systemctl restart storm-monitor
```

### Activer HTTPS (Certbot)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d storm-monitor.quentin-astro.fr
```

Au prochain `sudo bash install.sh`, le vhost HTTPS + HTTP/3 sera écrit automatiquement (le script détecte la présence des certs).

### Activer HTTP/3 (QUIC)

```bash
sudo ufw allow 443/udp && sudo ufw reload
# ou
sudo iptables -I INPUT -p udp --dport 443 -j ACCEPT
```

Vérification :

```bash
curl3 --http3-only -sI https://storm-monitor.quentin-astro.fr/ | head -3
# attendu: HTTP/3 200
```

---

## B) Mise à jour d'une install existante

C'est le cas usuel : vous avez poussé du code sur GitHub, vous voulez le déployer.

```bash
cd /opt/storm-monitor
git pull
sudo bash install.sh
```

Ou en une ligne :

```bash
cd /opt/storm-monitor && git pull && sudo bash install.sh
```

Ce qui se passe :
1. `git pull` met à jour `/opt/storm-monitor` (WORK_DIR).
2. `install.sh` détecte le clone existant, fetch+pull à nouveau (idempotent), affiche la liste des commits récupérés.
3. **Backup auto du `.env`** dans `/var/www/storm-monitor/backend/.env.backups/.env.YYYYMMDDTHHMMSSZ` (rotation : 10 derniers conservés).
4. `rsync` synchronise `/opt` → `/var/www` en préservant runtime (`.env`, `venv/`, `cache/`, `storm_data.json`, `build/`, `node_modules/`).
5. `pip install -r requirements.txt` met à jour les dépendances Python.
6. `ensure_env_var` ajoute les nouvelles variables d'env apparues dans la release **sans toucher aux valeurs existantes**.
7. `yarn install --frozen-lockfile && yarn build` rebuilds le frontend.
8. Reload Nginx + restart `storm-monitor.service`.

> Le `.env` n'est jamais écrasé. Les nouveaux champs sont ajoutés vides à la fin. Vous gardez vos clés Resend / VAPID / JWT.

### Restaurer un `.env` depuis un backup

```bash
ls -lt /var/www/storm-monitor/backend/.env.backups/
sudo cp /var/www/storm-monitor/backend/.env.backups/.env.YYYYMMDDTHHMMSSZ \
        /var/www/storm-monitor/backend/.env
sudo systemctl restart storm-monitor
```

---

## C) Migration de branche (Testing ↔ Version_With_Detector)

### Méthode 1 — Via variable d'env (recommandée)

```bash
# Basculer vers Version_With_Detector (avec détecteur AS3935)
sudo BRANCH=Version_With_Detector bash /opt/storm-monitor/install.sh

# Revenir à Testing (version publique sans matériel)
sudo BRANCH=Testing bash /opt/storm-monitor/install.sh
```

Le script :
1. Détecte que la branche actuelle ≠ `BRANCH` demandée.
2. Fait `git fetch && git checkout -B "$BRANCH" "origin/$BRANCH"` dans `/opt/storm-monitor`.
3. Resync `rsync` vers `/var/www/storm-monitor`.
4. Reinstall les deps si différentes, rebuild front, restart services.

### Méthode 2 — Switch manuel puis install

```bash
cd /opt/storm-monitor
git fetch origin
git checkout Version_With_Detector
git pull
sudo bash install.sh
```

### Vérifier sur quelle branche tourne la prod

```bash
git -C /opt/storm-monitor rev-parse --abbrev-ref HEAD
git -C /opt/storm-monitor rev-parse --short HEAD
```

> Note : `/var/www/storm-monitor` n'a **pas** de `.git/` (exclu du rsync). La seule source de vérité branche/commit est `/opt/storm-monitor`.

---

## Diagnostic

```bash
# Service backend
sudo systemctl status storm-monitor
sudo journalctl -u storm-monitor -f
sudo tail -f /var/log/storm-monitor.err.log

# Nginx
sudo nginx -t
sudo tail -f /var/log/nginx/error.log

# MongoDB
sudo systemctl status mongod

# Test API local
curl http://127.0.0.1:8003/api/health
curl 'http://127.0.0.1:8003/api/weather/current?lat=43.0951&lon=-0.0434'
```

---

## En cas de problème

| Symptôme | Action |
|---|---|
| `storm-monitor.service` en boucle de crash | `sudo journalctl -u storm-monitor -n 200` → lire la stack. Souvent : variable `.env` manquante ou venv corrompu. |
| 502 Bad Gateway | Backend down → `systemctl restart storm-monitor`. |
| 404 sur l'app | Build front absent → `cd /var/www/storm-monitor/frontend && yarn build`. |
| Nginx reload échoue | `sudo nginx -t` pour voir l'erreur de syntaxe. |
| `.env` corrompu / mal édité | Restaurer un backup (voir section B). |
| Update a cassé un truc | `cd /opt/storm-monitor && git log --oneline -10`, `git checkout <commit_précédent>`, `sudo bash install.sh`. |

### Reset complet (dernier recours)

```bash
sudo systemctl stop storm-monitor
sudo rm -rf /var/www/storm-monitor
cd /opt/storm-monitor && sudo bash install.sh
```

⚠️ Régénère les secrets `.env` (JWT, VAPID, UPLOAD_API_KEY). Les abonnements push existants deviendront invalides. **Pensez à `cp /var/www/storm-monitor/backend/.env ~/env.save` avant** si vous voulez les conserver.

---

## Arborescence cible

```
/opt/storm-monitor/                  # WORK_DIR (git, jamais de runtime ici)
├── .git/
├── backend/
├── frontend/
├── hardware/                        # branche Version_With_Detector uniquement
└── install.sh

/var/www/storm-monitor/              # APP_DIR (runtime, géré par install.sh)
├── backend/
│   ├── .env                         # secrets — JAMAIS écrasé
│   ├── .env.backups/                # rotation 10 derniers
│   ├── venv/                        # Python virtualenv
│   ├── server.py
│   └── ...
├── frontend/
│   ├── build/                       # bundle React servi par Nginx
│   ├── .env                         # REACT_APP_BACKEND_URL=https://...
│   └── src/
├── cache/videos/                    # cache MP4 (TTL 24h)
└── storm_data.json                  # uploads détecteur AS3935

/etc/nginx/
├── sites-available/storm-monitor.conf
├── sites-enabled/storm-monitor.conf -> ../sites-available/storm-monitor.conf
├── snippets/storm-monitor-app.conf
└── conf.d/00-default-catchall.conf

/etc/systemd/system/storm-monitor.service
/var/log/storm-monitor.{log,err.log}
```

---

## Aide-mémoire

| Action | Commande |
|---|---|
| Déployer la dernière version | `cd /opt/storm-monitor && git pull && sudo bash install.sh` |
| Basculer sur la branche détecteur | `sudo BRANCH=Version_With_Detector bash /opt/storm-monitor/install.sh` |
| Basculer sur la branche publique | `sudo BRANCH=Testing bash /opt/storm-monitor/install.sh` |
| Redémarrer le backend | `sudo systemctl restart storm-monitor` |
| Recharger Nginx | `sudo systemctl reload nginx` |
| Voir les 100 dernières lignes de logs | `sudo journalctl -u storm-monitor -n 100` |
| Renouveler le certif SSL | `sudo certbot renew` |
| Lister les backups `.env` | `ls -lt /var/www/storm-monitor/backend/.env.backups/` |
| Vérifier branche en prod | `git -C /opt/storm-monitor rev-parse --abbrev-ref HEAD` |
