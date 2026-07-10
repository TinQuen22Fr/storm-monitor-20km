# Procédure FCM — Notifications natives Android sur le Kimsufi (PRODUCTION)

> ⚠️ POINT CLÉ : le fichier `backend/firebase-admin.json` est volontairement
> ignoré par Git (`.gitignore` ligne 33) et exclu du rsync de `upgrade.sh`
> (sécurité : jamais de clé privée dans le dépôt GitHub).
> **Il n'arrive donc JAMAIS tout seul sur le Kimsufi.**
> Tant qu'il n'est pas déposé à la main dans `/var/www/storm-monitor/backend/`,
> le backend logge "FCM désactivé : credentials absents" et AUCUNE notification
> native Android ne peut partir. C'est l'unique étape manuelle, à faire UNE fois.

---

## Étape 0 — Diagnostic immédiat (30 s, sur le Kimsufi)

```bash
ls -l /var/www/storm-monitor/backend/firebase-admin.json
```

- `No such file or directory` → c'est bien ça le problème, continuez.
- Le fichier existe → passez directement à l'étape 3.

---

## Étape 1 — Récupérer la clé de service Firebase (sur votre PC)

1. Ouvrir https://console.firebase.google.com → projet **storm-monitor**
2. ⚙️ **Paramètres du projet** → onglet **Comptes de service**
3. Bouton **Générer une nouvelle clé privée** → un fichier
   `storm-monitor-firebase-adminsdk-xxxxx.json` est téléchargé.

---

## Étape 2 — Déposer la clé sur le Kimsufi (UNE seule fois)

Depuis votre PC (adapter le nom du fichier téléchargé) :

```bash
scp storm-monitor-firebase-adminsdk-*.json \
  root@storm-monitor.quentin-astro.fr:/var/www/storm-monitor/backend/firebase-admin.json
```

Puis sur le Kimsufi :

```bash
chmod 600 /var/www/storm-monitor/backend/firebase-admin.json
chown root:root /var/www/storm-monitor/backend/firebase-admin.json
```

> Le nom DOIT être exactement `firebase-admin.json` (ou définir
> `FIREBASE_CREDENTIALS=/chemin/vers/le/fichier.json` dans `backend/.env`).
> `upgrade.sh` ne touchera plus jamais à ce fichier (exclu du rsync).

---

## Étape 3 — Mettre à jour le code sur le Kimsufi

Le bouton "Envoyer un test" + les logs FCM détaillés sont dans la branche
`Version_With_Detector`. Sur le Kimsufi :

```bash
cd /opt/storm-monitor && bash upgrade.sh
```

---

## Étape 4 — Vérifier que FCM est actif (sur le Kimsufi)

```bash
systemctl restart storm-monitor
journalctl -u storm-monitor -n 80 --no-pager | grep -i fcm
```

Attendu :

```
FCM initialisé (projet storm-monitor)
FCM prêt · notifications Android natives activées
```

Si vous voyez `FCM désactivé : credentials absents` → le fichier de l'étape 2
n'est pas au bon endroit / mauvais nom.

---

## Étape 5 — Nouvelle APK (compilée automatiquement par GitHub)

1. Le push sur la branche `Version_With_Detector` déclenche le workflow
   **Build Android APK** (l'APK embarque déjà `google-services.json`,
   qui lui EST versionné — c'est normal, il ne contient pas de secret).
2. Sur le téléphone : GitHub → repo → **Releases** → dernière release
   `android-vXX` → télécharger `storm-monitor-debug.apk` → installer
   par-dessus l'ancienne version.

---

## Étape 6 — Test de bout en bout (sur le téléphone)

1. Ouvrir l'appli → se connecter → **activer les notifications push**
   (accepter la permission Android).
2. Sur le Kimsufi, vérifier l'enregistrement du téléphone :
   ```bash
   journalctl -u storm-monitor -n 50 --no-pager | grep "FCM token"
   ```
   Attendu : `FCM token enregistré (user_id=..., token=xxxx…)`
3. Dans l'appli, appuyer sur le bouton rouge **"Envoyer un test"**.
4. Attendu côté serveur :
   ```
   FCM envoi vers 1 appareils · titre='Test · Alerte orage'
   FCM résultat · envoyés=1 purgés=0 erreurs=0 total=1
   ```
5. Attendu côté téléphone : notification native
   **"Test · Alerte orage — Ceci est un test de notification push"**
   (fonctionne appli fermée / écran verrouillé).

---

## Dépannage rapide

| Symptôme (journalctl) | Cause | Correctif |
|---|---|---|
| `FCM désactivé : credentials absents` | `firebase-admin.json` absent sur le Kimsufi | Étapes 1–2 |
| `FCM init échoué : ...` | JSON corrompu / mauvais projet | Regénérer la clé (étape 1) |
| `FCM send_to_all : aucun token Android enregistré` | Le téléphone ne s'est pas abonné | Réactiver les notifs dans l'appli, vérifier `FCM token enregistré` |
| `envoyés=0 purgés=1` | Token expiré (APK réinstallée) | Désactiver puis réactiver les notifs dans l'appli |
| Rien ne s'affiche avec `grep FCM` | Ancien code encore en prod | `bash upgrade.sh` puis `systemctl restart storm-monitor` |

Vérifier les tokens enregistrés en base :

```bash
mongosh --quiet --eval 'db.getSiblingDB("storm_lourdes").fcm_tokens.countDocuments({})'
```
