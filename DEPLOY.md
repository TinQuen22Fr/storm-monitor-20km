# Storm Monitoring — Déploiement sur Kimsufi / VPS

Guide opérationnel pour installer, mettre à jour la production sur un serveur Ubuntu/Debian.

**Repo** : https://github.com/TinQuen22Fr/storm-monitor-20km
**URL prod** : https://storm-monitor.quentin-astro.fr
**Branche prod (figée)** : `Version_With_Detector`

> Kimsufi (OVH) est déjà en session root par défaut — **aucune commande n'utilise `sudo`** dans ce guide.

---

## Architecture

Deux dossiers, deux rôles **strictement séparés** :

| Dossier | Rôle | Modifié par |
|---|---|---|
| `/opt/storm-monitor` | **WORK_DIR** — clone git, source de vérité pour `git pull`. Aucun runtime ici. | Vous, à la main (`git`) |
| `/var/www/storm-monitor` | **APP_DIR** — runtime servi par Nginx + systemd. Contient `venv/`, `frontend/build/`, `backend/.env`, `cache/`, `storm_data.json`. | Les scripts `install.sh` / `upgrade.sh` (via `rsync`) |

Le script `install.sh` fait `git pull` dans `/opt`, puis `rsync` vers `/var/www` en **excluant** les fichiers runtime :
`.env`, `.env.backups/`, `venv/`, `storm_data.json`, `cache/`, `frontend/build/`, `frontend/node_modules/`, `frontend/.env`.

Conséquence : **vos secrets, votre venv Python, votre build front, vos données — rien n'est jamais écrasé par une mise à jour.**

---

## Branches Git

Le repo a deux branches d'usage **strictement séparé**. **Le choix se fait au moment du `git clone` initial** : la branche que tu clones définit la version que tu auras, et tu y restes.

| Branche | Pour qui | Contient |
|---|---|---|
| `Testing` | Quiconque veut la web app sans matériel | Carte, alertes, vigilance, replay. **Pas** de firmware, **pas** de route `/api/upload_storm`, **pas** de page `/detector`. Scripts d'install figés sur `Testing`. |
| `Version_With_Detector` | Moi (Kimsufi prod) avec détecteur AS3935 | Tout `Testing` **PLUS** : route `/api/upload_storm`, page `/detector`, autotune wizard, dossier `hardware/` (sketches Arduino). Scripts d'install figés sur `Version_With_Detector`. |

> Le firmware Arduino dans `hardware/` est temporairement cohabité dans le repo principal. À terme il sera extrait dans un repo dédié (`storm-monitor-firmware`). En attendant il est **uniquement présent sur `Version_With_Detector`**.

**Principe** : chaque branche est **autonome**.
- Si tu clones `Testing` → tu installes la version sans détecteur, point. Ses scripts `install.sh`/`upgrade.sh` resteront sur `Testing`.
- Si tu clones `Version_With_Detector` → tu installes la version avec détecteur, point. Ses scripts resteront sur `Version_With_Detector`.

Pas de bascule à chaud entre les deux via une variable d'env : c'est la branche que tu as clonée qui décide. Si un jour tu veux changer de version, tu repars d'un clone propre sur l'autre branche.

```bash
# Vérifier sur quelle branche tu es actuellement
git -C /opt/storm-monitor rev-parse --abbrev-ref HEAD
```

---

## A) Installation propre (serveur vierge)

**Pré-requis** : Ubuntu 22.04 / 24.04 ou Debian 12, accès root SSH, nom de domaine pointant vers le serveur.

```bash
# 1. Cloner le repo dans /opt (WORK_DIR)
mkdir -p /opt
git clone -b Version_With_Detector \
  https://github.com/TinQuen22Fr/storm-monitor-20km.git \
  /opt/storm-monitor

# 2. Lancer l'install (clone -> rsync -> venv -> build -> nginx -> systemd)
cd /opt/storm-monitor
bash install.sh
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
nano /var/www/storm-monitor/backend/.env
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
systemctl restart storm-monitor
```

