# 🏠 Casa di Quartiere Tuturano — AI Telegram Bot

> Assistente conversazionale in italiano su Telegram, basato su RAG (Retrieval-Augmented Generation), completamente self-hosted.

---

## 📋 Panoramica

Questo sistema è un assistente AI integrato con **Telegram** per la Casa di Quartiere di Tuturano (Brindisi, Puglia). Risponde alle domande dei cittadini su: orari, spazi, corsi, costi, contatti e procedure di prenotazione.

### Architettura

```
Cittadino Telegram
       ↓
  Telegram Bot API (polling o webhook)
       ↓
  FastAPI Server (locale)
       ↓
  Pipeline RAG:
  ├── Embedding (paraphrase-multilingual-MiniLM)
  ├── Retrieval (ChromaDB)
  └── Generation (Gemma 3 12B via Ollama)
       ↓
  Risposta → Telegram → Cittadino
```

### Stack Tecnologico

| Componente | Tecnologia |
|-----------|-----------|
| LLM | Gemma 3 12B (via Ollama) |
| Embedding | paraphrase-multilingual-MiniLM-L12-v2 |
| Vector DB | ChromaDB |
| Backend | FastAPI (Python) |
| Bot | python-telegram-bot 21.x |
| Dashboard | HTML/CSS/JS + Jinja2 |

### Vantaggi rispetto a WhatsApp

- ✅ **Setup immediato**: basta creare un bot con @BotFather (2 minuti)
- ✅ **Nessun tunnel**: modalità polling, niente Cloudflare/ngrok
- ✅ **Nessun account business**: non serve Meta Business
- ✅ **Gratuito**: nessun costo per messaggio
- ✅ **Comandi**: menu comandi integrato nell'interfaccia Telegram
- ✅ **Nessun limite**: nessuna restrizione sul numero di messaggi

---

## 🚀 Setup Rapido

### 1. Crea il Bot Telegram

1. Apri Telegram e cerca **@BotFather**
2. Invia `/newbot`
3. Scegli un nome (es: `Casa di Quartiere Tuturano`)
4. Scegli un username (es: `casa_quartiere_tuturano_bot`)
5. Copia il **token** che ricevi

### 2. Installazione

```bash
cd casa_quartiere_bot

# Crea ambiente virtuale
python -m venv venv
source venv/bin/activate  # Linux/Mac

# Installa dipendenze
pip install -r requirements.txt

# Configura .env (il token è già inserito se hai seguito il setup)
cp .env.example .env
nano .env    # Inserisci il tuo token Telegram

# Verifica setup
python scripts/setup.py
```

### 3. Scarica il modello LLM

```bash
# Avvia Ollama (in un terminale separato)
ollama serve

# Scarica il modello
ollama pull gemma3:12b

# Oppure, per un modello più veloce:
# ollama pull gemma3:4b
```

### 4. Carica il Knowledge Base

```bash
# Valida i file JSON
python scripts/load_kb.py --validate

# Carica tutto nel database vettoriale
python scripts/load_kb.py

# Verifica le statistiche
python scripts/load_kb.py --stats
```

### 5. Avvia il Sistema

```bash
# Avvia server + bot Telegram
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Il bot Telegram si avvierà automaticamente in modalità polling!
# La dashboard sarà disponibile su http://localhost:8000
```

---

## 🤖 Comandi Telegram

Il bot supporta questi comandi (visibili nel menu Telegram):

| Comando | Descrizione |
|---------|------------|
| `/start` | 🏠 Messaggio di benvenuto |
| `/aiuto` | 📋 Mostra tutti i comandi |
| `/info` | ℹ️ Informazioni generali |
| `/orari` | 🕐 Orari di apertura |
| `/corsi` | 📚 Corsi e attivita' |
| `/spazi` | 📍 Spazi disponibili |
| `/costi` | 💰 Costi e tariffe |
| `/contatti` | 📞 Contatti e referenti |
| `/prenota` | 📝 Come prenotare |
| `/regole` | 📋 Regolamento |
| `/eventi` | 🎉 Eventi in programma |

Oltre ai comandi, il bot risponde a **qualsiasi domanda in linguaggio naturale**.

---

## 📊 Dashboard di Gestione

