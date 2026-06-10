# Tune_Antenna — Accordage de l'antenne AS3935

> Si tu cherches à accorder la fréquence d'antenne du SparkFun Lightning
> Detector, regarde l'**Example 3 — Tune Antenna SPI** (ou son équivalent I2C)
> inclus dans la bibliothèque SparkFun Lightning Detector. Il te faut un moyen
> de lire un signal carré d'au moins **4 kHz** : un **oscilloscope** ou un
> **analyseur logique**.
>
> Comme bon point de départ, on observe que la fréquence de résonance des
> cartes fabriquées par SparkFun démarre autour de **~496 kHz**. La datasheet
> spécifie que la fréquence de résonance doit être à **±3,5 %** de **500 kHz**
> pour une détection de foudre optimale. Les cartes SparkFun sortent d'usine
> à **moins de 1 %** de cette valeur.

*(Adaptation française du texte officiel SparkFun.)*

---

## Pourquoi accorder l'antenne ?

Le module AS3935 utilise une antenne LC (bobine + capacités) accordée à
**500 kHz** pour capter les transitoires radio générés par les éclairs. Si la
fréquence de résonance dérive (vieillissement, proximité d'un objet métallique,
boîtier, etc.), la sensibilité chute et tu rates des impacts.

Les cartes SparkFun sont déjà à <1 % d'écart vs 500 kHz. Le tuning n'est
**utile** que si tu observes :
- Beaucoup de **noise interrupts** alors que l'environnement est calme
- Aucune détection alors qu'un orage est confirmé par Blitzortung à proximité
- Une carte « cliché » ou stockée longtemps dans un environnement humide

## Matériel nécessaire

