// ==========================================
// TEST ESP32 LDR (Sensori di luce - DIGITALI)
// ==========================================

// Pin digitali a cui sono collegati i sensori LDR
const int LDR_PIN_1 = 5; 
const int LDR_PIN_2 = 4;

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("=========================================");
  Serial.println("   TEST SENSORI LDR (DIGITALI) - AVVIO   ");
  Serial.println("=========================================");
  Serial.println("Usa il Monitor Seriale (baud: 115200) per leggere i valori.");
  Serial.println("Copri e scopri i sensori per vedere la variazione (0 o 1).\n");

  // Imposta i pin come INPUT
  pinMode(LDR_PIN_1, INPUT);
  pinMode(LDR_PIN_2, INPUT);
}

void loop() {
  // Legge lo stato digitale dei pin (HIGH/LOW ovvero 1/0)
  int statoLDR1 = digitalRead(LDR_PIN_1);
  int statoLDR2 = digitalRead(LDR_PIN_2);

  // Stampa i valori sul Monitor Seriale
  Serial.print("Sensore 1 (Pin ");
  Serial.print(LDR_PIN_1);
  Serial.print("): ");
  Serial.print(statoLDR1);
  
  Serial.print("   |   Sensore 2 (Pin ");
  Serial.print(LDR_PIN_2);
  Serial.print("): ");
  Serial.println(statoLDR2);

  // Pausa di 500ms per non intasare il monitor seriale
  delay(500);
}
