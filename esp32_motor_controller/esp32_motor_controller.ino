#include <WiFi.h>
#include <WebServer.h>
#include <AccelStepper.h>

// ==========================================
// CONFIGURAZIONE WIFI
// ==========================================
const char* ssid = "VF_IT_FWA_531F"; 
const char* password = "GalaHouse25!";

// ==========================================
// CONFIGURAZIONE MOTORE 28BYJ-48 + ULN2003
// ==========================================
// Tipo 8 = half-step a 4 fili (raccomandato per il 28BYJ-48)
#define motorInterfaceType 8
#define IN1 19
#define IN2 20
#define IN3 21
#define IN4 22
// CRITICO: La sequenza IN1, IN3, IN2, IN4 è OBBLIGATORIA per AccelStepper!
// (cioè: GPIO19, GPIO21, GPIO20, GPIO22)
AccelStepper stepper = AccelStepper(motorInterfaceType, IN1, IN3, IN2, IN4);

// ==========================================
// SERVER HTTP (Porta 80)
// ==========================================
WebServer server(80);

void handleRoot() {
  server.send(200, "text/plain", "ESP32 Motor Controller Online. Chiama /step per muovere il motore.");
}

void handleStep() {
  Serial.println(">>> Richiesta bot ricevuta! Movo il motore di 512 passi...");
  // 28BYJ-48 = 4096 passi per giro completo in half-step.
  // 512 passi = 1/8 di giro, visibilmente apprezzabile.
  stepper.move(512);
  server.send(200, "text/plain", "OK - Movimento in coda");
}

void setup() {
  Serial.begin(115200);
  delay(3000); // Pausa per aprire il Monitor Seriale

  // Configurazione velocità e accelerazione del motore
  stepper.setMaxSpeed(1000.0);
  stepper.setAcceleration(500.0);

  Serial.println("\n=================================");
  Serial.println("--- AVVIO SERVER ESP32 MOTOR ---");
  Serial.println("=================================");

  // Connessione WiFi con forzatura BSSID per bypassare il Band Steering di Vodafone
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // Disabilita power-saving WiFi

  Serial.println("Scansione reti in corso...");
  int n = WiFi.scanNetworks();
  bool reteTrovata = false;

  for (int i = 0; i < n; ++i) {
    if (String(WiFi.SSID(i)) == ssid) {
      Serial.print("Rete trovata! BSSID: ");
      Serial.print(WiFi.BSSIDstr(i));
      Serial.print("  Canale: ");
      Serial.println(WiFi.channel(i));
      // Forzatura sul BSSID specifico per evitare il rimbalzo tra 2.4 e 5 GHz
      WiFi.begin(ssid, password, WiFi.channel(i), WiFi.BSSID(i));
      reteTrovata = true;
      break;
    }
  }

  if (!reteTrovata) {
    Serial.println("BSSID non trovato, tentativo diretto...");
    WiFi.begin(ssid, password);
  }

  int tentativi = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    tentativi++;
    if (tentativi >= 40) {
      Serial.println("\n[ERRORE] Connessione fallita. Controlla SSID e password e riavvia.");
      return;
    }
  }

  Serial.println("\n[OK] CONNESSIONE STABILITA!");
  Serial.print(">>> Copia questo URL nel file .env come ESP32_MOTOR_URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/step");

  // Rotte per il server web
  server.on("/", handleRoot);
  server.on("/step", HTTP_GET, handleStep);

  server.begin();
  Serial.println("[OK] Server HTTP in ascolto su porta 80.");
}

void loop() {
  // Gestisce le richieste HTTP in arrivo
  server.handleClient();

  // Avanza il motore di un passo alla volta (non bloccante)
  stepper.run();
}
