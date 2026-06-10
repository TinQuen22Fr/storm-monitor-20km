/*
================================================================================
 Autotune Antenna → Backend Storm Monitor (I2C)
================================================================================
 Lit la fréquence de résonance d'antenne du CJMCU AS3935 via la fonction
 lightning.readAntennaFreq() de la librairie SparkFun, puis POSTe la valeur
 sur le backend Storm Monitor toutes les 2 secondes avec :
     kind = "tune_freq"
     raw_freq_hz = <fréquence brute en Hz>
     tune_cap    = <valeur actuelle de tuneCap>

 Le backend agrège ces mesures sur /api/detector/tune et la page web
 /detector/tune affiche en direct la fréquence, l'écart vs 500 kHz et la
 valeur de tuneCap recommandée — sans oscilloscope.

 ⚠️ Ce sketch ne détecte PAS la foudre — il sert uniquement à l'accordage.
    Une fois la bonne valeur trouvée, reporte-la dans Arduino_StormDetector.ino
    et reflashe ce sketch principal.

 Câblage I2C CJMCU : identique au sketch principal Arduino_StormDetector.ino
 (cf. hardware/README.md).
================================================================================
*/

#include <Wire.h>
#include <SPI.h>
#include <Ethernet.h>
#include <ArduinoJson.h>
#include <SparkFun_AS3935.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0x77 };

const char SERVER_HOST[] = "storm.ton-domaine.fr";   // <-- adapte (domaine public Kimsufi)
const int  SERVER_PORT   = 8080;                     // port HTTP non chiffré dédié
const char ENDPOINT[]    = "/api/upload_storm";

const char API_KEY[]     = "lourdes-storm-upload-2026-xV7p9Qm3RtA8Ks";
const char DEVICE_ID[]   = "as3935-lourdes-tune";

#define AS3935_ADDR 0x03
#define ANTFREQ     3   // code interne = oscillateur d'antenne

// Valeur de départ pour tuneCap (0-15) — ajuste depuis la page /detector/tune
const byte INITIAL_TUNE_CAP = 0;

// Intervalle entre 2 mesures + envois (ms)
const unsigned long SAMPLE_INTERVAL = 2000;

// ============================================================================

SparkFun_AS3935 lightning(AS3935_ADDR);
EthernetClient  client;
byte currentTuneCap = INITIAL_TUNE_CAP;
unsigned long lastSample = 0;

void setup() {
  Serial.begin(115200);
  Serial.println(F("=== Storm Monitor — Autotune antenne (I2C) ==="));

  Wire.begin();
  if (!lightning.begin()) {
    Serial.println(F("[ERR] AS3935 introuvable I2C"));
    while (1) { delay(1000); }
  }
  lightning.resetSettings();
  lightning.tuneCap(currentTuneCap);
  lightning.displayOscillator(true, ANTFREQ);  // sort la fréquence sur IRQ

  Serial.print(F("[OK] tuneCap initial = "));
  Serial.println(currentTuneCap);

  if (Ethernet.begin(mac) == 0) {
    Serial.println(F("[ERR] DHCP KO"));
    while (1) { delay(1000); }
  }
  Serial.print(F("[OK] IP : "));
  Serial.println(Ethernet.localIP());
  Serial.println(F("[GO] Mesures envoyées toutes les 2 s — ouvre /detector/tune"));
}

void loop() {
  Ethernet.maintain();

  if (millis() - lastSample >= SAMPLE_INTERVAL) {
    lastSample = millis();

    // Lecture interne de la fréquence (le capteur la mesure via son timer)
    // readAntennaFreq() retourne la valeur DÉJÀ multipliée par le division ratio
    long freq = lightning.readAntennaFreq();   // typiquement 480_000 → 520_000 Hz

    Serial.print(F("freq = "));
    Serial.print(freq);
    Serial.print(F(" Hz  · tuneCap = "));
    Serial.println(currentTuneCap);

    postFreq(freq, currentTuneCap);
  }
}

void postFreq(long freqHz, byte tuneCap) {
  StaticJsonDocument<192> doc;
  doc["kind"]        = "tune_freq";
  doc["device_id"]   = DEVICE_ID;
  doc["distance"]    = 0.0;
  doc["energy"]      = 0.0;
  doc["raw_freq_hz"] = (long)freqHz;
  doc["tune_cap"]    = (int)tuneCap;

  String body;
  serializeJson(doc, body);

  client.stop();
  if (!client.connect(SERVER_HOST, SERVER_PORT)) {
    Serial.println(F("[HTTP] connect KO"));
    return;
  }

  client.print(F("POST "));
  client.print(ENDPOINT);
  client.println(F(" HTTP/1.1"));
  client.print(F("Host: "));
  client.print(SERVER_HOST);
  client.print(F(":"));
  client.println(SERVER_PORT);
  client.println(F("Content-Type: application/json"));
  client.print(F("X-API-Key: "));
  client.println(API_KEY);
  client.print(F("Content-Length: "));
  client.println(body.length());
  client.println(F("Connection: close"));
  client.println();
  client.print(body);

  // Drain & close
  unsigned long start = millis();
  while (!client.available() && (millis() - start) < 3000) { delay(10); }
  while (client.connected() && client.available()) { client.read(); }
  client.stop();
}
