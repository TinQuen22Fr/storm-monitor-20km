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
const char SERVER_HOST[] = "192.168.1.10";  // IP LAN du serveur Kimsufi
const int  SERVER_PORT   = 8003;            // port FastAPI backend
const char API_KEY[]     = "...";           // = UPLOAD_API_KEY côté backend/.env
const char DEVICE_ID[]   = "as3935-lourdes-01";
```

La clé `API_KEY` doit correspondre **exactement** à `UPLOAD_API_KEY` dans
`/app/backend/.env` côté serveur, sinon le backend renvoie `401`.

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
  VCC   →  3V3              (NE PAS mettre en 5V)
  GND   →  GND
  SDA   →  A4
  SCL   →  A5
  IRQ   →  D4
```

### SPI (Arduino Uno + Ethernet Shield)

```
AS3935  →  Arduino Uno
  VCC   →  3V3
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
