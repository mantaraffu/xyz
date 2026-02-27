/*
 * ESP32 Quiz Motor Controller — con AccelStepper
 * ============================================================
 * Motore : 28BYJ-48 + driver ULN2003
 * Libreria: AccelStepper (half-step, tipo 8)
 *
 * Endpoint HTTP:
 *   GET /            → stato del server
 *   GET /step        → muove di 512 passi avanti (compatibilità bot principale)
 *   GET /move?steps=N → muove di N half-steps (N>0=avanti, N<0=indietro)
 *
 * Pin ULN2003 → ESP32:
 *   IN1 → GPIO 19
 *   IN2 → GPIO 20
 *   IN3 → GPIO 21
 *   IN4 → GPIO 22
 *
 * NOTA: AccelStepper richiede l'ordine IN1, IN3, IN2, IN4 nel costruttore.
 */

#include <WiFi.h>
#include <WebServer.h>
#include <AccelStepper.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ============================================================
// CONFIGURAZIONE WIFI
// ============================================================
const char* ssid     = "VF_IT_FWA_531F";
const char* password = "GalaHouse25!";

// ============================================================
// CONFIGURAZIONE MOTORE 28BYJ-48
// ============================================================
#define MOTOR_INTERFACE_TYPE 8  // Half-step 4 fili

// Pin fisici ULN2003 → ESP32
#define IN1 19
#define IN2 20
#define IN3 21
#define IN4 22

// Ordine obbligatorio per AccelStepper + 28BYJ-48: IN1, IN3, IN2, IN4
AccelStepper stepper(MOTOR_INTERFACE_TYPE, IN1, IN3, IN2, IN4);

// Velocità e accelerazione
const float MAX_SPEED    = 800.0;   // step/s (max affidabile per 28BYJ-48)
const float ACCELERATION = 400.0;   // step/s²

// Limiti
const int LEGACY_STEPS = 68;       // passi per /step (1/30 di mezzo giro)
const int MAX_STEPS    = 8192;      // limite sicurezza per /move (2 giri)

// ============================================================
// CONFIGURAZIONE SENSORI LDR
// ============================================================
const int LDR_PIN_1 = 5;
const int LDR_PIN_2 = 4;

// IMPORTANTE: Imposta qui lo stato che consideri "VOTATO"
// Se coprendo il sensore l'output sullo sketch di test era '0', usa LOW. 
// Se l'output coperto era '1', usa HIGH.
const int TRIGGER_STATE = LOW;

volatile int pendingVotesA = 0;
volatile int pendingVotesB = 0;

int lastLdrState1 = -1; 
int lastLdrState2 = -1;
unsigned long lastVoteTime = 0;
const unsigned long VOTE_COOLDOWN = 3000; // 3 secondi di pausa per evitare voti multipli istantanei

// ============================================================
// CONFIGURAZIONE LCD 1602 I2C
// ============================================================
LiquidCrystal_I2C lcd(0x27, 16, 2); 
const int I2C_SDA_PIN = 6;
const int I2C_SCL_PIN = 7;

// Testi correnti sul display
String quizText = "Attesa quiz...";
String ans1Text = "Pronto";
String ans2Text = "online";

String qLine1 = "Attesa quiz...";
String qLine2 = "";
bool scrollQ = false;
bool scrollA1 = false;
bool scrollA2 = false;

unsigned long lastLcdUpdate = 0;
bool showQuestion = true;
const unsigned long LCD_PAGE_INTERVAL = 4000; // Scambia pagina ogni 4 secondi
unsigned long lastPageSwap = 0;

const unsigned long SCROLL_INTERVAL = 400; // Avanza lo scorrimento ogni 400ms
int scrollPosQ = 0;
int scrollPosA1 = 0;
int scrollPosA2 = 0;

void formatQuestion() {
  scrollQ = false;
  qLine1 = "";
  qLine2 = "";
  
  int len = quizText.length();
  if (len <= 16) {
    qLine1 = quizText;
  } else if (len <= 32) {
    int splitIdx = -1;
    for (int i = min(16, len - 1); i >= 0; i--) {
      if (quizText[i] == ' ') {
        splitIdx = i;
        break;
      }
    }
    
    if (splitIdx > 0) {
      String firstPart = quizText.substring(0, splitIdx);
      String secondPart = quizText.substring(splitIdx + 1); // skip space
      if (firstPart.length() <= 16 && secondPart.length() <= 16) {
        qLine1 = firstPart;
        qLine2 = secondPart;
      } else {
        scrollQ = true;
      }
    } else {
      scrollQ = true;
    }
  } else {
    scrollQ = true;
  }
}


// ============================================================
// SERVER HTTP
// ============================================================
WebServer server(80);

