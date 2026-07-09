# 📱 Storm Monitor — Application Android

L'application Android embarque le frontend React directement dans l'APK (via **Capacitor**).
Au lancement, l'app s'ouvre instantanément et récupère uniquement les données météo/foudre
depuis le serveur Kimsufi : `https://storm-monitor.quentin-astro.fr`.

---

## ⚙️ Compilation automatique (GitHub Actions)

Le workflow `.github/workflows/android-build.yml` compile automatiquement l'APK :

- **À chaque push** sur `Version_With_Detector` ou `main` touchant `frontend/`
- **Manuellement** : onglet **Actions** → *Build Android APK* → **Run workflow**

### Récupérer l'APK

**📲 Méthode simple (fonctionne sur mobile)** — via les Releases :

1. GitHub → onglet **Releases** (ou `https://github.com/<ton-repo>/releases`)
2. Chaque build crée une **nouvelle release** « 📱 Storm Monitor v1.0.N » (N = numéro de build, la plus récente est marquée *Latest*)
3. Télécharger directement `storm-monitor-debug.apk` → l'ouvrir → installer par-dessus l'ancienne version

**💻 Méthode alternative (navigateur desktop uniquement)** — via les Artifacts :

1. Aller sur GitHub → onglet **Actions**
2. Cliquer sur le dernier run *Build Android APK* (vert ✅)
3. En bas de page, section **Artifacts** :
   - `storm-monitor-debug` → APK debug, installable directement
   - `storm-monitor-release` → APK signé (seulement si le keystore est configuré, voir plus bas)
4. Télécharger le zip, extraire le `.apk`, le transférer sur le téléphone

> ⚠️ L'app GitHub mobile ne permet PAS de télécharger les artifacts — utiliser les Releases.

### Installer sur le téléphone

1. Ouvrir le fichier `.apk` sur le téléphone
2. Android demande d'autoriser les **sources inconnues** → accepter (une seule fois)
3. L'app **Storm Monitor** apparaît avec son icône éclair ⚡

> ℹ️ L'APK **debug** suffit largement pour un usage personnel.
> L'APK **release** signé sert surtout si tu veux distribuer l'app ou éviter
> la réinstallation forcée à chaque mise à jour.

---

## 🔐 APK Release signé (optionnel)

Pour activer la compilation de l'APK release signé, créer un keystore **une seule fois** :

```bash
keytool -genkey -v -keystore storm-monitor.keystore \
  -alias storm-monitor -keyalg RSA -keysize 2048 -validity 10000
```

Puis l'encoder en base64 :

```bash
base64 -w 0 storm-monitor.keystore
```

Ajouter ensuite **4 secrets** sur GitHub (repo → Settings → Secrets and variables → Actions) :

| Secret              | Valeur                                    |
|---------------------|-------------------------------------------|
| `KEYSTORE_BASE64`   | La sortie de la commande `base64` ci-dessus |
| `KEYSTORE_PASSWORD` | Mot de passe du keystore                  |
| `KEY_ALIAS`         | `storm-monitor`                           |
| `KEY_PASSWORD`      | Mot de passe de la clé (souvent identique) |

Au prochain run, l'artifact `storm-monitor-release` sera généré automatiquement.
⚠️ **Conserver précieusement le fichier keystore** : il faut le même pour toutes
les mises à jour futures de l'app signée.

---

## 🌐 Serveur Kimsufi — point d'attention CORS

L'app Android tourne sous l'origine `https://localhost` (webview Capacitor).
Le backend accepte tout par défaut (`CORS_ORIGINS=*`), donc **rien à faire**.

⚠️ Si un jour tu restreins `CORS_ORIGINS` dans le `.env` du backend Kimsufi,
il faudra y ajouter l'origine Capacitor :

```
CORS_ORIGINS=https://storm-monitor.quentin-astro.fr,https://localhost
```

---

## 🔄 Mettre à jour l'app

1. Pousser les modifications du frontend sur GitHub (bouton *Save to GitHub*)
2. Le workflow recompile l'APK automatiquement
3. Télécharger et réinstaller le nouvel APK sur le téléphone

Pour changer le numéro de version affiché : éditer `versionCode` (entier, +1 à chaque fois)
et `versionName` (ex: `"1.1"`) dans `frontend/android/app/build.gradle`.

---

## 🎨 Changer l'icône de l'app

Les icônes sont dans `frontend/android/app/src/main/res/mipmap-*/`.
Fournir une image carrée (idéalement 1024×1024) et régénérer les tailles :
`ic_launcher.png` (48/72/96/144/192 px), `ic_launcher_round.png` (mêmes tailles, ronde)
et `ic_launcher_foreground.png` (108/162/216/324/432 px, icône centrée à ~62%).

---

## 🛠️ Structure technique

```
frontend/
├── capacitor.config.json   # Config Capacitor (appId, nom, webDir)
├── android/                # Projet Android natif généré (committé)
│   └── app/build.gradle    # versionCode / versionName / signature
└── build/                  # Build React (généré par le CI, non committé)
```

- **Capacitor 7** (compatible Node 20+, Java 21, Gradle 8)
- Le CI build le React avec `REACT_APP_BACKEND_URL=https://storm-monitor.quentin-astro.fr`
  puis `npx cap sync android` copie le build dans l'APK.
