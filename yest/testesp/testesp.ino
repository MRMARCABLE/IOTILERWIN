#include <WiFi.h>

#define LED_PIN 2  // LED bawaan kebanyakan ESP32 DevKit

unsigned long terakhirScan = 0;

void infoChip() {
  Serial.println("=== TES ESP32 ===");
  Serial.printf("Chip     : %s rev %d\n", ESP.getChipModel(), ESP.getChipRevision());
  Serial.printf("Core     : %d\n", ESP.getChipCores());
  Serial.printf("CPU      : %d MHz\n", getCpuFrequencyMhz());
  Serial.printf("Flash    : %u KB\n", ESP.getFlashChipSize() / 1024);
  Serial.printf("Free heap: %u KB\n", ESP.getFreeHeap() / 1024);
  Serial.printf("MAC      : %s\n", WiFi.macAddress().c_str());
  Serial.println();
}

void scanWiFi() {
  Serial.println("Scan WiFi...");
  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.println("Tidak ada jaringan ditemukan");
    return;
  }
  for (int i = 0; i < n; i++) {
    Serial.printf("%2d. %-24s %4d dBm  ch %d\n", i + 1,
                  WiFi.SSID(i).c_str(), WiFi.RSSI(i), WiFi.channel(i));
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(1000);
  infoChip();
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  delay(250);
  digitalWrite(LED_PIN, LOW);
  delay(250);

  if (millis() - terakhirScan > 10000) {
    terakhirScan = millis();
    scanWiFi();
  }
}
