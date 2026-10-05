#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>

// Definisi Layar OLED SSD1306 (128x64)
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Objek dan Pin Servo
Servo servoPan;   // Sumbu X (Horizontal / Kiri-Kanan)
Servo servoTilt;  // Sumbu Y (Vertikal / Atas-Bawah)

const int pinServoPan  = 18;
const int pinServoTilt = 19;

// Variabel Sudut Gerak (Default menghadap tengah = 90 derajat)
int currentPan  = 90;
int currentTilt = 90;
int targetPan   = 90;
int targetTilt  = 90;

// Pewaktu (Non-blocking Timer)
unsigned long lastAIDetection = 0;
unsigned long lastBlinkTime   = 0;
bool isBlinking = false;

// Fungsi Menggambar Ekspresi Mata Robot di Layar OLED
void drawRobotFace(int eyeShiftX, int eyeShiftY, bool blink) {
  display.clearDisplay();

  // Titik pusat kedua mata
  int leftEyeX  = 40 + eyeShiftX;
  int rightEyeX = 88 + eyeShiftX;
  int eyesY     = 32 + eyeShiftY;

  if (blink) {
    // Animasi Kelopak Mata Terpejam (Garis Pipih Melengkung)
    display.fillRoundRect(leftEyeX - 18, eyesY - 2, 36, 4, 2, SSD1306_WHITE);
    display.fillRoundRect(rightEyeX - 18, eyesY - 2, 36, 4, 2, SSD1306_WHITE);
  } else {
    // Kelopak Luar Mata (Putih)
    display.fillRoundRect(leftEyeX - 18, eyesY - 20, 36, 40, 8, SSD1306_WHITE);
    display.fillRoundRect(rightEyeX - 18, eyesY - 20, 36, 40, 8, SSD1306_WHITE);

    // Bola Mata / Pupil Dalam (Hitam)
    display.fillCircle(leftEyeX, eyesY, 7, SSD1306_BLACK);
    display.fillCircle(rightEyeX, eyesY, 7, SSD1306_BLACK);

    // Efek Pantulan Cahaya di Bola Mata (Titik Putih Kecil)
    display.fillCircle(leftEyeX + 2, eyesY - 2, 2, SSD1306_WHITE);
    display.fillCircle(rightEyeX + 2, eyesY - 2, 2, SSD1306_WHITE);
  }

  // Tampilkan gambar ke layar fisik
  display.display();
}

void setup() {
  Serial.begin(115200);

  // 1. Inisialisasi Jalur I2C (SDA = GPIO 21, SCL = GPIO 22)
  Wire.begin(21, 22);
  Wire.setClock(400000);   // [DITAMBAH] I2C 400 kHz: refresh OLED ~4x lebih cepat, gerak servo jadi lebih lancar

  // 2. Inisialisasi Display OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("[ERROR] OLED SSD1306 tidak terdeteksi!"));
    for (;;);
  }

  // Tampilan Sambutan Awal (Booting Screen)
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(18, 20);
  display.print("AI TRACKING ARM");
  display.setCursor(24, 35);
  display.print("Initializing...");
  display.display();
  delay(1500);

  // 3. Inisialisasi Servo (SG90: 50 Hz, pulsa 500-2400 us)
  servoPan.setPeriodHertz(50);    // [DITAMBAH] frekuensi standar servo analog SG90
  servoTilt.setPeriodHertz(50);
  servoPan.attach(pinServoPan, 500, 2400);
  servoTilt.attach(pinServoTilt, 500, 2400);
  servoPan.write(currentPan);
  servoTilt.write(currentTilt);

  Serial.println(F("========================================"));
  Serial.println(F("   SISTEM LENGAN TRACKING AKTIF (ESP32) "));
  Serial.println(F("========================================"));
}

void loop() {
  unsigned long now = millis();

  // 1. SIMULASI AI VISION: Wajah bergerak setiap 2.8 detik
  if (now - lastAIDetection > 2800) {
    targetPan  = random(45, 135);  // Sudut menjejak horizontal (kiri-kanan)
    targetTilt = random(70, 110);  // Sudut menjejak vertikal (atas-bawah)
    lastAIDetection = now;

    // Cetak log telemetri ke Serial Monitor
    Serial.print(F("[VISION-AI] Target Face Acquired -> Pan: "));
    Serial.print(targetPan);
    Serial.print(F(" deg | Tilt: "));
    Serial.print(targetTilt);
    Serial.println(F(" deg"));
  }

  // 2. INTERPOLASI GERAKAN HALUS (Mencegah servo menyentak kasar)
  if (currentPan < targetPan)   currentPan++;
  if (currentPan > targetPan)   currentPan--;
  if (currentTilt < targetTilt) currentTilt++;
  if (currentTilt > targetTilt) currentTilt--;

  servoPan.write(currentPan);
  servoTilt.write(currentTilt);

  // 3. ANIMASI BERKEDIP OTOMATIS
  if (now - lastBlinkTime > 3500) {
    isBlinking = true;
    lastBlinkTime = now;
  }
  // Lama kelopak menutup hanya 160 milidetik
  if (isBlinking && (now - lastBlinkTime > 160)) {
    isBlinking = false;
  }

  // 4. PEMETAAN KOORDINAT MATA (Pupil bergeser sesuai sudut servo)
  // Rentang servo dipetakan ke offset piksel layar (-10 s/d +10 piksel)
  int eyeOffsetX = map(currentPan, 45, 135, -10, 10);
  int eyeOffsetY = map(currentTilt, 70, 110, -5, 5);

  drawRobotFace(eyeOffsetX, eyeOffsetY, isBlinking);

  delay(20); // Interval pembaruan gerakan (kecepatan transisi)
}
