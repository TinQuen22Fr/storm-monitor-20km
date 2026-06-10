/*
================================================================================
 Autotune Antenna → Backend Storm Monitor (SPI)
================================================================================
 Variante SPI du sketch d'autotune. Lit lightning.readAntennaFreq() toutes les
 2 secondes et POSTe la valeur sur /api/upload_storm avec kind=tune_freq.
 La page /detector/tune affiche en direct l'écart vs 500 kHz et la valeur de
 tuneCap recommandée — sans oscilloscope.

 Câblage SPI CJMCU : voir hardware/Arduino_StormDetector_SPI.ino
 (CS=D6, MOSI=D11, MISO=D12, SCK=D13, IRQ=D4, SI=GND)
================================================================================
*/

#include <SPI.h>
#include <Wire.h>
#include <Ethernet.h>
#include <ArduinoJson.h>
#include <SparkFun_AS3935.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0x78 };

const char SERVER_HOST[] = "storm.ton-domaine.fr";
const int  SERVER_PORT   = 8080;
const char ENDPOINT[]    = "/api/upload_storm";

const char API_KEY[]     = "lourdes-storm-upload-2026-xV7p9Qm3RtA8Ks";
const char DEVICE_ID[]   = "as3935-lourdes-tune-spi";

const byte AS3935_CS  = 6;
#define ANTFREQ 3

const byte INITIAL_TUNE_CAP = 0;
const unsigned long SAMPLE_INTERVAL = 2000;

// ============================================================================

SparkFun_AS3935 lightning;
EthernetClient  client;
byte currentTuneCap = INITIAL_TUNE_CAP;
unsigned long lastSample = 0;

void setup() {
  Serial.begin(115200);
  Serial.println(F("=== Storm Monitor — Autotune antenne (SPI) ==="));

  SPI.begin();
  if (!lightning.beginSPI(AS3935_CS, 2000000)) {
    Serial.println(F("[ERR] AS3935 introuvable SPI"));
    while (1) { delay(1000); }
  }
  lightning.resetSettings();
  lightning.tuneCap(currentTuneCap);
  lightning.displayOscillator(true, ANTFREQ);

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
    long freq = lightning.readAntennaFreq();

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

  unsigned long start = millis();
  while (!client.available() && (millis() - start) < 3000) { delay(10); }
  while (client.connected() && client.available()) { client.read(); }
  client.stop();
}
