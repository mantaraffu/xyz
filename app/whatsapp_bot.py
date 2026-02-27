"""
WhatsApp Cloud API — Modulo parallelo al bot Telegram.

Gestisce messaggi in arrivo dal webhook Meta e risponde
tramite l'API Graph di Meta (WhatsApp Cloud API v19).

Funzionalità:
  - Risposte AI tramite pipeline RAG (stesso motore di Telegram)
  - Wizard /gioco testuale con sessioni persistite su gioco/wa_sessions.json
  - Messaggi di testo e Interactive Messages (bottoni A/B per i sondaggi)

Attivazione:
  Impostare nel .env:
    WHATSAPP_TOKEN=<token>
    WHATSAPP_PHONE_NUMBER_ID=<id>
    WHATSAPP_VERIFY_TOKEN=<secret>

Webhook Meta:
  GET  /whatsapp/webhook  → verifica hub.challenge
  POST /whatsapp/webhook  → messaggi in arrivo
"""

import json
import logging
import os
import random
import time
import asyncio
from pathlib import Path
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# Costanti API
# ============================================================

_API_BASE = "https://graph.facebook.com/v19.0"
_SESSIONS_FILE = Path(__file__).resolve().parent.parent / "gioco" / "wa_sessions.json"

# ============================================================
# Stato wizard per sessione (persistito su file)
# Struttura: { "<wa_from>": {"step": "domanda"|"opzione_a"|"opzione_b", "draft": {...}} }
# ============================================================

def _load_sessions() -> dict:
    if not _SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sessions(sessions: dict) -> None:
    try:
        _SESSIONS_FILE.write_text(
            json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"❌ wa_sessions write error: {e}")


def _get_session(wa_from: str) -> Optional[dict]:
    return _load_sessions().get(wa_from)


def _set_session(wa_from: str, data: dict) -> None:
    sessions = _load_sessions()
    sessions[wa_from] = data
    _save_sessions(sessions)


def _clear_session(wa_from: str) -> None:
    sessions = _load_sessions()
    sessions.pop(wa_from, None)
    _save_sessions(sessions)


# ============================================================
# Esempi rotativi (stessi di gioco/wizard.py)
# ============================================================

_ESEMPI_DOMANDE = [
    "Di chi è quel cane che abbaia alle 3 di notte?",
    "Cosa faremo per l'ennesima buca in strada?",
    "Perché c'è sempre puzza di fritto di giovedì?",
    "Di chi è la colpa se piove proprio nel weekend?",
    "Che ne dite dell'ultima riunione di quartiere?",
    "Chi ha rubato la mia penna preferita?",
    "Perché la connessione Wi-Fi salta sul più bello?",
]
_ESEMPI_A = [
    "A dell'unico insonne",
    "A la difenderemo all'UNESCO",
    "A nonna Maria ha colpito ancora",
    "A di chi ha lavato l'auto oggi",
    "A ottima cura per l'insonnia",
    "A un trafficante di cancelleria",
    "A i criceti sul server sono cotti",
]
_ESEMPI_B = [
    "B di un demone in incognito",
    "B ci pianteremo dei gerani finti",
    "B lobby delle melanzane fritte",
    "B dei poteri forti, palesemente",
    "B peggio di un calcio sugli stinchi",
    "B è palesemente scappata da sola",
    "B i marziani ci stanno spiando",
]


def _pick() -> tuple[str, str, str]:
    idx = random.randrange(len(_ESEMPI_DOMANDE))
    return _ESEMPI_DOMANDE[idx], _ESEMPI_A[idx], _ESEMPI_B[idx]


# ============================================================
# Invio messaggi via Meta API
# ============================================================

async def _send_text(to: str, body: str) -> None:
    """Invia un messaggio di testo semplice via WhatsApp Cloud API."""
    url = f"{_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            logger.info(f"✅ WA → {to}: {body[:60]}...")
    except Exception as e:
        logger.error(f"❌ WA send_text error ({to}): {e}")


