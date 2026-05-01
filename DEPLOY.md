# Déploiement Storm Monitoring sur Kimsufi

Guide complet pour installer et mettre à jour l'application **Storm Monitoring** sur un serveur personnel (Kimsufi / OVH Ubuntu).

**Auteur** : Build & Idea by Quentin Dumont
**Repo** : https://github.com/TinQuen22Fr/storm-monitor-20km
**URL prod** : https://storm-monitor.quentin-astro.fr

---

## 📂 Les 2 dossiers sur votre Kimsufi

Il y a volontairement **deux copies** du code sur le serveur, chacune avec un rôle différent :

| Dossier | Rôle | Qui le met à jour ? |
|---|---|---|
| `/opt/storm-monitor` | **Copie de travail** (là où vous faites `git pull` manuellement pour récupérer le code depuis GitHub) | **Vous, manuellement** |
| `/var/www/storm-monitor` | **Copie de déploiement** (lue par Nginx + systemd, c'est ce qui sert réellement l'application en prod) | **Le script `install.sh`** |

> ℹ️ **Pourquoi deux copies ?** La copie `/opt/storm-monitor` sert de "backup local" / espace pour bidouiller sans impacter la prod. La copie `/var/www/storm-monitor` n'est jamais modifiée à la main — elle est gérée de A à Z par `install.sh`.

---

## 🚀 Première installation (serveur vierge)

Pré-requis : serveur Ubuntu 22.04 / 24.04 / Debian 12, accès root SSH, nom de domaine pointant vers le serveur.

```bash
# 1. Cloner le repo dans /opt (emplacement de travail)
sudo git clone -b Testing https://github.com/TinQuen22Fr/storm-monitor-20km.git /opt/storm-monitor
cd /opt/storm-monitor

# 2. Lancer le script d'installation complet
sudo bash install.sh
```

Le script va automatiquement :
- Installer les dépendances système (Python 3.11+, Node 20, Yarn, MongoDB 8, **Nginx 1.30+** depuis nginx.org, **ffmpeg**, fonts DejaVu)
- Cloner le repo dans `/var/www/storm-monitor` (copie de déploiement)
- Créer le venv Python + installer les dépendances backend
- Générer `/var/www/storm-monitor/backend/.env` avec des secrets aléatoires (JWT, VAPID, clé upload)
- Builder le frontend en production
- Écrire le vhost Nginx + le snippet idempotent
- Créer le service systemd `storm-monitor.service` (port 8003)
- Démarrer tout

### Activer HTTPS (après la 1ère install)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d storm-monitor.quentin-astro.fr
```

Certbot ajoutera automatiquement le bloc 443 + la redirection HTTP → HTTPS.

### Activer HTTP/3 (QUIC) — optionnel mais recommandé

Storm Monitoring tourne sur Nginx 1.30+ qui supporte HTTP/3 nativement. Le vhost est déjà configuré (`listen 443 quic`, `http3 on`, header `Alt-Svc`). Il reste juste à **ouvrir UDP 443** sur votre pare-feu :

```bash
# UFW
sudo ufw allow 443/udp
sudo ufw reload

# OU iptables
sudo iptables -I INPUT -p udp --dport 443 -j ACCEPT
```

#### Tester HTTP/3 depuis le serveur

⚠️ Le `curl` fourni par Ubuntu/Debian est **compilé sans HTTP/3** :

```
curl: option --http3-only: the installed libcurl version doesn't support this
```

`install.sh` installe automatiquement une version récente de `curl` via snap et expose 2 raccourcis :

| Commande | Effet |
|---|---|
| `curl3 --http3-only -sI https://...` | Toujours dispo (binaire snap, symlink dans `/usr/local/bin/`) |
| `curl --http3-only -sI https://...` | Dispo dans un **nouveau shell root** (alias dans `/etc/profile.d/storm-monitor-curl3.sh`) |

Vérifier que HTTP/3 répond :

```bash
# Méthode rapide (binaire snap, pas besoin de nouveau shell)
curl3 --http3-only -sI https://storm-monitor.quentin-astro.fr/ | head -3
# Doit afficher: HTTP/3 200

# Ou en ouvrant un nouveau shell SSH (alias chargé)
curl --http3-only -sI https://storm-monitor.quentin-astro.fr/ | head -3
```

