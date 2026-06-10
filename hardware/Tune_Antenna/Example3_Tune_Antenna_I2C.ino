/*
================================================================================
 Example 3 — Tune Antenna (I2C)
================================================================================
 Source originale : SparkFun_AS3935_Lightning_Detector_Arduino_Library
 Auteur original  : Elias Santistevan, SparkFun Electronics — Avril 2019
 Licence          : Beerware (domaine public, offre-moi une bière si on se croise)

 Adapté & commenté en français pour le projet Storm Monitor · Lourdes
 (Branche Version_With_Detector — https://github.com/TinQuen22Fr/storm-monitor-20km)

 OBJECTIF
 --------
 Ce sketch sort la fréquence de résonance de l'antenne LC du module AS3935
 sur la broche d'interruption (IRQ). Tu peux la mesurer avec un oscilloscope
 ou un analyseur logique capable de lire un signal carré entre 4 kHz et 32 kHz
 (selon le « division ratio » choisi).

 Par défaut, le rapport de division est 16 → la fréquence affichée sur IRQ
 est freq_antenne / 16. Donc pour une antenne idéalement réglée à 500 kHz,
 tu dois mesurer ≈ 31,25 kHz sur IRQ. Pour une antenne fraîche SparkFun,
 typiquement ≈ 31,04 kHz × 16 = 496,64 kHz (< 1 % d'écart vs 500 kHz idéal).

 La datasheet AS3935 (page 35) spécifie ±3,5 % comme plage OPTIMALE.

 CONNEXIONS I2C
 --------------
   AS3935 SDA → A4
   AS3935 SCL → A5
   AS3935 IRQ → D4   (c'est sur cette broche que tu mesures la fréquence)
   AS3935 VCC → 3V3
   AS3935 GND → GND
================================================================================
*/

#include <SPI.h>
#include <Wire.h>
#include "SparkFun_AS3935.h"

// 0x03 par défaut ; peut aussi être 0x02 ou 0x01 selon les straps sous le PCB.
#define AS3935_ADDR 0x03
#define ANTFREQ     3   // code interne = oscillateur d'antenne (cf. datasheet)

SparkFun_AS3935 lightning(AS3935_ADDR);

void setup()
{
  Serial.begin(115200);
  Serial.println(F("AS3935 Franklin Lightning Detector — Tune Antenna (I2C)"));

  Wire.begin();
  if (!lightning.begin()) {
    Serial.println(F("[ERR] Détecteur introuvable — vérifier câblage I2C (SDA=A4, SCL=A5)"));
    while (1) { delay(1000); }
  }
  Serial.println(F("[OK] Prêt à tuner l'antenne."));

  // ---------------------------------------------------------------------------
  // Rapport de division (16 par défaut). Tu peux le passer à 32/64/128 si ton
  // outil de mesure ne tient pas 31 kHz. Plus le rapport est élevé, plus la
  // fréquence affichée sur IRQ est basse (donc plus facile à mesurer avec un
  // analyseur logique bas de gamme).
  // ---------------------------------------------------------------------------
  // lightning.changeDivRatio(32);

  byte divVal = lightning.readDivRatio();
  Serial.print(F("Division Ratio : "));
  Serial.println(divVal);

  // ---------------------------------------------------------------------------
  // Capacité interne d'accord (0 → 120 pF par pas de 8 pF).
  // Décommente et adapte si la mesure montre un écart > 3,5 % vs 500 kHz.
  // Exemple : lightning.tuneCap(8);  → ajoute 8 pF
  // ---------------------------------------------------------------------------
  // lightning.tuneCap(8);

  int tuneVal = lightning.readTuneCap();
  Serial.print(F("Capacité interne  : "));
  Serial.print(tuneVal);
  Serial.println(F(" pF"));

  // ---------------------------------------------------------------------------
  // Demande au capteur de sortir l'oscillateur d'antenne sur la broche IRQ.
  // ---------------------------------------------------------------------------
  Serial.println(F("\n---- Sortie de l'oscillateur sur la broche IRQ ----"));
  Serial.println(F("Branche ton oscilloscope/analyseur logique sur D4 (IRQ)."));
  Serial.println(F("Fréquence cible IRQ = 500 kHz / divRatio (≈ 31,25 kHz si div=16)."));
  lightning.displayOscillator(true, ANTFREQ);

  // Pour arrêter la sortie, passe `false` ou coupe l'alimentation du capteur.
  // lightning.displayOscillator(false, ANTFREQ);

  // ---------------------------------------------------------------------------
  // Une fois l'antenne accordée, tu peux calibrer les oscillateurs internes.
  // Décommente après avoir trouvé la bonne tuneCap.
  // ---------------------------------------------------------------------------
  // if (lightning.calibrateOsc())
  //   Serial.println(F("[OK] Oscillateurs internes calibrés."));
  // else
  //   Serial.println(F("[KO] Calibration échouée."));
}

void loop() {
  // Rien — l'autotune est lancé en setup().
}
