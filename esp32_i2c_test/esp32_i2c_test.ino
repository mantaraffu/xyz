// ==========================================
// TEST ESP32 I2C SCANNER E LCD 1602
// ==========================================

#include <Wire.h>

// Definizione Pin I2C Personalizzati
const int I2C_SDA_PIN = 6;
const int I2C_SCL_PIN = 7;

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n=========================================");
  Serial.println("     TEST SCANNER I2C (Pin Personalizzati) ");
  Serial.println("=========================================");
  Serial.print("Inizializzazione I2C su SDA: ");
  Serial.print(I2C_SDA_PIN);
  Serial.print(" | SCL: ");
  Serial.println(I2C_SCL_PIN);

  // Inizializza il bus I2C con i pin specifici al posto di quelli di default (21, 22)
  if(!Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN)) {
    Serial.println("ERRORE CRITICO: Impossibile inizializzare il bus I2C su questi pin.");
    Serial.println("I pin 6, 7, 8, 9, 10 e 11 sono solitamente connessi alla memoria Flash SPI interna sull'ESP32 e NON DEVONO ESSERE USATI.");
    while(1); // Blocca in caso di errore
  }
}

void loop() {
  byte error, address;
  int nDevices;

  Serial.println("\nScansione del bus I2C avviata...");

  nDevices = 0;
  for(address = 1; address < 127; address++ ) {
    // La funzione endTransmission ritorna 0 se il dispositivo risponde con un ACK
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Dispositivo I2C trovato all'indirizzo 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.print(address, HEX);
      Serial.println(" !");

      // Salva l'indirizzo tipico dei display LCD I2C
      if (address == 0x27 || address == 0x3F) {
        Serial.println("  -> Sembra essere un modulo display LCD!");
      }
      nDevices++;
    }
    else if (error == 4) {
      Serial.print("Errore sconosciuto all'indirizzo 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
    }
  }

  if (nDevices == 0) {
    Serial.println("Nessun dispositivo I2C trovato sul bus.");
    Serial.println("Controlla i collegamenti fisici a VCC, GND, SDA e SCL.");
  } else {
    Serial.println("Scansione completata.");
  }

  delay(5000); // Ripete la scansione ogni 5 secondi
}