> 💡 **Si le warning Snap apparaît** ("Caution: You are using the Snap version of curl..."), exécuter une fois `/snap/bin/curl.snap-acked` (déjà fait par `install.sh` à la première run).
>
> **Pour annuler** l'alias système : `sudo rm /etc/profile.d/storm-monitor-curl3.sh /usr/local/bin/curl3 && sudo snap remove curl`

Chrome/Firefox mettront automatiquement à niveau la connexion au deuxième chargement grâce au header `Alt-Svc`.

### Activer les webhooks Discord / Telegram — optionnel

L'app envoie automatiquement des alertes sur Discord ou Telegram pour 4 événements :
- **Orage en cours** (CAPE élevé détecté)
- **Impacts de foudre** (strikes dans le rayon de 20 km)
- **Orage en approche** (centroid qui se rapproche avec ETA)
- **Vigilance orange/rouge** sur le 65 (Hautes-Pyrénées)

Un cooldown de 15 min par type d'alerte évite le flood.

#### Configuration

Éditez `/var/www/storm-monitor/backend/.env` et remplissez selon vos besoins :

```env
# Discord (créer un webhook dans Paramètres du salon → Intégrations → Webhooks)
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123456/abc..."

# Telegram (parler à @BotFather pour créer un bot, puis @userinfobot pour votre chat_id)
TELEGRAM_BOT_TOKEN="7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxx"
TELEGRAM_CHAT_ID="-1001234567890"   # ou votre ID perso

# Facultatif
WEBHOOK_APP_URL="https://storm-monitor.quentin-astro.fr"
WEBHOOK_COOLDOWN_S="900"   # 15 min par défaut
```

Puis redémarrer le backend :

```bash
sudo systemctl restart storm-monitor
```

#### Tester les webhooks

```bash
# Récupérer un token d'auth (login)
TOKEN=$(curl -s -X POST https://storm-monitor.quentin-astro.fr/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@lourdes.fr","password":"storm123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

# Voir quels canaux sont actifs (sans secret)
curl https://storm-monitor.quentin-astro.fr/api/webhooks/status

# Envoyer un test (bypass cooldown)
curl -X POST https://storm-monitor.quentin-astro.fr/api/webhooks/test \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🔄 Mettre à jour la production (après chaque nouvelle feature)

### Option 1 — Recommandée (tout via `/opt/storm-monitor`)

```bash
cd /opt/storm-monitor
git pull origin Testing
sudo bash install.sh
```

Ou en une seule ligne :

```bash
cd /opt/storm-monitor && git pull origin Testing && sudo bash install.sh
```

Quand le script tourne en mode UPDATE, il va :
1. **Détecter** que `/var/www/storm-monitor` existe déjà → bascule automatiquement en mode UPDATE (pas de `rm -rf`)
2. **Stasher** les modifications locales éventuelles (fichiers générés, bidouilles)
3. **Fetch + pull** `origin/Testing` dans `/var/www/storm-monitor`
4. **Afficher la liste des commits** qui viennent d'être récupérés
5. **Restaurer** le stash (ou le garder dans `git stash list` si conflit)
6. **Rebuild** le frontend (`yarn install --frozen-lockfile && yarn build`)
7. **Reload** systemd + Nginx

> ⚠️ **Le fichier `/var/www/storm-monitor/backend/.env` n'est JAMAIS écrasé** sur update. Vos clés (JWT, VAPID, upload API key) restent stables.

### Option 2 — Zapper le `/opt/storm-monitor`

Si vous n'utilisez pas `/opt/storm-monitor` comme backup de travail, vous pouvez sauter la première étape :

```bash
cd /opt/storm-monitor
sudo bash install.sh
```

Le script ira quand même chercher la dernière version sur GitHub pour la copie `/var/www/storm-monitor`.

### Ce que vous verrez à l'écran sur un update

```
==> Storm Monitor — installation on ns3020148
    Domain  : storm-monitor.quentin-astro.fr
    Dir     : /var/www/storm-monitor
    Backend : 127.0.0.1:8003
    User    : root
==> Installing system packages...
==> Existing install detected at /var/www/storm-monitor — switching to UPDATE mode
    Current branch : Testing
    Current commit : c7be03c
==> Fetching latest from origin...
==> Pulling origin/Testing...
    Updated c7be03c → 43c6a32
    Changed files :
      - 43c6a32 Phase 18: Démos Pyrénées + Export MP4
      - 9f2d81a Phase 17: Mode Replay orages majeurs