### Activer HTTPS (Certbot)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d storm-monitor.quentin-astro.fr
```

Au prochain `bash install.sh`, le vhost HTTPS + HTTP/3 sera écrit automatiquement (le script détecte la présence des certs).

### Activer HTTP/3 (QUIC)

```bash
ufw allow 443/udp && ufw reload
# ou
iptables -I INPUT -p udp --dport 443 -j ACCEPT
```

Vérification :

```bash
curl3 --http3-only -sI https://storm-monitor.quentin-astro.fr/ | head -3
# attendu: HTTP/3 200
```

---

## B) Mise à jour d'une install existante

**Mode rapide (recommandé pour les déploiements routiniers)** :

```bash
cd /opt/storm-monitor && git pull && bash upgrade.sh
```

`upgrade.sh` ne touche **que** au code applicatif. Il prend ~30 s à 2 min selon ce qui a changé. Concrètement il :

1. `git pull` (re-pull pour confirmer le HEAD) dans `/opt/storm-monitor`. La branche `Version_With_Detector` est forcée par le script.
2. **Backup auto du `.env`** dans `/var/www/storm-monitor/backend/.env.backups/.env.YYYYMMDDTHHMMSSZ` (rotation : 10 derniers).
3. Détecte quels fichiers ont changé via `git diff` entre l'ancien et le nouveau HEAD.
4. `rsync` synchronise `/opt` → `/var/www` en préservant runtime (`.env`, `venv/`, `cache/`, `storm_data.json`, `build/`, `node_modules/`).
5. **`pip install`** **seulement si** `backend/requirements.txt` a changé.
6. **`yarn install`** **seulement si** `frontend/package.json` ou `frontend/yarn.lock` a changé.
7. **`yarn build`** **seulement si** un fichier de `frontend/` a changé.
8. `systemctl restart storm-monitor` (toujours, pour recharger les modules Python).
9. `nginx reload` **seulement si** un fichier de config Nginx a changé.

À utiliser **dans 95% des cas**.

**Mode complet (réinstall système)** :

```bash
cd /opt/storm-monitor && git pull && bash install.sh
```

`install.sh` refait tout : installe les paquets apt (Python, Node, MongoDB, Nginx, ffmpeg, snap…), régénère le vhost Nginx, l'unit systemd, le `.env` (si absent), build le frontend, etc. À utiliser :
- Après une migration de serveur
- Si tu as bidouillé Nginx / systemd à la main et veux les remettre d'aplomb
- Si `install.sh` lui-même a changé dans la release

**Comparaison rapide** :

| Étape | `upgrade.sh` | `install.sh` |
|---|---|---|
| `apt install` paquets système | non | oui |
| `git pull` + `rsync` | oui | oui |
| Backup `.env` | oui | oui |
| `pip install` | si requirements changé | toujours |
| `yarn install` + build | si package.json/frontend changé | toujours |
| Régénérer vhost Nginx | non | oui |
| Régénérer unit systemd | non | oui |
| Restart backend | oui | oui |
| Durée typique | 30 s — 2 min | 5 — 15 min |

> Le `.env` n'est jamais écrasé. Les nouveaux champs sont ajoutés vides à la fin **uniquement par `install.sh`**. `upgrade.sh` ne touche pas du tout au contenu du `.env` (il fait juste un backup avant chaque sync).

### Restaurer un `.env` depuis un backup

```bash
ls -lt /var/www/storm-monitor/backend/.env.backups/
cp /var/www/storm-monitor/backend/.env.backups/.env.YYYYMMDDTHHMMSSZ \
   /var/www/storm-monitor/backend/.env
systemctl restart storm-monitor
```

### Vérifier sur quelle branche/commit tourne la prod

```bash
git -C /opt/storm-monitor rev-parse --abbrev-ref HEAD   # → Version_With_Detector
git -C /opt/storm-monitor rev-parse --short HEAD
```

> Note : `/var/www/storm-monitor` n'a **pas** de `.git/` (exclu du rsync). La seule source de vérité branche/commit est `/opt/storm-monitor`.

---

## Diagnostic

```bash
# Service backend
systemctl status storm-monitor
journalctl -u storm-monitor -f
tail -f /var/log/storm-monitor.err.log

# Nginx
nginx -t
tail -f /var/log/nginx/error.log

# MongoDB
systemctl status mongod

