# Procédure FCM — Notifications natives Android sur le Kimsufi (PRODUCTION)

> ⚠️ IMPORTANT — LOGS : sur le Kimsufi, le service N'ÉCRIT PAS dans journald.
> L'unit systemd redirige tout vers des fichiers :
> ```
> tail -f /var/log/storm-monitor.err.log      # ← logs applicatifs (FCM, alertes…)
> tail -f /var/log/storm-monitor.log          # stdout
> ```
> `journalctl -u storm-monitor` ne montrera RIEN d'applicatif. Ne pas l'utiliser.

> ⚠️ CLÉ FIREBASE : `backend/firebase-admin.json` est volontairement ignoré par
> Git et exclu du rsync d'`upgrade.sh` (jamais de clé privée sur GitHub).
> Il doit être déposé À LA MAIN, une seule fois, sur le Kimsufi.
> Depuis la version courante, PAS BESOIN de restart après dépôt : le backend
> le détecte au prochain appel.

---

## Étape 1 — Déployer la dernière version du code

```bash
cd /opt/storm-monitor && bash upgrade.sh
```

(`upgrade.sh` force désormais `pip install` si le module `firebase_admin`
manque du venv.)

## Étape 2 — Diagnostic complet en UN curl (sans SSH, depuis n'importe où)

```bash
curl -s https://storm-monitor.quentin-astro.fr/api/push/status | python3 -m json.tool
```

Réponse type :

```json
{
  "fcm_available": false,
  "fcm": {
    "credentials_path": "/var/www/storm-monitor/backend/firebase-admin.json",
    "file_exists": false,
    "file_readable": false,
    "valid_json": false,
    "project_id": null,
    "sdk_installed": true,
    "sdk_version": "7.5.0",
    "initialized": false,
    "last_error": "fichier credentials absent"
  },
  "fcm_tokens": 1,
  "webpush_subscriptions": 0
}
```

`last_error` nomme le problème exact. Interprétation :

| `last_error` | Cause | Correctif |
|---|---|---|
| `fichier credentials absent` | Clé pas déposée / mauvais chemin ou nom | Étape 3 |
| `module python firebase_admin non installé (pip)` | venv incomplet | relancer `bash upgrade.sh` |
| `JSON invalide : ...` | Fichier corrompu (copier-coller raté) | re-télécharger la clé, re-scp |
| `fichier illisible (droits)` | chmod/chown trop restrictif | `chmod 600` + `chown root:root` |
| `champ private_key absent du JSON` | Mauvais fichier (ce n'est pas la clé admin) | Étape 3, bien prendre "Comptes de service" |
| `null` + `initialized: true` | ✅ Tout fonctionne | — |

## Étape 3 — Déposer la clé Firebase (si `file_exists: false`)

1. https://console.firebase.google.com → projet **storm-monitor** →
   ⚙️ Paramètres du projet → **Comptes de service** →
   **Générer une nouvelle clé privée** → fichier JSON téléchargé.
2. Depuis le PC :
   ```bash
   scp storm-monitor-firebase-adminsdk-*.json \
     root@storm-monitor.quentin-astro.fr:/var/www/storm-monitor/backend/firebase-admin.json
   ```
3. Sur le Kimsufi :
   ```bash
   chmod 600 /var/www/storm-monitor/backend/firebase-admin.json
   chown root:root /var/www/storm-monitor/backend/firebase-admin.json
   ```
4. Re-lancer le curl de l'étape 2 → `initialized: true` attendu
   (aucun restart nécessaire). Le log confirme :
   ```bash
   grep -i fcm /var/log/storm-monitor.err.log | tail -5
   # → "FCM initialisé (projet storm-monitor)"
   ```

## Étape 4 — APK et test sur le téléphone

1. Push de la branche `Version_With_Detector` → GitHub Actions compile →
   Releases → `android-vXX` → installer `storm-monitor-debug.apk`.
2. Dans l'appli : activer **Push serveur actif** (désactiver/réactiver si déjà
   actif, pour ré-envoyer le token). Le toast indique désormais si le serveur
   a bien FCM actif.
3. Vérifier côté serveur : le curl de l'étape 2 doit montrer `fcm_tokens ≥ 1`.
4. Se connecter dans l'appli → bouton **"Envoyer un test"** →
   notification native attendue + toast `Test envoyé (1/1 appareils)`.
   Le toast explique tout échec (FCM désactivé serveur / aucun appareil /
   0 délivrés).

## Dépannage — logs applicatifs

```bash
grep -i fcm /var/log/storm-monitor.err.log | tail -20
tail -30 /var/log/storm-monitor.err.log
```

Tokens en base :

```bash
mongosh --quiet --eval 'db.getSiblingDB("storm_lourdes").fcm_tokens.countDocuments({})'
```
