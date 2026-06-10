/*
================================================================================
 Storm Monitor · Lourdes — Détecteur d'orage AS3935 (variante SPI) + Ethernet
================================================================================
 Build & Idea by Quentin Dumont
 Branche cible GitHub : Version_With_Detector
 Dépôt              : https://github.com/TinQuen22Fr/storm-monitor-20km

 ⚠️ Cette version utilise la connexion SPI au lieu de l'I2C — souvent plus stable
    en pratique (anti-bruit meilleur, communication full-duplex, pas d'adresse à
    partager). Choisir cette version si :
      - tu observes des freezes du bus I2C au moment d'un impact
      - tu as déjà du matériel I2C sur le bus (capteurs météo)
      - tu veux une meilleure isolation électrique

 MATÉRIEL
 --------
   - Arduino Uno
   - Module Franklin AS3935 (variante SPI — vérifier le strap MISO/SDA sur le PCB)
   - Ethernet Shield W5100/W5500 (occupe déjà SPI sur D10-D13)
   - 3 LEDs (Bleu / Vert / Rouge)

 ⚠️ ATTENTION CONFLIT SPI :
   L'Ethernet Shield utilise les broches SPI partagées (D11/D12/D13) avec son
   propre CS sur D10. L'AS3935 doit donc avoir un CS DIFFÉRENT (ici D6) pour
   éviter toute collision. La librairie SparkFun_AS3935 gère bien le partage.

 BIBLIOTHÈQUES (Arduino IDE > Outils > Gérer les bibliothèques)
 -------------------------------------------------------------
   - SparkFun_AS3935       (capteur foudre — interface SPI incluse)
   - Ethernet              (officielle Arduino)
   - ArduinoJson           (par Benoit Blanchon, v6+)
   - SPI                   (incluse Arduino)

 CONNEXIONS SPI
 --------------
   AS3935  →  Arduino Uno
     VCC   →  3V3 (NE PAS mettre en 5V)
     GND   →  GND
     MOSI  →  D11 (SPI MOSI partagé avec Ethernet)
     MISO  →  D12 (SPI MISO partagé)
     SCK   →  D13 (SPI SCK partagé)
     CS    →  D6  (Chip Select dédié — distinct de D10 utilisé par Ethernet)
     IRQ   →  D4
     SI    →  GND  (force le mode SPI sur le module SparkFun)

   LEDs                Pin
     Bleue (foudre)    D8
     Verte (upload OK) D7
     Rouge (upload KO) D9

 ENDPOINT BACKEND
 ----------------
   POST  http://SERVER_HOST:SERVER_PORT/api/upload_storm
   Headers : X-API-Key: <API_KEY>, Content-Type: application/json
   Body    : {"kind":"lightning","distance":3.4,"energy":42.1,
              "device_id":"as3935-lourdes-01","timestamp":"<ISO>"}

   Types d'événements remontés :
     - "lightning"  → impact détecté
     - "disturber"  → parasite identifié (informatif)
     - "heartbeat"  → ping de présence (toutes les HEARTBEAT_INTERVAL ms)

 Date : Juin 2026
================================================================================
*/

#include <SPI.h>
#include <Ethernet.h>
#include <ArduinoJson.h>
#include <SparkFun_AS3935.h>

// ============================================================================
// CONFIGURATION — modifiez ces valeurs avant flash
// ============================================================================

// MAC arbitraire (doit être unique sur le LAN)
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0x08 };

// Cible du backend
const char SERVER_HOST[] = "192.168.1.10";  // <-- adapter (IP LAN du Kimsufi ou tunnel)
const int  SERVER_PORT   = 8003;
const char ENDPOINT[]    = "/api/upload_storm";

// Authentification (doit correspondre à UPLOAD_API_KEY côté backend .env)
const char API_KEY[]   = "lourdes-storm-upload-2026-xV7p9Qm3RtA8Ks";

// Identifiant du détecteur
const char DEVICE_ID[] = "as3935-lourdes-01-spi";

// Pins SPI
const byte AS3935_CS  = 6;     // Chip Select dédié AS3935 (NE PAS utiliser D10)
const byte lightningInt = 4;   // IRQ AS3935
const byte LEDBLEU      = 8;
const byte LEDVERTE     = 7;
const byte LEDROUGE     = 9;

// Mode du capteur
#define INDOOR_OUTDOOR_MODE OUTDOOR

// Seuils AS3935 (cf. datasheet section 7)
const byte NOISE_FLOOR      = 2;   // 0-7
const byte WATCHDOG_VAL     = 2;   // 0-10
const byte SPIKE_REJECT     = 2;   // 0-11
const byte LIGHTNING_THRESH = 1;   // 1, 5, 9 ou 16 strikes

// Heartbeat toutes les 5 minutes
const unsigned long HEARTBEAT_INTERVAL = 5UL * 60UL * 1000UL;

