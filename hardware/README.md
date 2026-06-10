# Hardware — Détecteur d'orage AS3935

Sketches Arduino pour le module **Franklin AS3935 Lightning Detector** intégré
à l'application **Storm Monitor · Lourdes**. Les données détectées sont
transmises au backend FastAPI via `POST /api/upload_storm` et affichées en
temps réel sur la page `/detector` de l'application.

> ⚠️ Branche cible GitHub : `Version_With_Detector` — ne pas pousser sur `Testing`.

## Structure

```
hardware/
├── Arduino_StormDetector.ino          # Sketch principal — communication I2C
├── Arduino_StormDetector_SPI.ino      # Sketch principal — communication SPI
└── Tune_Antenna/
    ├── README.md                      # Comment accorder l'antenne (FR)
    ├── Example3_Tune_Antenna_I2C.ino  # Sketch de tuning (I2C)
    └── Example3_Tune_Antenna_SPI.ino  # Sketch de tuning (SPI)
```

## Quelle variante choisir ?

| Critère | **I2C** | **SPI** |
|---|---|---|
| Câblage | 2 fils (SDA/SCL) | 4 fils (MOSI/MISO/SCK/CS) |
| Bus partagé | Avec autres capteurs I2C | Avec Ethernet Shield |
| Robustesse en présence de parasites | Moyenne | **Meilleure** (full-duplex) |
| Recommandation par défaut | OK pour banc d'essai | **Recommandé** en installation finale |

Choisis la version **SPI** si tu observes des freezes du bus I2C au moment où
le détecteur signale un impact (le capteur monopolise alors le bus pendant la
lecture des registres).

## Configuration commune (les deux sketches)

Modifie en haut du fichier `.ino` :

```c++
const char SERVER_HOST[] = "storm.ton-domaine.fr"; // domaine public du Kimsufi
const int  SERVER_PORT   = 8080;                   // port HTTP non chiffré dédié
const char API_KEY[]     = "...";                  // = UPLOAD_API_KEY côté backend/.env
const char DEVICE_ID[]   = "as3935-lourdes-01";
```

La clé `API_KEY` doit correspondre **exactement** à `UPLOAD_API_KEY` dans
`/app/backend/.env` côté serveur, sinon le backend renvoie `401`.

### Accès au Kimsufi depuis l'Internet (datacenter Roubaix)

L'Arduino Uno + Ethernet Shield ne fait **pas** de HTTPS/TLS. Comme le Kimsufi
est en datacenter (pas en LAN local), il faut une des stratégies suivantes :

| Option | Avantages | Inconvénients |
|---|---|---|
| **1. Port HTTP dédié** (ex: `:8080`) ouvert sur le pare-feu Kimsufi, Nginx redirige vers `127.0.0.1:8003` | Simple, marche tout de suite | Trafic en clair (API_KEY visible en sniff passif) |
| **2. VPN Tailscale/WireGuard** : un petit routeur OpenWRT ou mini-PC chez toi rejoint le réseau Tailscale, le Kimsufi est joignable via une IP `100.x.y.z` | Chiffrement bout en bout, le Kimsufi reste fermé sur Internet | Setup VPN à monter côté maison |
| **3. Upgrade hardware** : remplacer Uno+Ethernet par ESP32 ou MKR1010 | HTTPS natif, le plus propre à terme | Coût matériel + refonte sketch |

**Recommandé pour démarrer** : Option 1 + clé API longue et changée régulièrement.
Exemple de bloc Nginx à ajouter sur le Kimsufi (HTTP plaintext sur 8080,
uniquement pour `/api/upload_storm`) :

```nginx
server {
    listen 8080;
    server_name storm.ton-domaine.fr;
    # Permet uniquement l'upload du détecteur (lecture, push, etc. restent en HTTPS:443)
    location = /api/upload_storm {
        proxy_pass http://127.0.0.1:8003;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
    location / { return 404; }
}
```

Puis ouvre le port 8080 sur le firewall Kimsufi (`ufw allow 8080/tcp`).

## Bibliothèques Arduino requises

À installer via **Outils > Gérer les bibliothèques** dans l'IDE Arduino :
- `SparkFun_AS3935_Lightning_Detector_Arduino_Library`
- `Ethernet` (officielle Arduino)
- `ArduinoJson` v6+ (par Benoit Blanchon)
- `SPI` et `Wire` (incluses Arduino)

## Câblage rapide

### I2C (Arduino Uno + Ethernet Shield)

```
AS3935  →  Arduino Uno
  VCC   →  5V   (recommandé sur module SparkFun — LDO embarqué, plus stable
                 que le 3V3 Arduino qui plafonne à 50 mA)
  GND   →  GND
  SDA   →  A4
  SCL   →  A5
  IRQ   →  D4
```

### SPI (Arduino Uno + Ethernet Shield)

```
AS3935  →  Arduino Uno
  VCC   →  5V   (idem ci-dessus, module SparkFun avec LDO 3V3 embarqué)
  GND   →  GND
  MOSI  →  D11 (SPI partagé)
  MISO  →  D12 (SPI partagé)
  SCK   →  D13 (SPI partagé)
  CS    →  D6  (Chip Select DÉDIÉ — ne PAS prendre D10 = Ethernet)
  IRQ   →  D4
  SI    →  GND (force le mode SPI)
```

### LEDs (communes I2C + SPI)

```
LED Bleue (foudre détectée)     →  D8 + résistance 220 Ω → GND
LED Verte (upload OK)           →  D7 + résistance 220 Ω → GND
LED Rouge (upload KO ou erreur) →  D9 + résistance 220 Ω → GND
```

## Avant le premier flash : accorder l'antenne

Avant d'utiliser le sketch principal, accorde la fréquence de résonance de
l'antenne avec les sketches dans `Tune_Antenna/`. La procédure complète est
détaillée dans **[Tune_Antenna/README.md](./Tune_Antenna/README.md)**.

En résumé :
1. Flasher `Example3_Tune_Antenna_I2C.ino` (ou SPI)
2. Mesurer la fréquence sur la broche **D4 (IRQ)** avec oscilloscope/analyseur logique
3. Ajuster `lightning.tuneCap(N)` jusqu'à atteindre ~31,25 kHz (= 500 kHz / 16)
4. Reporter la valeur trouvée dans le sketch principal et reflasher

## Vérification post-déploiement

Une fois le détecteur en service, ouvre la page `/detector` de l'application :
- Le bandeau doit afficher **DÉTECTEUR EN LIGNE** (vert)
- Un heartbeat est remonté toutes les 5 minutes
- À chaque impact, la LED bleue clignote sur l'Arduino + une ligne **Foudre**
  apparaît dans le flux récent

Tu peux aussi tester manuellement avec curl :

```bash
curl -X POST https://<ton-domaine>/api/upload_storm \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <UPLOAD_API_KEY>" \
  -d '{"kind":"lightning","distance":4.2,"energy":51.3,"device_id":"as3935-lourdes-01"}'
```

---
*Build & Idea by Quentin Dumont — Storm Monitor · Lourdes*
