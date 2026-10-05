// Fungsi setup dijalankan sekali saat Arduino dinyalakan atau direset
void setup() {
  // Mengatur pin 13 sebagai output digital
  pinMode(13, OUTPUT);
}

// Fungsi loop berjalan berulang-ulang selamanya
void loop() {
  digitalWrite(13, HIGH);   // Menyalakan LED (tegangan 5V)
  delay(1000);              // Menunggu selama 1 detik (1000 milidetik)
  digitalWrite(13, LOW);    // Mematikan LED (tegangan 0V)
  delay(1000);              // Menunggu selama 1 detik
}



