#include <AccelStepper.h>

// ==========================================
// CONFIGURAZIONE PIN
// ==========================================
// Inserisci i pin a cui hai collegato gli IN1, IN2, IN3 e IN4 del driver ULN2003.
// Questi sono quelli ipotizzati basandoci sul codice precedente:
#define IN1 19
#define IN2 18
#define IN3 5
#define IN4 17

// ==========================================
// INIZIALIZZAZIONE MOTORE
// ==========================================
// Il tipo "8" indica un motore controllato a 4 fili (half-step), raccomandato per 28BYJ-48.
// ATTENZIONE: Per il 28BYJ-48 la sequenza corretta dei pin in AccelStepper è IN1, IN3, IN2, IN4!
AccelStepper stepper(8, IN1, IN3, IN2, IN4);

void setup() {
  Serial.begin(115200);
  delay(3000); // Pausa iniziale per far aprire il Monitor Seriale
  
  Serial.println("\n--- Test Motore Stepper 28BYJ-48 ---");
  
  // Il 28BYJ-48 è un motore demoltiplicato, quindi i valori di velocità
  // non devono essere troppo alti altrimenti salta passi o si blocca e fa solo rumore.
  stepper.setMaxSpeed(1000.0);
  stepper.setAcceleration(500.0);
}

void loop() {
  Serial.println("Comando: un giro in senso ORARIO...");
  // Il 28BYJ-48 ha di base circa 4096 passi per fare un giro completo dell'albero d'uscita in half-step.
  stepper.move(4096); 
  
  // Questa funzione blocca il codice finché il motore non ha raggiunto la destinazione
  while(stepper.distanceToGo() != 0) {
    stepper.run();
  }
  
  Serial.println("Arrivato! Pausa di 2 secondi.");
  delay(2000);
  
  Serial.println("Comando: mezzo giro in senso ANTIORARIO...");
  // Valore negativo per andare nella direzione opposta
  stepper.move(-2048); 
  
  while(stepper.distanceToGo() != 0) {
    stepper.run();
  }
  
  Serial.println("Arrivato! Pausa di 2 secondi.");
  delay(2000);
  
  Serial.println("--- Fine ciclo di test, ripeto... ---\n");
}