// -------- Handler: GET / -----------------------------------
void handleRoot() {
  String body  = "ESP32 Quiz Motor (AccelStepper) — Online\n\n";
  body += "Endpoint:\n";
  body += "  GET /step           -> " + String(LEGACY_STEPS) + " passi avanti\n";
  body += "  GET /move?steps=N   -> N half-steps (neg=indietro, max=" + String(MAX_STEPS) + ")\n\n";
  body += "Posizione attuale: " + String(stepper.currentPosition()) + " steps\n";
  body += "Velocita' max: " + String(MAX_SPEED) + " step/s\n";
  server.send(200, "text/plain", body);
}

// -------- Handler: GET /step (compatibilità bot) ----------
void handleStep() {
  Serial.println(">>> /step: " + String(LEGACY_STEPS) + " passi avanti");
  
  stepper.enableOutputs();
  stepper.move(LEGACY_STEPS);
  
  server.send(200, "text/plain", "OK - /step: " + String(LEGACY_STEPS) + " passi impostati");
}

// -------- Handler: GET /move?steps=N ----------------------
void handleMove() {
  if (!server.hasArg("steps")) {
    server.send(400, "text/plain", "ERRORE: parametro 'steps' mancante. Usa /move?steps=N");
    return;
  }

  String raw   = server.arg("steps");
  long   steps = raw.toInt();

  if (steps == 0 && raw != "0") {
    server.send(400, "text/plain", "ERRORE: valore non numerico: " + raw);
    return;
  }
  if (abs(steps) > MAX_STEPS) {
    server.send(400, "text/plain",
      "ERRORE: troppi passi (" + String(steps) + "). Max: " + String(MAX_STEPS));
    return;
  }

  String verso = (steps >= 0) ? "avanti" : "indietro";
  Serial.println(">>> /move: " + String(steps) + " steps (" + verso + ")");

  stepper.enableOutputs();
  stepper.move(steps);

  server.send(200, "text/plain", "OK - Movimento impostato");
}

// -------- Handler: GET /quiz ------------------------------
void handleQuiz() {
  if (server.hasArg("q")) quizText = server.arg("q");
  if (server.hasArg("a1")) ans1Text = server.arg("a1");
  if (server.hasArg("a2")) ans2Text = server.arg("a2");
  
  formatQuestion();
  
  scrollA1 = (ans1Text.length() > 16);
  scrollA2 = (ans2Text.length() > 16);
  
  // Aggiungi spazi alla fine per uno scorrimento continuo più leggibile
  if (scrollQ) quizText += "   ***   ";
  if (scrollA1) ans1Text += "   ***   ";
  if (scrollA2) ans2Text += "   ***   ";
  
  showQuestion = true;
  lastPageSwap = millis() - LCD_PAGE_INTERVAL; // Forza aggiornamento immediato al ricevimento
  scrollPosQ = 0;
  scrollPosA1 = 0;
  scrollPosA2 = 0;
  
  server.send(200, "text/plain", "OK - Quiz aggiornato su LCD");
}

// -------- Handler: GET /poll_votes ------------------------
void handlePollVotes() {
  String json = "{\"A\":" + String(pendingVotesA) + ",\"B\":" + String(pendingVotesB) + "}";
  pendingVotesA = 0;
  pendingVotesB = 0;
  server.send(200, "application/json", json);
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(2000);

  // Configura AccelStepper
  stepper.setMaxSpeed(MAX_SPEED);
  stepper.setAcceleration(ACCELERATION);
  stepper.disableOutputs(); // bobine spente finché non servono

  Serial.println("\n=========================================");
  Serial.println("  ESP32 QUIZ MOTOR (AccelStepper) — AVVIO");
  Serial.println("=========================================");
  Serial.println("  Pin: IN1=" + String(IN1) + " IN3=" + String(IN3) +
                 " IN2=" + String(IN2) + " IN4=" + String(IN4));
  Serial.println("  Velocita' max: " + String(MAX_SPEED) + " step/s");

  // Configura LDR come input
  pinMode(LDR_PIN_1, INPUT);
  pinMode(LDR_PIN_2, INPUT);
  Serial.println("  Sensori LDR configurati su pin " + String(LDR_PIN_1) + " e " + String(LDR_PIN_2));

  // Inizializza modulo LCD
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ESP32 Avvio...");
  lcd.setCursor(0, 1);
  lcd.print("Versione 1.0");

  // Test rapido al boot
  Serial.println("  Test motore (64 passi A/R)...");
  stepper.enableOutputs();
  stepper.move(64);
  while(stepper.distanceToGo() != 0) stepper.run();
  delay(300);
  stepper.move(-64);
  while(stepper.distanceToGo() != 0) stepper.run();
  stepper.disableOutputs();
  Serial.println("  Test completato.");

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  Serial.println("  Connessione WiFi in corso...");

  int  n     = WiFi.scanNetworks();
  bool found = false;
  for (int i = 0; i < n; ++i) {
    if (String(WiFi.SSID(i)) == ssid) {
      WiFi.begin(ssid, password, WiFi.channel(i), WiFi.BSSID(i));
      found = true;
      break;
    }
  }
  if (!found) WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (++attempts >= 40) {
      Serial.println("\n[ERRORE] WiFi non raggiunto. Riavvia.");
      return;
    }
  }

  Serial.println("\n[OK] WiFi connesso!");
  Serial.print("  IP assegnato: "); Serial.println(WiFi.localIP());

  server.on("/",     HTTP_GET, handleRoot);
  server.on("/step", HTTP_GET, handleStep);
  server.on("/move", HTTP_GET, handleMove);
  server.on("/quiz", HTTP_GET, handleQuiz);
  server.on("/poll_votes", HTTP_GET, handlePollVotes);
  server.begin();

  Serial.println("[OK] Server HTTP in ascolto sulla porta 80");
  
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Server HTTP OK");
  delay(1000);
}

