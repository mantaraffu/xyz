#include <WiFi.h>

const char* ssid = "VF_IT_FWA_531F"; 
const char* password = "5yJAQaB5A557AdeD";

void setup() {
  Serial.begin(115200);
  delay(3000); 
  
  Serial.println("\n--- TENTATIVO CON BSSID FORZATO E CANALE ---");
  
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // Disabilita power-saving

  // Se conosciamo il MAC Address (BSSID) del router per la rete 2.4GHz e il Canale,  
  // potremmo forzarli qui. Per ora, facciamo una scansione per trovarli e poi tentiamo di connetterci mirati.
  
  int n = WiFi.scanNetworks();
  if (n == 0) {
      Serial.println("Nessuna rete trovata.");
  } else {
      for (int i = 0; i < n; ++i) {
          if (String(WiFi.SSID(i)) == ssid) {
              Serial.print("Trovata rete: ");
              Serial.print(ssid);
              Serial.print(" su Canale: ");
              Serial.print(WiFi.channel(i));
              Serial.print(" con BSSID: ");
              Serial.println(WiFi.BSSIDstr(i));
              
              // Tentiamo la connessione forzando questo BSSID e Canale
              Serial.println("Avvio connessione mirata al BSSID e canale trovati...");
              WiFi.begin(ssid, password, WiFi.channel(i), WiFi.BSSID(i));
              break; // Ne tenta una, la prima che trova
          }
      }
  }

  int tentativi = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    tentativi++;
    if (tentativi >= 40) {
      Serial.println("\n[KO] Nulla da fare, la connessione viene comunque rifiutata.");
      return;
    }
  }

  Serial.print("\n[OK] CONNESSO! IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Lascia vuoto
}