- L'un de ces outils de mesure :
  - **Oscilloscope** (idéalement ≥ 5 MHz de bande passante)
  - **Analyseur logique** (Saleae, DSLogic, etc. — taux d'échantillonnage ≥ 1 MS/s)
  - À défaut, un **multimètre avec mode fréquence** peut donner une lecture grossière (~31 kHz)
- L'AS3935 câblé selon ton mode de communication (I2C ou SPI)
- Une sonde sur la broche **IRQ** du capteur (D4 par défaut sur Uno)

## Où brancher la sonde de mesure ?

La fréquence à mesurer sort sur la **broche IRQ du capteur AS3935**, qui est
reliée à la broche **D4 de l'Arduino**. C'est **le même fil** vu de deux côtés.
Tu peux donc piquer la sonde n'importe où sur ce fil.

⚠️ **Important** : ta masse de mesure (pince crocodile noire de l'oscilloscope
ou GND de l'analyseur logique) doit être **commune avec la masse de l'Arduino**.
Sinon les mesures seront flottantes ou ramèneront du bruit secteur.

### Schéma — variante I2C

```
                  ┌──────────────────────────────┐
                  │       Arduino Uno            │
                  │                              │
                  │   5V ●──────────┐            │
                  │  3V3 ●          │            │
                  │  GND ●──────┐   │            │
                  │             │   │            │
                  │   D4 ●──────┼───┼────────┐   │  ← piquer la sonde "+"
                  │       │ │   │   │        │   │     ici (au plus près
                  │   A4 ●┼─┼───┼───┼──────┐ │   │     du connecteur D4)
                  │   A5 ●┼─┼───┼───┼─────┐│ │   │
                  └───────┼─┼───┼───┼─────┼┼─┼───┘
                          │ │   │   │     ││ │
                          │ │   │   │     ││ │       ┌────────────┐
                          │ │   └───┼─────┼┼─┼───── ●│ VCC        │
                          │ │       │     ││ │       │            │
                          │ └───────┘     ││ └─────●│ IRQ  AS3935 │
                          │               │└──────●│ SDA          │
                          │               └───────●│ SCL          │
                          └───────────────────────●│ GND          │
                                                   └────────────┘
                                                          │
                                                          │
            ┌─────────────────┐                           │
            │  OSCILLOSCOPE   │                           │
            │   ou ANALYSEUR  │                           │
            │     LOGIQUE     │                           │
            │                 │                           │
            │  CH1 +   ●──────┴──── sur D4 (= IRQ AS3935)
            │  CH1 GND ●─────────── sur GND (Arduino ou capteur, même fil)
            └─────────────────┘
```

### Schéma — variante SPI

```
                  ┌──────────────────────────────┐
                  │       Arduino Uno            │
                  │                              │
                  │   5V ●──────────┐            │
                  │  GND ●─────┐    │            │
                  │            │    │            │
                  │   D4 ●─────┼────┼────────┐   │  ← piquer la sonde "+"
                  │   D6 ●─────┼────┼───────┐│   │     ici (D4 = IRQ)
                  │  D11 ●─────┼────┼──────┐││   │
                  │  D12 ●─────┼────┼─────┐│││   │
                  │  D13 ●─────┼────┼────┐││││   │
                  └────────────┼────┼────┼┼┼┼┼───┘
                               │    │    │││││
                               │    │    │││││           ┌────────────┐
                               │    └────┼┼┼┼┼─────────●│ VCC        │
                               │         ││││└─────────●│ IRQ        │
                               │         │││└──────────●│ CS         │
                               │         ││└───────────●│ MOSI AS3935│
                               │         │└────────────●│ MISO       │
                               │         └─────────────●│ SCK        │
                               └───────────────────────●│ GND        │
                                                       │ SI ─── GND  │
                                                       └────────────┘
                                                              │
            ┌─────────────────┐                               │
            │  OSCILLOSCOPE   │                               │
            │   ou ANALYSEUR  │                               │
            │     LOGIQUE     │                               │
            │                 │                               │
            │  CH1 +   ●──────┴──────── sur D4 (= IRQ AS3935)
            │  CH1 GND ●──────────────── sur GND
            └─────────────────┘
```

### Réglages oscilloscope recommandés

| Paramètre              | Valeur conseillée                |
|------------------------|----------------------------------|
| Couplage               | DC                               |
| Échelle verticale      | 1 V/div (signal logique 0–3,3 V) |
| Base de temps          | 10 µs/div (pour voir ~3 périodes du signal à 31 kHz) |
| Trigger                | Rising edge, niveau 1,6 V        |
| Sonde                  | ×1 (ou ×10 si signal trop fort)  |

### Réglages analyseur logique recommandés

| Paramètre              | Valeur conseillée                |
|------------------------|----------------------------------|
| Échantillonnage        | ≥ 1 MS/s (10× le signal à 31 kHz) |
| Durée capture          | 10 ms (= 310 périodes à 31 kHz) suffisant pour mesurer la fréquence avec précision |
| Trigger                | Front montant sur le canal D4    |

## Comment ça marche

Le sketch active une fonction interne du AS3935 qui **route l'oscillateur de
l'antenne sur la broche IRQ** sous forme d'un signal carré. Cette fréquence
est :

```
f_IRQ = f_antenne / division_ratio
```

Où `division_ratio` vaut **16** par défaut (configurable à 32/64/128 via
`changeDivRatio()`).

Avec une antenne idéalement accordée à 500 kHz et div=16, tu dois mesurer
**31,25 kHz** sur IRQ. Sur les cartes SparkFun typiques : ~31,04 kHz
(≈ 496,6 kHz × 1/16).

## Procédure pas à pas

1. **Choisir le sketch** selon ton câblage :
   - I2C → `Example3_Tune_Antenna_I2C.ino`
   - SPI → `Example3_Tune_Antenna_SPI.ino`
2. **Flasher** sur ton Arduino Uno (Ethernet Shield débranché de préférence,
   pour éviter tout parasite SPI/I2C parasite pendant la mesure).
3. **Ouvrir le moniteur série** à **115200 bauds** — tu dois voir :
   ```
   AS3935 Franklin Lightning Detector — Tune Antenna (I2C|SPI)
   [OK] Prêt à tuner l'antenne.
   Division Ratio : 16
   Capacité interne  : 0 pF
   ---- Sortie de l'oscillateur sur la broche IRQ ----
   ```
4. **Brancher la sonde** de ton oscilloscope/analyseur logique sur la broche
   **IRQ (D4)** + masse commune avec l'Arduino.
5. **Lire la fréquence** mesurée. Multiplie par `division_ratio` (16 par défaut)
   pour obtenir la fréquence réelle d'antenne.
6. **Calculer l'écart** vs 500 kHz :
   ```
   écart (%) = |f_antenne - 500000| / 500000 × 100
   ```
   - Si **écart < 3,5 %** → c'est dans la plage optimale, ne rien faire.
   - Si **écart ≥ 3,5 %** → ajuster la capacité interne (étape 7).
7. **Ajuster la capacité interne** (dé-commenter dans le sketch et reflasher) :
   ```c++
   lightning.tuneCap(N);   // N entre 0 et 15 ; chaque pas = 8 pF
   ```
   - Si la fréquence mesurée est **trop haute** (> 500 kHz) → augmenter la
     capacité (essayer N=1, puis 2, etc.) pour faire **baisser** la fréquence.
   - Si **trop basse** (< 500 kHz) → la capacité est déjà au minimum (N=0),
     le module est probablement défectueux ou mal soudé.
   - Plage théorique : on peut faire baisser la fréquence jusqu'à -22 kHz
     environ avec 120 pF (N=15).
8. **Itérer** : reflasher, remesurer, ajuster, jusqu'à minimiser l'écart.
9. Une fois la **valeur optimale trouvée** (le `N` qui donne la mesure la plus
   proche de 31,25 kHz sur IRQ), reporter cette valeur dans le sketch
   principal `Arduino_StormDetector.ino` ou `Arduino_StormDetector_SPI.ino`
   en ajoutant juste après le `lightning.resetSettings()` :
   ```c++
   lightning.tuneCap(N);  // N = ta valeur optimale
   ```
10. Optionnel : **calibrer les oscillateurs internes** une fois l'antenne
    correctement accordée :
    ```c++
    lightning.calibrateOsc();
    ```

## Aide-mémoire des fréquences

| Mesure sur IRQ (div=16) | Fréquence d'antenne | Écart vs 500 kHz | Verdict       |
|------------------------:|--------------------:|-----------------:|---------------|
| 31,25 kHz               | 500,0 kHz           | 0,0 %            | Parfait       |
| 31,04 kHz               | 496,6 kHz           | 0,7 %            | Excellent     |
| 30,80 kHz               | 492,8 kHz           | 1,4 %            | Très bon      |
| 30,30 kHz               | 484,8 kHz           | 3,0 %            | Acceptable    |
| 30,16 kHz               | 482,5 kHz           | 3,5 %            | Limite haute  |
| < 30,16 kHz             | < 482,5 kHz         | > 3,5 %          | À ré-accorder |

## Conseils pratiques

- Faire le tuning **dans la position finale** du capteur (boîtier fermé,
  installé à son emplacement définitif) — déplacer l'antenne après tuning
  peut changer la fréquence de quelques pourcents.
- **Éloigner** l'antenne de tout objet métallique massif et des grosses
  alimentations à découpage (au moins 50 cm).
- Le tuning ne se fait **qu'une seule fois** par carte ; après, ça reste stable.
- Bien noter la valeur de `tuneCap` finale pour pouvoir la re-flasher après une
  mise à jour du firmware.

## Références

- Datasheet officielle AS3935 — page 35 (calibration de l'antenne)
- Tutoriel SparkFun : <https://learn.sparkfun.com/tutorials/sparkfun-as3935-lightning-detector-hookup-guide-v20>
- Lib Arduino : <https://github.com/sparkfun/SparkFun_AS3935_Lightning_Detector_Arduino_Library>

---
*Build & Idea by Quentin Dumont — Storm Monitor · Lourdes*