// Funzione di utilità per stampare stringhe statiche e scorrevoli
void printLcdLine(int row, String text, int &pos, bool scroll) {
  lcd.setCursor(0, row);
  if (!scroll) {
    lcd.print(text);
    // Pulisce il resto della riga
    for(int i = text.length(); i < 16; i++) {
        lcd.print(" ");
    }
  } else {
    String disp = text.substring(pos, pos + 16);
    if (disp.length() < 16) { // wrap around
       disp += text.substring(0, 16 - disp.length());
    }
    lcd.print(disp);
    pos++;
    if (pos >= text.length()) {
       pos = 0;
    }
  }
}

// ============================================================
// LOOP 
// ============================================================
void loop() {
  server.handleClient();
  
  unsigned long now = millis();
  
  // Calcolo intervallo base o dinamico di pagina
  unsigned long currentInterval = LCD_PAGE_INTERVAL;
  if (showQuestion) {
      if (scrollQ) {
          int displayLen = quizText.length();
          currentInterval = displayLen * SCROLL_INTERVAL + 1500;
      }
  } else {
      if (scrollA1 || scrollA2) {
          unsigned int maxLen = ans1Text.length();
          if (ans2Text.length() > maxLen) maxLen = ans2Text.length();
          currentInterval = maxLen * SCROLL_INTERVAL + 1500;
      }
  }

  // Scambia pagina ogni currentInterval
  if (now - lastPageSwap > currentInterval) {
    showQuestion = !showQuestion;
    lastPageSwap = now;
    lcd.clear(); // Pulisci lo schermo al cambio pagina per evitare residui
    // Reset posizioni scorrimento quando cambia pagina
    scrollPosQ = 0;
    scrollPosA1 = 0;
    scrollPosA2 = 0;
  }
  
  // Aggiorna LCD ogni SCROLL_INTERVAL
  if (now - lastLcdUpdate > SCROLL_INTERVAL) {
    if (showQuestion) {
      if (scrollQ) {
         lcd.setCursor(0, 0);
         lcd.print("Domanda:        ");
         printLcdLine(1, quizText, scrollPosQ, true);
      } else {
         printLcdLine(0, qLine1, scrollPosQ, false);
         printLcdLine(1, qLine2, scrollPosQ, false);
      }
    } else {
      printLcdLine(0, ans1Text, scrollPosA1, scrollA1);
      printLcdLine(1, ans2Text, scrollPosA2, scrollA2);
    }
    lastLcdUpdate = now;
  }

  // --- GESTIONE MOTORE E SENSORI ---
  if (stepper.distanceToGo() != 0) {
    // Finché sta compiendo un movimento, lo esegue e basta
    stepper.run();
  } else {
    // Motore arrivato a destinazione: stacchiamo le bobine per non scaldare
    stepper.disableOutputs();

    // Quando non si muove, restiamo in ascolto dei sensori LDR
    int currentLdrState1 = digitalRead(LDR_PIN_1);
    int currentLdrState2 = digitalRead(LDR_PIN_2);

    // Controlliamo il Sensore 1
    if (currentLdrState1 == TRIGGER_STATE && lastLdrState1 != TRIGGER_STATE) {
      if (millis() - lastVoteTime > VOTE_COOLDOWN) {
        Serial.println(">>> VOTO: Sensore 1 attivato! (Pin " + String(LDR_PIN_1) + ")");
        pendingVotesA++;
        stepper.enableOutputs();
        stepper.move(LEGACY_STEPS); // 68 passi per "voto registrato"
        lastVoteTime = millis();
      }
    }

    // Controlliamo il Sensore 2
    if (currentLdrState2 == TRIGGER_STATE && lastLdrState2 != TRIGGER_STATE) {
      if (millis() - lastVoteTime > VOTE_COOLDOWN) {
        Serial.println(">>> VOTO: Sensore 2 attivato! (Pin " + String(LDR_PIN_2) + ")");
        pendingVotesB++;
        stepper.enableOutputs();
        stepper.move(-LEGACY_STEPS); // -68 passi per ruotare nell'altra direzione
        lastVoteTime = millis();
      }
    }

    // Aggiorniamo gli stati precedenti
    lastLdrState1 = currentLdrState1;
    lastLdrState2 = currentLdrState2;
  }
}
