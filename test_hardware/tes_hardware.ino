/*
  tes_hardware.ino
  Diagnosis hardware ESP32-WROOM-32: OLED SSD1306 + 2 servo.

  Yang dilakukan:
    1. Scan I2C (SDA=GPIO21, SCL=GPIO22) dan cetak alamat yang ditemukan
    2. Kalau OLED ketemu (0x3C / 0x3D): tampilkan teks + bingkai di layar
    3. Sapu servo Pan (GPIO18) lalu Tilt (GPIO19): 90 -> 45 -> 135 -> 90
    Semua hasil dicetak ke Serial Monitor (115200 baud).

  Library: Adafruit SSD1306, Adafruit GFX Library, ESP32Servo
  Board  : esp32:esp32:esp32
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

#define SDA_PIN 21
#define SCL_PIN 22

const int pinServoPan  = 18;
const int pinServoTilt = 19;

Adafruit_SSD1306 display(128, 64, &Wire, -1);
Servo servoPan;
Servo servoTilt;

uint8_t alamatOled = 0;   // 0 = OLED belum ditemukan

void scanI2C() {
  Serial.println("Scan I2C (SDA=21, SCL=22)...");
  int jumlah = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  Ditemukan perangkat di 0x%02X\n", a);
      if (a == 0x3C || a == 0x3D) alamatOled = a;
      jumlah++;
    }
  }
  if (jumlah == 0) {
    Serial.println("  TIDAK ADA perangkat I2C. Cek SDA/SCL/VCC(3V3)/GND OLED.");
  }
}

void tampil(const char *baris1, const char *baris2) {
  if (!alamatOled) return;
  display.clearDisplay();
  display.drawRect(0, 0, 128, 64, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(10, 18);
  display.print(baris1);
  display.setCursor(10, 36);
  display.print(baris2);
  display.display();
}

void sapu(Servo &servo, const char *nama) {
  Serial.printf("Tes servo %s: 90 -> 45 -> 135 -> 90\n", nama);
  tampil("TES SERVO", nama);
  for (int s = 90; s >= 45; s--)  { servo.write(s); delay(15); }
  for (int s = 45; s <= 135; s++) { servo.write(s); delay(15); }
  for (int s = 135; s >= 90; s--) { servo.write(s); delay(15); }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("=== TES HARDWARE ESP32 ===");

  Wire.begin(SDA_PIN, SCL_PIN);
  scanI2C();

  if (alamatOled) {
    if (display.begin(SSD1306_SWITCHCAPVCC, alamatOled)) {
      Serial.printf("OLED siap di 0x%02X\n", alamatOled);
      char alamatTeks[20];
      snprintf(alamatTeks, sizeof(alamatTeks), "Alamat 0x%02X", alamatOled);
      tampil("OLED OK", alamatTeks);
    } else {
      Serial.println("display.begin() gagal.");
      alamatOled = 0;
    }
  } else {
    Serial.println("OLED tidak ditemukan di 0x3C maupun 0x3D.");
  }

  servoPan.attach(pinServoPan, 500, 2400);
  servoTilt.attach(pinServoTilt, 500, 2400);
  servoPan.write(90);
  servoTilt.write(90);
  delay(1500);
}

void loop() {
  sapu(servoPan, "PAN (GPIO18)");
  delay(800);
  sapu(servoTilt, "TILT (GPIO19)");
  delay(800);
  tampil("Tes selesai", "Ulang...");
  Serial.println("--- ulang ---");
  delay(1500);
}