// ============================================================================
// État interne
// ============================================================================

SparkFun_AS3935 lightning;
EthernetClient  client;

unsigned long lastHeartbeat = 0;
bool ethernetReady = false;

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) {}

  pinMode(LEDBLEU, OUTPUT);
  pinMode(LEDVERTE, OUTPUT);
  pinMode(LEDROUGE, OUTPUT);
  pinMode(lightningInt, INPUT);

  // --- SPI + AS3935 ---
  SPI.begin();
  // beginSPI signature : (CS pin, SPI port)
  if (!lightning.beginSPI(AS3935_CS, 2000000)) {
    Serial.println(F("[AS3935] introuvable sur SPI — vérifier câblage CS=D6, MOSI/MISO/SCK"));
    digitalWrite(LEDROUGE, HIGH);
    while (true) { delay(1000); }
  }

  lightning.resetSettings();
  lightning.setIndoorOutdoor(INDOOR_OUTDOOR_MODE);
  lightning.setNoiseLevel(NOISE_FLOOR);
  lightning.watchdogThreshold(WATCHDOG_VAL);
  lightning.spikeRejection(SPIKE_REJECT);
  lightning.lightningThreshold(LIGHTNING_THRESH);
  lightning.maskDisturber(false);
  Serial.println(F("[AS3935] initialisé en SPI"));

  // --- Ethernet ---
  Serial.println(F("[ETH] initialisation DHCP…"));
  if (Ethernet.begin(mac) == 0) {
    Serial.println(F("[ETH] DHCP échoué — vérifier câble & routeur"));
    digitalWrite(LEDROUGE, HIGH);
  } else {
    ethernetReady = true;
    Serial.print(F("[ETH] IP locale : "));
    Serial.println(Ethernet.localIP());
    digitalWrite(LEDVERTE, HIGH);
    delay(500);
    digitalWrite(LEDVERTE, LOW);
  }

  // Premier heartbeat
  if (ethernetReady) {
    sendEvent("heartbeat", -1.0, -1.0);
    lastHeartbeat = millis();
  }
}

// ============================================================================
// LOOP
// ============================================================================

void loop() {
  Ethernet.maintain();

  if (digitalRead(lightningInt) == HIGH) {
    byte intVal = lightning.readInterruptReg();
    delay(2);

    switch (intVal) {
      case NOISE_INT:
        Serial.println(F("[AS3935] Bruit ambiant"));
        break;

      case DISTURBER_INT:
        Serial.println(F("[AS3935] Parasite"));
        sendEvent("disturber", -1.0, -1.0);
        break;

      case LIGHTNING_INT: {
        byte distance     = lightning.distanceToStorm();
        long lightEnergy  = lightning.lightningEnergy();
        float energyKJ    = (float)lightEnergy / 1000.0;

        Serial.print(F("[AS3935] FOUDRE · d="));
        Serial.print(distance);
        Serial.print(F(" km, energy="));
        Serial.println(lightEnergy);

        digitalWrite(LEDBLEU, HIGH);
        delay(80);
        digitalWrite(LEDBLEU, LOW);

        sendEvent("lightning", (float)distance, energyKJ);
        break;
      }

      default:
        break;
    }
  }

  unsigned long now = millis();
  if (ethernetReady && (now - lastHeartbeat) >= HEARTBEAT_INTERVAL) {
    sendEvent("heartbeat", -1.0, -1.0);
    lastHeartbeat = now;
  }
}

// ============================================================================
// POST JSON vers /api/upload_storm
// ============================================================================

void sendEvent(const char* kind, float distance, float energy) {
  if (!ethernetReady) return;

  StaticJsonDocument<256> doc;
  doc["kind"]      = kind;
  doc["device_id"] = DEVICE_ID;
  doc["distance"]  = (distance < 0) ? 0.0 : distance;
  doc["energy"]    = (energy   < 0) ? 0.0 : energy;

  String body;
  serializeJson(doc, body);

  client.stop();
  if (!client.connect(SERVER_HOST, SERVER_PORT)) {
    Serial.println(F("[HTTP] connect KO"));
    blinkLed(LEDROUGE, 2);
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
  while (!client.available() && (millis() - start) < 5000) { delay(10); }

  String status = client.readStringUntil('\n');
  Serial.print(F("[HTTP] "));
  Serial.println(status);

  if (status.indexOf("200") > 0) {
    blinkLed(LEDVERTE, 1);
  } else {
    blinkLed(LEDROUGE, 1);
  }

  while (client.connected() && client.available()) {
    client.read();
  }
  client.stop();
}

void blinkLed(byte pin, byte times) {
  for (byte i = 0; i < times; i++) {
    digitalWrite(pin, HIGH);
    delay(60);
    digitalWrite(pin, LOW);
    delay(60);
  }
}