==> Setting up backend...
==> Building frontend...
==> Writing Nginx vhost...
==> Writing systemd unit...
==> Done.
```

---

## ⚠️ Point d'attention — modifications locales

Si vous avez **modifié des fichiers en local** dans `/opt/storm-monitor` sans commit/push, le `git pull` peut générer un conflit.

Vérifiez toujours avant de pull :

```bash
cd /opt/storm-monitor
git status        # → doit afficher "nothing to commit, working tree clean"
git pull origin Testing
```

Pour `/var/www/storm-monitor`, le script gère les conflits automatiquement (stash auto + restore). En cas de conflit non résolvable, vos modifs sont conservées dans `git stash list` et vous pouvez les récupérer manuellement.

---

## 🔍 Commandes de diagnostic utiles

```bash
# État du service backend
sudo systemctl status storm-monitor

# Logs backend en temps réel
sudo journalctl -u storm-monitor -f
sudo tail -f /var/log/storm-monitor.err.log

# Logs Nginx
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Test de l'API backend local
curl http://127.0.0.1:8003/api/weather/current?lat=43.0951\&lon=-0.0434

# Test de la config Nginx
sudo nginx -t

# Vider le cache vidéos (libérer l'espace disque)
sudo rm -rf /var/www/storm-monitor/cache/videos/output/*.mp4
```

---

## 🗂️ Arborescence sur le serveur après install

```
/opt/storm-monitor/              # Votre copie de travail (git pull manuel)
│
/var/www/storm-monitor/          # Copie de déploiement (managée par install.sh)
├── backend/
│   ├── .env                     # Secrets (NE PAS committer, NE PAS écraser)
│   ├── venv/                    # Python virtualenv
│   ├── server.py
│   └── ...
├── frontend/
│   ├── build/                   # Bundle React production (servi par Nginx)
│   ├── .env                     # REACT_APP_BACKEND_URL=https://...
│   └── src/
├── cache/
│   └── videos/                  # Cache tuiles CARTO + MP4 générés (TTL 24h)
└── storm_data.json              # Uploads storm JSON local

/etc/nginx/
├── sites-available/storm-monitor.conf     # vhost
├── sites-enabled/storm-monitor.conf       # → symlink
├── snippets/storm-monitor-app.conf        # config snippet partagée
└── conf.d/00-default-catchall.conf        # anti vhost-bleed

/etc/systemd/system/storm-monitor.service  # unit systemd
/var/log/storm-monitor.{log,err.log}       # logs backend
```

---

## 🧠 Pense-bête rapide

| Je veux... | Commande |
|---|---|
| Récupérer les dernières features | `cd /opt/storm-monitor && git pull origin Testing && sudo bash install.sh` |
| Redémarrer juste le backend | `sudo systemctl restart storm-monitor` |
| Recharger juste Nginx | `sudo systemctl reload nginx` |
| Voir les dernières erreurs backend | `sudo journalctl -u storm-monitor -n 100` |
| Purger le cache des MP4 générés | `sudo rm -rf /var/www/storm-monitor/cache/videos/output/*.mp4` |
| Renouveler le certificat SSL | `sudo certbot renew` |
| Vérifier que tout tourne | `sudo systemctl status storm-monitor nginx mongod` |

---

## 🔗 URL importantes

- **App prod** : https://storm-monitor.quentin-astro.fr
- **Page Direct** : `/`
- **Carte Vigilance** : `/vigilance`
- **Mode Replay + MP4** : `/replay`
- **Historique** : `/historique`
- **API racine** : `/api/` (toutes les routes backend préfixées par `/api`)

---

## 🆘 En cas de problème

1. **Service ne démarre pas** : `sudo journalctl -u storm-monitor -n 200` → regarder la pile d'erreurs
2. **404 sur l'app** : vérifier le build frontend (`ls /var/www/storm-monitor/frontend/build/index.html`)
3. **502/503** : le backend est down, vérifier `systemctl status storm-monitor`
4. **Nginx refuse le reload** : `sudo nginx -t` pour voir l'erreur de syntaxe
5. **MP4 ne se génère pas** : vérifier `which ffmpeg` (doit retourner `/usr/bin/ffmpeg`) et les logs backend

En dernier recours, vous pouvez toujours repartir de zéro :

```bash
sudo rm -rf /var/www/storm-monitor
cd /opt/storm-monitor && sudo bash install.sh
```

Le script détectera l'absence de `/var/www/storm-monitor` et refera une install complète. Vos clés `.env` seront **régénérées** (donc les abonnements push existants seront invalidés — c'est le seul effet de bord à accepter).
