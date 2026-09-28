/*
  senyum.ino
  Menampilkan wajah SENYUM di OLED SSD1306 128x64 (I2C) pada ESP32-WROOM-32.

  WIRING:
    OLED VCC -> 3V3
    OLED GND -> GND
    OLED SDA -> GPIO21
    OLED SCL -> GPIO22

  LIBRARY (install sekali):
    arduino-cli lib install "Adafruit SSD1306"
    arduino-cli lib install "Adafruit GFX Library"

  BOARD (FQBN): esp32:esp32:esp32
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define LEBAR_LAYAR  128
#define TINGGI_LAYAR 64
#define OLED_RESET   -1
#define ALAMAT_OLED  0x3C   // kalau layar tidak nyala, coba 0x3D

#define SDA_PIN 21
#define SCL_PIN 22

Adafruit_SSD1306 display(LEBAR_LAYAR, TINGGI_LAYAR, &Wire, OLED_RESET);

void gambarSenyum() {
  const int cx = LEBAR_LAYAR / 2;
  const int cy = TINGGI_LAYAR / 2;

  display.clearDisplay();

  // Lingkaran wajah (tebal 2 px)
  display.drawCircle(cx, cy, 30, SSD1306_WHITE);
  display.drawCircle(cx, cy, 29, SSD1306_WHITE);

  // Mata
  display.fillCircle(cx - 10, cy - 9, 3, SSD1306_WHITE);
  display.fillCircle(cx + 10, cy - 9, 3, SSD1306_WHITE);

  // Mulut senyum: busur setengah elips di bawah titik tengah
  for (int sudut = 25; sudut <= 155; sudut += 2) {
    float rad = sudut * PI / 180.0;
    int x = cx + (int)(17 * cos(rad));
    int y = cy + 2 + (int)(13 * sin(rad));
    display.fillCircle(x, y, 1, SSD1306_WHITE);
  }

  display.display();
}

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);

  if (!display.begin(SSD1306_SWITCHCAPVCC, ALAMAT_OLED)) {
    Serial.println("OLED tidak terdeteksi. Cek wiring SDA/SCL dan alamat I2C (0x3C / 0x3D).");
    while (true) delay(1000);
  }

  gambarSenyum();
  Serial.println("Wajah senyum ditampilkan.");
}

void loop() {
  // Tidak ada yang perlu diulang, gambar tetap tampil.
}