Accedi alla dashboard: `http://localhost:8000/`
- Username: `admin` (configurabile in `.env`)
- Password: `changeme_immediately` (configurabile in `.env`)

La dashboard permette di:
- 📈 Vedere statistiche in tempo reale
- 📚 Gestire il Knowledge Base (aggiungere/rimuovere entries)
- 🧪 Testare il bot senza Telegram
- 📋 Monitorare le conversazioni recenti
- 🔗 Link diretto al bot Telegram

---

## 📚 Knowledge Base

### Struttura File

```
knowledge_base/entries/
├── informazioni_generali.json   # Info base, orari, mission
├── spazi.json                   # Sale, aule, dotazioni
├── corsi_attivita.json          # Corsi, laboratori, programmi
├── costi_tariffe.json           # Prezzi, pagamenti
├── contatti.json                # Telefono, email, social
├── prenotazioni.json            # Procedure prenotazione
├── regolamento.json             # Regole, norme
└── eventi.json                  # Eventi, volontariato
```

### Aggiornare il Knowledge Base

1. **Via Dashboard**: `http://localhost:8000/kb` → form di aggiunta
2. **Via File JSON**: modifica i file e poi `python scripts/load_kb.py --reset`
3. **Via API**:
   ```bash
   curl -X POST http://localhost:8000/api/kb \
     -u admin:password \
     -F "categoria=informazioni_generali" \
     -F "domanda=Nuova domanda?" \
     -F "risposta=Nuova risposta."
   ```

---

## 🔌 API Endpoints

| Metodo | Endpoint | Descrizione |
|--------|---------|-------------|
| POST | `/telegram/webhook` | Webhook Telegram (solo modalità webhook) |
| GET | `/` | Dashboard principale |
| GET | `/kb` | Gestione Knowledge Base |
| GET | `/api/stats` | Statistiche JSON |
| GET | `/api/kb` | Lista entries KB |
| POST | `/api/kb` | Aggiungi entry |
| DELETE | `/api/kb/{id}` | Rimuovi entry |
| GET | `/api/search?q=...` | Test retrieval |
| POST | `/api/test` | Test pipeline completo |
| GET | `/health` | Health check |

---

## ⚙️ Modalità di Funzionamento

### Polling (default, consigliato)
Il bot interroga i server Telegram periodicamente. **Non richiede URL pubblico, tunnel o SSL.**
```env
TELEGRAM_MODE=polling
```

### Webhook (avanzato)
Telegram invia aggiornamenti al tuo server via HTTPS. Richiede un URL pubblico.
```env
TELEGRAM_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://tuodominio.com
```

---

## 📁 Struttura Progetto

```
casa_quartiere_bot/
├── app/
│   ├── __init__.py
│   ├── config.py          # Configurazione centralizzata
│   ├── main.py            # Server FastAPI + lifecycle bot
│   ├── models.py          # Modelli dati Pydantic
│   ├── rag.py             # Pipeline RAG completo
│   ├── telegram_bot.py    # Bot Telegram (handler e comandi)
│   └── analytics.py       # Tracking conversazioni
├── knowledge_base/
│   └── entries/           # File JSON knowledge base
├── scripts/
│   ├── setup.py           # Verifica setup
│   └── load_kb.py         # Caricamento knowledge base
├── static/
│   ├── css/               # Stili dashboard
│   └── js/                # JavaScript dashboard
├── templates/
│   ├── dashboard.html     # Dashboard principale
│   └── kb_manager.html    # Gestione knowledge base
├── .env                   # Configurazione (non committare!)
├── .env.example           # Template configurazione
├── requirements.txt       # Dipendenze Python
└── README.md              # Questa guida
```

---

## 🏁 Checklist per il Go-Live

- [ ] Orari di apertura ufficiali inseriti nel KB
- [ ] Elenco completo spazi con capienza e dotazioni
- [ ] Catalogo corsi aggiornato con costi e orari
- [ ] Contatti reali (telefono, email) inseriti
- [ ] Regolamento interno caricato
- [ ] Bot Telegram creato con @BotFather
- [ ] Test con almeno 20 domande tipiche
- [ ] Approvazione del responsabile della struttura
- [ ] Password dashboard cambiata
- [ ] Monitoraggio attivo (health check)

---

*Piano redatto per la Casa di Quartiere di Tuturano — Tuturano (BR), Puglia*
