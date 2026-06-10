/*
================================================================================
 Example 3 — Tune Antenna (SPI)
================================================================================
 Source originale : SparkFun_AS3935_Lightning_Detector_Arduino_Library
 Auteur original  : Elias Santistevan, SparkFun Electronics — Avril 2019
 Licence          : Beerware (domaine public, offre-moi une bière si on se croise)

 Adapté & commenté en français pour le projet Storm Monitor · Lourdes
 (Branche Version_With_Detector — https://github.com/TinQuen22Fr/storm-monitor-20km)

 OBJECTIF
 --------
 Identique à l'exemple I2C : sortir la fréquence de résonance de l'antenne
 sur la broche IRQ pour la mesurer à l'oscilloscope/analyseur logique.

 Référence : datasheet AS3935 page 35 — plage optimale ±3,5 % autour de 500 kHz.

 CONNEXIONS SPI (Arduino Uno)
 ----------------------------
   AS3935 MOSI → D11
   AS3935 MISO → D12
   AS3935 SCK  → D13
   AS3935 CS   → D10  (par défaut dans cet exemple, à adapter si conflit Ethernet)
   AS3935 IRQ  → D4   ← mesure la fréquence ici
   AS3935 SI   → GND  (force le mode SPI sur les modules SparkFun)
   AS3935 VCC  → 3V3
   AS3935 GND  → GND

 ⚠️ Si tu utilises ce sketch en présence d'un Ethernet Shield (qui prend déjà
    CS=D10), change `spiCS` ci-dessous pour D6 par exemple, et débranche
    l'Ethernet Shield le temps du tuning pour éviter tout conflit SPI parasite.
================================================================================
*/

#include <SPI.h>
#include <Wire.h>
#include "SparkFun_AS3935.h"

#define ANTFREQ 3   // code interne = oscillateur d'antenne

// Chip Select SPI — D10 par défaut, change-le si conflit (Ethernet Shield).
int spiCS = 10;

SparkFun_AS3935 lightning;

void setup()
{
  Serial.begin(115200);
  Serial.println(F("AS3935 Franklin Lightning Detector — Tune Antenna (SPI)"));

  SPI.begin();
  if (!lightning.beginSPI(spiCS)) {
    Serial.println(F("[ERR] Détecteur introuvable sur SPI — vérifier CS, MOSI/MISO/SCK"));
    while (1) { delay(1000); }
  }
  Serial.println(F("[OK] Prêt à tuner l'antenne."));

  // ---------------------------------------------------------------------------
  // Rapport de division (16 par défaut). Passe à 32/64/128 si ton matos de
  // mesure peine à 31 kHz.
  // ---------------------------------------------------------------------------
  // lightning.changeDivRatio(32);

  byte divVal = lightning.readDivRatio();
  Serial.print(F("Division Ratio : "));
  Serial.println(divVal);

  // ---------------------------------------------------------------------------
  // Capacité interne d'accord (0 → 120 pF, pas de 8 pF).
  // Décommente pour appliquer la valeur trouvée après mesure.
  // ---------------------------------------------------------------------------
  // lightning.tuneCap(8);

  int tuneVal = lightning.readTuneCap();
  Serial.print(F("Capacité interne  : "));
  Serial.print(tuneVal);
  Serial.println(F(" pF"));

  // ---------------------------------------------------------------------------
  // Sort la fréquence de résonance d'antenne sur la broche IRQ
  // ---------------------------------------------------------------------------
  Serial.println(F("\n---- Sortie de l'oscillateur sur la broche IRQ ----"));
  Serial.println(F("Branche ton oscilloscope/analyseur logique sur D4 (IRQ)."));
  Serial.println(F("Fréquence cible IRQ = 500 kHz / divRatio (≈ 31,25 kHz si div=16)."));
  lightning.displayOscillator(true, ANTFREQ);

  // Pour arrêter : lightning.displayOscillator(false, ANTFREQ);

  // ---------------------------------------------------------------------------
  // Calibration des oscillateurs internes — à lancer une fois l'antenne réglée.
  // ---------------------------------------------------------------------------
  // if (lightning.calibrateOsc())
  //   Serial.println(F("[OK] Oscillateurs internes calibrés."));
  // else
  //   Serial.println(F("[KO] Calibration échouée."));
}

void loop() {
  // Rien — l'autotune est lancé en setup().
}
