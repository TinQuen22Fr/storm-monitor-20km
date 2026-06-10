/*
================================================================================
 Storm Monitor · Lourdes — Détecteur d'orage AS3935 + Ethernet Shield
================================================================================
 Build & Idea by Quentin Dumont
 Branche cible GitHub : Version_With_Detector
 Dépôt              : https://github.com/TinQuen22Fr/storm-monitor-20km

 MATÉRIEL
 --------
   - Arduino Uno
   - Module Franklin AS3935 (I2C)
   - Ethernet Shield W5100/W5500
   - 3 LEDs (Bleu / Vert / Rouge)

 BIBLIOTHÈQUES (Arduino IDE > Outils > Gérer les bibliothèques)
 -------------------------------------------------------------
   - SparkFun_AS3935       (capteur foudre)
   - Ethernet              (officielle Arduino)
   - ArduinoJson           (par Benoit Blanchon, v6+)

 CONNEXIONS
 ----------
   AS3935  →  Arduino
     VCC   →  3V3
     GND   →  GND
     SDA   →  A4 (I2C)
     SCL   →  A5 (I2C)
     IRQ   →  D4

   LEDs                Pin
     Bleue (foudre)    D8
     Verte (upload OK) D7
     Rouge (upload KO) D9

 ENDPOINT BACKEND
 ----------------
   POST  http(s)://SERVER_HOST:SERVER_PORT/api/upload_storm
   Headers : X-API-Key: <API_KEY>, Content-Type: application/json
   Body    : {"kind":"lightning","distance":3.4,"energy":42.1,
              "device_id":"as3935-lourdes-01","timestamp":"<ISO>"}

   Types d'événements :
     - "lightning"  → impact détecté
     - "disturber"  → parasite identifié (informatif)
     - "heartbeat"  → ping de présence (toutes les HEARTBEAT_INTERVAL ms)

 NOTE: l'Ethernet Shield ne fait pas TLS. Pour HTTPS, soit on
       passe par Nginx en HTTP en LAN + reverse proxy, soit on
       utilise un MKR1010/ESP32. Ici on cible le backend en HTTP
       local et Nginx s'occupe du TLS pour l'app publique.

 Date : Mai 2026
================================================================================
*/

#include <Wire.h>
#include <SPI.h>
#include <Ethernet.h>
#include <ArduinoJson.h>
#include <SparkFun_AS3935.h>

// ============================================================================
// CONFIGURATION — modifiez ces valeurs avant flash
// ============================================================================

// MAC arbitraire (doit être unique sur le LAN)
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0x07 };

// Cible du backend (IP locale du serveur Kimsufi en LAN OU exposé via VPN)
const char SERVER_HOST[] = "192.168.1.10";  // <-- adapter
const int  SERVER_PORT   = 8003;            // backend FastAPI (Storm Monitor)
const char ENDPOINT[]    = "/api/upload_storm";

// Authentification (doit correspondre à UPLOAD_API_KEY côté backend .env)
const char API_KEY[]   = "lourdes-storm-upload-2026-xV7p9Qm3RtA8Ks";

// Identifiant du détecteur (utile si plusieurs sondes)
const char DEVICE_ID[] = "as3935-lourdes-01";

// AS3935 — adresse I2C par défaut
#define AS3935_ADDR 0x03

// Pins
const byte lightningInt = 4;   // IRQ AS3935
const byte LEDBLEU      = 8;   // Foudre détectée
const byte LEDVERTE     = 7;   // Réseau OK
const byte LEDROUGE     = 9;   // Réseau KO

// Mode du capteur : OUTDOOR (préconisé en extérieur)
#define INDOOR_OUTDOOR_MODE OUTDOOR  // ou INDOOR

// Seuils AS3935
const byte NOISE_FLOOR     = 2;   // 0-7, plus haut = moins sensible
const byte WATCHDOG_VAL    = 2;   // 0-10
const byte SPIKE_REJECT    = 2;   // 0-11
const byte LIGHTNING_THRESH = 1;  // 1, 5, 9 ou 16 strikes