# Test API local
curl http://127.0.0.1:8003/api/health
curl 'http://127.0.0.1:8003/api/weather/current?lat=43.0951&lon=-0.0434'
curl 'http://127.0.0.1:8003/api/weather/severe?lat=43.0951&lon=-0.0434&hours=48'
```

---

## En cas de problème

| Symptôme | Action |
|---|---|
| `storm-monitor.service` en boucle de crash | `journalctl -u storm-monitor -n 200` → lire la stack. Souvent : variable `.env` manquante ou venv corrompu. |
| 502 Bad Gateway | Backend down → `systemctl restart storm-monitor`. |
| 404 sur l'app | Build front absent → `cd /var/www/storm-monitor/frontend && yarn build`. |
| Nginx reload échoue | `nginx -t` pour voir l'erreur de syntaxe. |
| `.env` corrompu / mal édité | Restaurer un backup (voir section B). |
| Update a cassé un truc | `cd /opt/storm-monitor && git log --oneline -10`, `git checkout <commit_précédent>`, `bash install.sh`. |

### Reset complet (dernier recours)

```bash
systemctl stop storm-monitor
rm -rf /var/www/storm-monitor
cd /opt/storm-monitor && bash install.sh
```

⚠️ Régénère les secrets `.env` (JWT, VAPID, UPLOAD_API_KEY). Les abonnements push existants deviendront invalides. **Pensez à `cp /var/www/storm-monitor/backend/.env ~/env.save` avant** si vous voulez les conserver.

---

## Pourquoi des dizaines de warnings au `yarn install` ?

Court résumé : **react-scripts (Create React App) est en mode maintenance depuis 2023**. Il embarque des versions figées de :

- `eslint@8.57.1` (l'équipe ESLint a marqué la branche 8 comme non supportée)
- `workbox-*@6.6.1` (toute la famille marquée deprecated)
- `glob@7.2.3`, `rimraf@3.0.2` (versions pré-v4)
- `@babel/plugin-proposal-*` (renommés en `plugin-transform-*` côté Babel)
- `abab`, `svgo@1.x`, `q`, `stable`, `sourcemap-codec`…

Ces packages **fonctionnent toujours** mais ne reçoivent plus de mises à jour. Tant que tu restes sur CRA, ils sont **scellés** dans `react-scripts@5.0.1`. Yarn affiche le warning par hygiène, c'est tout.

### Ce qui a déjà été fait (cosmétique)

1. **Bloc `resolutions` dans `frontend/package.json`** — force les versions corrigeant des CVE sur les sous-dépendances safe :
   - `nth-check@^2.1.1` · `postcss@^8.4.49` · `cookie@^0.7.2`
   - `semver@^7.6.3` · `serialize-javascript@^6.0.2`

   Aucune de ces résolutions ne casse CRA, elles font juste taire les outils d'audit type `npm audit`/`yarn audit`.

2. **Filtre dans `install.sh`** — les lignes `warning …` sont archivées dans `/var/log/storm-monitor-yarn-install.log` au lieu d'inonder le terminal. Le récap final affiche juste `[yarn] N warnings cosmétiques filtrés`.

### Inspecter les warnings après installation

```bash
# Tous les warnings du dernier yarn install
tail -n 100 /var/log/storm-monitor-yarn-install.log | grep '^warning'

# Compter par catégorie
grep '^warning' /var/log/storm-monitor-yarn-install.log | sort | uniq -c | sort -rn | head -20
```

---

## Arborescence cible

```
/opt/storm-monitor/                  # WORK_DIR (git, jamais de runtime ici)
├── .git/
├── backend/
├── frontend/
├── hardware/                        # firmware AS3935 (Version_With_Detector)
├── install.sh
└── upgrade.sh

/var/www/storm-monitor/              # APP_DIR (runtime, géré par les scripts)
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
| **Déployer la dernière version (rapide)** | `cd /opt/storm-monitor && git pull && bash upgrade.sh` |
| Réinstall complète (système) | `cd /opt/storm-monitor && git pull && bash install.sh` |
| Redémarrer le backend | `systemctl restart storm-monitor` |
| Recharger Nginx | `systemctl reload nginx` |
| Voir les 100 dernières lignes de logs | `journalctl -u storm-monitor -n 100` |
| Renouveler le certif SSL | `certbot renew` |
| Lister les backups `.env` | `ls -lt /var/www/storm-monitor/backend/.env.backups/` |
| Vérifier branche en prod | `git -C /opt/storm-monitor rev-parse --abbrev-ref HEAD` |
