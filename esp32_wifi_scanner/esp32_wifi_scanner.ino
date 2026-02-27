#include "WiFi.h"

void setup()
{
  Serial.begin(115200);
  delay(3000); // Wait for Serial Monitor to open (especially for ESP32-C6 with native USB)

  // Set WiFi to station mode and disconnect from an AP if it was previously connected
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  Serial.println("Inizializzazione completata");
}

void loop()
{
  Serial.println("Inizio scansione reti Wi-Fi...");

  // WiFi.scanNetworks will return the number of networks found
  int n = WiFi.scanNetworks();
  Serial.println("Scansione terminata");
  
  if (n == 0) {
      Serial.println("Nessuna rete Wi-Fi trovata.");
  } else {
    Serial.print(n);
    Serial.println(" reti trovate:");
    for (int i = 0; i < n; ++i) {
      // Stampa l'Ssid e l'RSSI (potenza del segnale) per ogni rete
      Serial.print(i + 1);
      Serial.print(": ");
      Serial.print(WiFi.SSID(i));
      Serial.print(" (");
      Serial.print(WiFi.RSSI(i));
      Serial.print(")");
      Serial.println((WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? " " : " *");
      delay(10);
    }
  }
  Serial.println("");

  // Aspetta 5 secondi prima di ripetere la scansione
  delay(5000);
}