// Heartbeat toutes les 5 minutes
const unsigned long HEARTBEAT_INTERVAL = 5UL * 60UL * 1000UL;

// ============================================================================
// État interne
// ============================================================================

SparkFun_AS3935 lightning;
EthernetClient  client;

unsigned long lastHeartbeat = 0;
unsigned long lastBlinkLed  = 0;
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

  // --- Capteur AS3935 ---
  Wire.begin();
  if (!lightning.begin(AS3935_ADDR)) {
    Serial.println(F("[AS3935] introuvable — vérifier câblage I2C"));
    digitalWrite(LEDROUGE, HIGH);
    while (true) { delay(1000); }
  }

  lightning.resetSettings();
  lightning.setIndoorOutdoor(INDOOR_OUTDOOR_MODE);
  lightning.setNoiseLevel(NOISE_FLOOR);
  lightning.watchdogThreshold(WATCHDOG_VAL);
  lightning.spikeRejection(SPIKE_REJECT);
  lightning.lightningThreshold(LIGHTNING_THRESH);
  lightning.maskDisturber(false);  // on REMONTE les disturbers (informatif)
  Serial.println(F("[AS3935] initialisé"));

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

  // Premier heartbeat immédiat
  if (ethernetReady) {
    sendEvent("heartbeat", -1.0, -1.0);
    lastHeartbeat = millis();
  }
}

// ============================================================================
// LOOP
// ============================================================================

void loop() {
  // Maintenir le bail DHCP (sans bloquer)
  Ethernet.maintain();

  // ---- Lecture de l'interruption AS3935 ----
  if (digitalRead(lightningInt) == HIGH) {
    byte intVal = lightning.readInterruptReg();
    delay(2);

    switch (intVal) {
      case NOISE_INT:
        Serial.println(F("[AS3935] Bruit ambiant"));
        // pas d'upload — informatif seulement, déjà filtré
        break;

      case DISTURBER_INT:
        Serial.println(F("[AS3935] Parasite (disturber)"));
        sendEvent("disturber", -1.0, -1.0);
        break;

      case LIGHTNING_INT: {
        byte distance     = lightning.distanceToStorm();   // km (1..40, 63=hors portée)
        long lightEnergy  = lightning.lightningEnergy();   // valeur brute (~0..1000000)

        // Normaliser l'énergie en "kJ équivalent" (échelle relative)
        float energyKJ = (float)lightEnergy / 1000.0;

        Serial.print(F("[AS3935] FOUDRE · d="));
        Serial.print(distance);
        Serial.print(F(" km, energy="));
        Serial.println(lightEnergy);

        // Flash LED bleue
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

  // ---- Heartbeat périodique ----
  unsigned long now = millis();
  if (ethernetReady && (now - lastHeartbeat) >= HEARTBEAT_INTERVAL) {
    sendEvent("heartbeat", -1.0, -1.0);
    lastHeartbeat = now;
  }
}

// ============================================================================
// ENVOI HTTP POST JSON vers /api/upload_storm
// ============================================================================

void sendEvent(const char* kind, float distance, float energy) {
  if (!ethernetReady) return;

  // 1) Construire le JSON
  StaticJsonDocument<256> doc;
  doc["kind"]      = kind;
  doc["device_id"] = DEVICE_ID;
  // distance/energy : -1 = non applicable (heartbeat/disturber)
  doc["distance"]  = (distance < 0) ? 0.0 : distance;
  doc["energy"]    = (energy   < 0) ? 0.0 : energy;

  String body;
  serializeJson(doc, body);

  // 2) Connexion TCP
  client.stop();
  if (!client.connect(SERVER_HOST, SERVER_PORT)) {
    Serial.println(F("[HTTP] connect KO"));
    blinkLed(LEDROUGE, 2);
    return;
  }

  // 3) Requête HTTP/1.1
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

  // 4) Lecture du status code (1ère ligne)
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

  // Drain et fermer
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