async def _send_buttons(to: str, body: str, buttons: list[dict]) -> None:
    """
    Invia un Interactive Message con bottoni (max 3).
    buttons: [{"id": "...", "title": "..."}]
    """
    url = f"{_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                    for b in buttons
                ]
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            logger.info(f"✅ WA buttons → {to}")
    except Exception as e:
        logger.error(f"❌ WA send_buttons error ({to}): {e}")


async def _send_list_message(to: str, header: str, body: str, button_label: str, rows: list[dict]) -> None:
    """
    Invia un List Message (menu a scorrimento, max 10 voci).
    rows: [{"id": "...", "title": "...", "description": "..."}]
    """
    url = f"{_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body":   {"text": body},
            "action": {
                "button": button_label,
                "sections": [{
                    "title": "Scegli un'opzione",
                    "rows": [
                        {"id": r["id"], "title": r["title"][:24], "description": r.get("description", "")[:72]}
                        for r in rows
                    ],
                }],
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            logger.info(f"✅ WA list → {to}")
    except Exception as e:
        logger.error(f"❌ WA send_list error ({to}): {e}")


async def _send_main_menu(to: str) -> None:
    """Invia il menu principale come List Message."""
    await _send_list_message(
        to=to,
        header="🏠 Casa di Quartiere Tuturano",
        body="Sono tutulacchi, l'assistente virtuale. Scegli un'opzione dal menu oppure scrivimi direttamente la tua domanda!",
        button_label="📋 Apri menu",
        rows=[
            {"id": "wa_menu_info",    "title": "ℹ️ Info", "description": "Informazioni generali, orari di apertura e contatti"},
            {"id": "wa_menu_corsi",   "title": "📚 Corsi e attività",       "description": "Corsi, laboratori e attività disponibili"},
            {"id": "wa_menu_spazi",   "title": "📍 Spazi disponibili",      "description": "Sala riunioni, spazi comuni e prenotazioni"},
            {"id": "wa_menu_costi",   "title": "💰 Costi e tariffe",        "description": "Prezzi e tariffe per spazi e corsi"},
            {"id": "wa_menu_prenota", "title": "📝 Come prenotare",         "description": "Procedura di prenotazione degli spazi"},
            {"id": "wa_menu_regole",  "title": "📋 Regolamento",            "description": "Regole di comportamento e utilizzo"},
            {"id": "wa_menu_eventi",  "title": "🎉 Eventi",                 "description": "Prossimi eventi in programma"},
            {"id": "wa_menu_gioco",   "title": "🎯 Gioca",  "description": "Partecipa o crea un sondaggio per la comunità"},
        ],
    )


# ============================================================
# Wizard gioco su WhatsApp
# ============================================================

async def _handle_gioco_wizard(wa_from: str, user_text: str, session: dict) -> None:
    """Gestisce i passi del wizard sondaggio per WhatsApp."""
    from gioco.storage import save_quiz, get_active_quiz, save_answer, get_quiz_by_id

    step = session.get("step")
    draft = session.get("draft", {})

    if step == "domanda":
        domanda = user_text.strip()
        if len(domanda) < 5:
            await _send_text(wa_from, "⚠️ La domanda è troppo corta. Scrivila di nuovo.")
            return
        if len(domanda) > 300:
            await _send_text(wa_from, "⚠️ La domanda è troppo lunga (max 300 caratteri).")
            return
        draft["domanda"] = domanda
        es_a = session.get("esempi", {}).get("a", "A la prima opzione")
        _set_session(wa_from, {"step": "opzione_a", "draft": draft, "esempi": session.get("esempi", {})})
        await _send_text(wa_from,
            f"✅ {domanda}\n\n"
            f"🅰️ Scrivi la prima opzione\nes. {es_a}"
        )

    elif step == "opzione_a":
        risposta_a = user_text.strip()
        if not risposta_a or len(risposta_a) > 150:
            await _send_text(wa_from, "⚠️ Opzione non valida (max 150 caratteri).")
            return
        draft["risposta_a"] = risposta_a
        es_b = session.get("esempi", {}).get("b", "B la seconda opzione")
        _set_session(wa_from, {"step": "opzione_b", "draft": draft, "esempi": session.get("esempi", {})})
        await _send_text(wa_from,
            f"✅ {risposta_a}\n\n"
            f"🅱️ Scrivi la seconda opzione\nes. {es_b}"
        )

    elif step == "opzione_b":
        risposta_b = user_text.strip()
        if not risposta_b or len(risposta_b) > 150:
            await _send_text(wa_from, "⚠️ Opzione non valida (max 150 caratteri).")
            return
        draft["risposta_b"] = risposta_b
        _set_session(wa_from, {"step": "conferma", "draft": draft})
        await _send_buttons(
            to=wa_from,
            body=(
                f"📋 Riepilogo — Conferma?\n\n"
                f"❓ {draft['domanda']}\n\n"
                f"🅰️ {draft['risposta_a']}\n"
                f"🅱️ {draft['risposta_b']}"
            ),
            buttons=[
                {"id": "wa_pubblica", "title": "✅ Pubblica"},
                {"id": "wa_annulla",  "title": "❌ Annulla"},
            ],
        )

    elif step == "conferma":
        # L'utente ha risposto a testo invece di premere un bottone
        await _send_text(wa_from,
            "👆 Usa i bottoni per confermare o annullare il sondaggio."
        )


async def _start_gioco(wa_from: str) -> None:
    """Avvia il wizard di creazione sondaggio o mostra quello attivo."""
    from gioco.storage import get_active_quiz, _load_db
    from datetime import datetime, timezone, timedelta
    quiz = get_active_quiz()

    if quiz is not None:
        voti_a = quiz.get("voti_a", 0)
        voti_b = quiz.get("voti_b", 0)
        
        # Calcolo scadenze e coda
        db = _load_db()
        coda_count = sum(1 for q in db["quizzes"] if not q.get("attivo", False) and q.get("attivo_dal") is None)
        coda_text = f"\n⏳ In coda: {coda_count} sondaggi" if coda_count > 0 else ""
        
        scadenza_text = ""
        attivo_dal_str = quiz.get("attivo_dal")
        if attivo_dal_str:
            try:
                attivo_dal = datetime.strptime(attivo_dal_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                days_left = 7 - (now - attivo_dal).days
                if days_left > 0:
                    scadenza_text = f" (Scade tra {days_left} giorni)"
                else:
                    scadenza_text = " (Scade a breve)"
            except ValueError:
                pass
                
        await _send_buttons(
            to=wa_from,
            body=(
                f"📊 Sondaggio attivo #{quiz['id']}{scadenza_text}\n\n"
                f"❓ {quiz['domanda']}\n\n"
                f"🅰️ {quiz['risposta_a']} — {voti_a} voti\n"
                f"🅱️ {quiz['risposta_b']} — {voti_b} voti\n{coda_text}\n\n"
                "Scegli o proponi un nuovo sondaggio."
            ),
            buttons=[
                {"id": f"wa_voto_a:{quiz['id']}", "title": f"🅰️ {quiz['risposta_a'][:18]}"},
                {"id": f"wa_voto_b:{quiz['id']}", "title": f"🅱️ {quiz['risposta_b'][:18]}"},
                {"id": "wa_crea_nuovo", "title": "✏️ Crea nuovo"},
            ],
        )
        return

    # Nessun sondaggio attivo → avvia creazione
    es_d, es_a, es_b = _pick()
    _set_session(wa_from, {
        "step": "domanda",
        "draft": {},
        "esempi": {"domanda": es_d, "a": es_a, "b": es_b},
    })
    await _send_text(wa_from,
        "📋 Poni una domanda alla comunità di Tuturano\n\n"
        "La domanda verrà proiettata sulla bacheca esterna e i risultati "
        "saranno visibili a tutta la comunità.\n\n"
        f"✏️ Scrivi la domanda\nes. {es_d}\n\n"
        "Scrivi 'annulla' per uscire in qualsiasi momento."
    )


# ============================================================
# Entry point principale — chiamato da main.py per ogni POST
# ============================================================

async def handle_whatsapp_message(data: dict, rag_pipeline) -> None:
    """
    Analizza il payload JSON in arrivo dal webhook Meta e risponde.
    Supporta testo libero, interactive button replies.
    """
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
    except (KeyError, IndexError):
        return  # ping / status update, niente da fare

    # Messaggi in arrivo
    messages = value.get("messages", [])
    for msg in messages:
        wa_from = msg.get("from", "")
        msg_type = msg.get("type", "")

        # ── Testo libero ──────────────────────────────────────
        if msg_type == "text":
            user_text = msg.get("text", {}).get("body", "").strip()
            if not user_text:
                continue

            logger.info(f"📩 WA {wa_from}: '{user_text[:80]}'")

            # Annullamento globale
            if user_text.lower() in {"annulla", "cancel", "/annulla"}:
                _clear_session(wa_from)
                await _send_text(wa_from, "❌ Operazione annullata. Scrivi 'gioco' per iniziare.")
                continue

            # Comando gioco
            if user_text.lower() in {"gioco", "/gioco"}:
                await _start_gioco(wa_from)
                continue

            # Wizard attivo
            session = _get_session(wa_from)
            if session:
                await _handle_gioco_wizard(wa_from, user_text, session)
                continue

            # Saluti / menu
            menu_triggers = {"ciao", "buongiorno", "buonasera", "salve", "hey", "hello", "hi",
                             "menu", "aiuto", "help", "start", "/start", "/aiuto"}
            if user_text.lower() in menu_triggers:
                await _send_main_menu(wa_from)
                continue

            # RAG — risposta AI
            if not rag_pipeline:
                await _send_text(wa_from, "⚠️ Sistema in avvio. Riprova tra qualche secondo.")
                continue

            start_t = time.time()
            result = await asyncio.to_thread(rag_pipeline.answer, user_text)
            elapsed = (time.time() - start_t) * 1000
            response_text = result.get("risposta", "Mi dispiace, non ho trovato una risposta.")

            # WA ha limite ~65535 chars, ma tagliamo a 4000 per leggibilità
            if len(response_text) > 4000:
                response_text = response_text[:3997] + "..."

            await _send_text(wa_from, response_text)
            logger.info(f"✅ WA risposta in {elapsed:.0f}ms")

        # ── Interactive button reply ───────────────────────────
        elif msg_type == "interactive":
            # Legge sia button_reply (bottoni A/B) che list_reply (voci menu)
            interactive = msg.get("interactive", {})
            btn_id = (
                interactive.get("button_reply", {}).get("id", "")
                or interactive.get("list_reply", {}).get("id", "")
            )
            logger.info(f"🔘 WA interactive {wa_from}: {btn_id}")

            # ── Selezioni dal menu principale ─────────────────
            _MENU_QUERIES = {
                "wa_menu_info":    [
                    ("ℹ️ Informazioni generali", "Cos'e' la Casa di Quartiere di Tuturano e cos'è l'Associazione IL CURRO-APS?"),
                    ("🕐 Orari di apertura",     "Quali sono gli orari di apertura della Casa di Quartiere?"),
                    ("📞 Contatti",             "Come posso contattare la Casa di Quartiere e l'Associazione IL CURRO-APS?"),
                    ("🗺️ Come raggiungere", "Come arrivare alla Casa di Quartiere di Tuturano?"),
                ],
                "wa_menu_corsi":   [("📚 Corsi e attività", "Quali corsi e attivita' sono disponibili alla Casa di Quartiere e quali attività svolge IL CURRO-APS?")],
                "wa_menu_spazi":   [("📍 Spazi",            "Quali spazi sono disponibili nella Casa di Quartiere e per IL CURRO-APS?")],
                "wa_menu_costi":   [("💰 Costi",            "Quanto costa utilizzare gli spazi o iscriversi ai corsi della Casa di Quartiere e quali sono i costi de IL CURRO-APS?")],
                "wa_menu_prenota": [("📝 Prenotazione",     "Come prenoto uno spazio alla Casa di Quartiere o mi prenoto per un'iniziativa de IL CURRO-APS?")],
                "wa_menu_regole":  [("📋 Regolamento",      "Quali sono le regole di comportamento e quali valori guidano IL CURRO-APS?")],
                "wa_menu_eventi":  [("🎉 Eventi",            "Quali eventi ci sono alla Casa di Quartiere e che iniziative organizza IL CURRO-APS?")],
            }

            if btn_id in _MENU_QUERIES and rag_pipeline:
                queries = _MENU_QUERIES[btn_id]
                parts = []
                for title, q in queries:
                    result = await asyncio.to_thread(rag_pipeline.answer, q)
                    parts.append(f"{title}\n{result['risposta']}")
                response = "\n\n".join(parts)
                if len(response) > 4000:
                    response = response[:3997] + "..."
                await _send_text(wa_from, response)
                continue

            if btn_id == "wa_menu_gioco":
                await _start_gioco(wa_from)
                continue

            if btn_id == "wa_crea_nuovo":
                _clear_session(wa_from)
                await _start_gioco(wa_from)

            elif btn_id == "wa_pubblica":
                session = _get_session(wa_from)
                if session and session.get("step") == "conferma":
                    from gioco.storage import save_quiz
                    draft = session["draft"]
                    quiz_id = save_quiz(
                        domanda=draft["domanda"],
                        risposta_a=draft["risposta_a"],
                        risposta_b=draft["risposta_b"],
                        created_by=int(wa_from) if wa_from.isdigit() else 0,
                        created_by_name=wa_from,
                    )
                    _clear_session(wa_from)
                    await _send_text(wa_from,
                        f"🎉 Sondaggio #{quiz_id} pubblicato!\n\n"
                        "Scrivi 'gioco' per votare o crearne un altro."
                    )
                else:
                    await _send_text(wa_from, "⚠️ Nessun sondaggio in attesa di conferma.")

            elif btn_id == "wa_annulla":
                _clear_session(wa_from)
                await _send_text(wa_from, "❌ Sondaggio annullato. Scrivi 'gioco' per ricominciare.")

            elif btn_id.startswith("wa_voto_a:") or btn_id.startswith("wa_voto_b:"):
                from gioco.storage import get_quiz_by_id, save_answer
                from gioco.motor import trigger_motor
                import asyncio

                try:
                    side, quiz_id_str = btn_id.split(":", 1)
                    quiz_id = int(quiz_id_str)
                except (ValueError, IndexError):
                    await _send_text(wa_from, "⚠️ Errore. Riprova.")
                    continue

                quiz = get_quiz_by_id(quiz_id)
                if not quiz:
                    await _send_text(wa_from, "⚠️ Sondaggio non trovato.")
                    continue

                scelta = "A" if side == "wa_voto_a" else "B"
                testo = quiz["risposta_a"] if scelta == "A" else quiz["risposta_b"]
                steps = 512 if scelta == "A" else -512

                saved = save_answer(
                    quiz_id=quiz_id,
                    scelta=scelta,
                    testo_scelta=testo,
                )

                asyncio.create_task(trigger_motor(steps=steps))
                await _send_text(wa_from,
                    f"✅ Voto registrato!\n\n"
                    f"❓ {quiz['domanda']}\n"
                    f"👉 Hai scelto: {scelta} — {testo}\n\n"
                    f"Grazie per aver partecipato! 🙌"
                )
