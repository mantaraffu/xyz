"""
Gioco Wizard — unico punto d'accesso /gioco per i sondaggi comunitari.

/gioco (context-aware):
  • Nessun sondaggio attivo → avvia subito la creazione
  • Sondaggio attivo        → mostra il sondaggio con bottoni di voto
                              + pulsante "✏️ Crea nuovo sondaggio"

Flusso creazione:
  entry (comando /gioco o bottone "Crea nuovo")
    → [STEP_DOMANDA]    l'utente scrive la domanda
    → [STEP_RISPOSTA_A] prima opzione
    → [STEP_RISPOSTA_B] seconda opzione
    → [STEP_CONFERMA]   riepilogo + [✅ Pubblica] [❌ Annulla]

Motore ESP32:
  Opzione A → /move?steps=+512
  Opzione B → /move?steps=-512
"""

import asyncio
import logging
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from gioco.storage import (
    save_quiz,
    load_all_quizzes,
    save_answer,
    get_quiz_by_id,
    get_active_quiz,
    force_rotate_quiz,
)
from gioco.motor import trigger_motor, get_steps

logger = logging.getLogger(__name__)

# ============================================================
# Stati
# ============================================================
STEP_DOMANDA = 0
STEP_RISPOSTA_A = 1
STEP_RISPOSTA_B = 2
STEP_CONFERMA = 3

CB_PUBBLICA    = "gioco_pubblica"
CB_ANNULLA     = "gioco_annulla"
CB_CREA_NUOVO  = "gioco_crea_nuovo"
CB_RISPOSTA_A  = "gioco_risposta_a"
CB_RISPOSTA_B  = "gioco_risposta_b"

# ============================================================
# Esempi rotativi — indice scelto casualmente ad ogni sessione
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


def _start_creation_message(es_domanda: str) -> str:
    return (
        "📋 *Poni una domanda alla comunità di Tuturano*\n\n"
        "La domanda verrà proiettata sulla bacheca esterna e i risultati "
        "saranno visibili a tutta la comunità. Per ogni domanda proponi "
        "due opzioni: ogni voto muoverà il motore della bacheca.\n\n"
        f"✏️ *Scrivi la domanda*\n_es. {es_domanda}_\n\n"
        "_Digita /annulla per uscire in qualsiasi momento._"
    )


# ============================================================
# Entry point: /gioco  (context-aware)
# ============================================================

async def cmd_gioco(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Punto unico d'accesso: mostra sondaggio attivo o avvia creazione."""
    context.user_data.clear()
    
    # Importiamo qui per evitare dipendenze circolari all'avvio
    from gioco.storage import get_active_quiz, _load_db
    from datetime import datetime, timezone, timedelta
    
    quiz = get_active_quiz()

    if quiz is not None:
        # Mostra il sondaggio attivo con bottoni di voto + "Crea nuovo"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"🅰️ {quiz['risposta_a']}", callback_data=f"{CB_RISPOSTA_A}:{quiz['id']}"),
                InlineKeyboardButton(f"🅱️ {quiz['risposta_b']}", callback_data=f"{CB_RISPOSTA_B}:{quiz['id']}"),
            ],
            [
                InlineKeyboardButton("✏️ Crea nuovo sondaggio", callback_data=CB_CREA_NUOVO),
            ],
        ])
        voti_a = quiz.get("voti_a", 0)
        voti_b = quiz.get("voti_b", 0)
        
        # Calcolo scadenze e coda
        db = _load_db()
        coda_count = sum(1 for q in db["quizzes"] if not q.get("attivo", False) and q.get("attivo_dal") is None)
        coda_text = f"\n⏳ _In coda: {coda_count} sondagg{'io' if coda_count == 1 else 'i'}_\n" if coda_count > 0 else ""

        await update.message.reply_text(
            f"📊 *Sondaggio attivo \\#{quiz['id']}*\n\n"
            f"❓ {quiz['domanda']}\n\n"
            f"🅰️ {quiz['risposta_a']}\n"
            f"🅱️ {quiz['risposta_b']}\n{coda_text}\n"
            "_Scegli la tua risposta oppure proponi un nuovo sondaggio\\._",
            parse_mode="MarkdownV2",
            reply_markup=keyboard,
        )
        return ConversationHandler.END  # Non entra nel wizard

    # Nessun sondaggio attivo → avvia creazione
    es_d, es_a, es_b = _pick()
    context.user_data["quiz_draft"] = {}
    context.user_data["esempi"] = {"domanda": es_d, "a": es_a, "b": es_b}

    await update.message.reply_text(
        _start_creation_message(es_d),
        parse_mode="Markdown",
    )
    return STEP_DOMANDA


# ============================================================
# Entry point da bottone "Crea nuovo sondaggio"
# ============================================================

async def cmd_gioco_da_bottone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Avvia creazione sondaggio cliccando il bottone inline 'Crea nuovo'."""
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    es_d, es_a, es_b = _pick()
    context.user_data["quiz_draft"] = {}
    context.user_data["esempi"] = {"domanda": es_d, "a": es_a, "b": es_b}

    await query.message.reply_text(
        _start_creation_message(es_d),
        parse_mode="Markdown",
    )
    return STEP_DOMANDA


# ============================================================
# Passo 1: domanda
# ============================================================

async def step_domanda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    domanda = update.message.text.strip()
    if len(domanda) < 5:
        await update.message.reply_text("⚠️ La domanda è troppo corta.")
        return STEP_DOMANDA
    if len(domanda) > 300:
        await update.message.reply_text("⚠️ La domanda è troppo lunga (max 300 caratteri).")
        return STEP_DOMANDA

    context.user_data["quiz_draft"]["domanda"] = domanda
    es_a = context.user_data["esempi"]["a"]

    await update.message.reply_text(
        f"✅ *{domanda}*\n\n"
        f"🅰️ *Scrivi la prima opzione*\n_es. {es_a}_",
        parse_mode="Markdown",
    )
    return STEP_RISPOSTA_A


# ============================================================
# Passo 2: opzione A
# ============================================================

async def step_risposta_a(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    risposta_a = update.message.text.strip()
    if len(risposta_a) < 1:
        await update.message.reply_text("⚠️ L'opzione non può essere vuota.")
        return STEP_RISPOSTA_A
    if len(risposta_a) > 150:
        await update.message.reply_text("⚠️ Opzione troppo lunga (max 150 caratteri).")
        return STEP_RISPOSTA_A

    context.user_data["quiz_draft"]["risposta_a"] = risposta_a
    es_b = context.user_data["esempi"]["b"]

    await update.message.reply_text(
        f"✅ *{risposta_a}*\n\n"
        f"🅱️ *Scrivi la seconda opzione*\n_es. {es_b}_",
        parse_mode="Markdown",
    )
    return STEP_RISPOSTA_B


# ============================================================
# Passo 3: opzione B → riepilogo
# ============================================================

async def step_risposta_b(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    risposta_b = update.message.text.strip()
    if len(risposta_b) < 1:
        await update.message.reply_text("⚠️ L'opzione non può essere vuota.")
        return STEP_RISPOSTA_B
    if len(risposta_b) > 150:
        await update.message.reply_text("⚠️ Opzione troppo lunga (max 150 caratteri).")
        return STEP_RISPOSTA_B

    draft = context.user_data["quiz_draft"]
    draft["risposta_b"] = risposta_b

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Pubblica", callback_data=CB_PUBBLICA),
        InlineKeyboardButton("❌ Annulla",  callback_data=CB_ANNULLA),
    ]])

    await update.message.reply_text(
        "📋 *Riepilogo — Conferma?*\n\n"
        f"❓ *Domanda:*\n{draft['domanda']}\n\n"
        f"🅰️ *Opzione A:*\n{draft['risposta_a']}\n\n"
        f"🅱️ *Opzione B:*\n{draft['risposta_b']}\n\n"
        "Premi *Pubblica* per proiettare sulla bacheca.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return STEP_CONFERMA


# ============================================================
# Passo 4: conferma
# ============================================================

async def step_conferma_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == CB_ANNULLA:
        context.user_data.clear()
        await query.edit_message_text("❌ Sondaggio annullato. Usa /gioca per ricominciare.")
        return ConversationHandler.END

    draft = context.user_data.get("quiz_draft", {})
    user = query.from_user

    quiz_id = save_quiz(
        domanda=draft["domanda"],
        risposta_a=draft["risposta_a"],
        risposta_b=draft["risposta_b"],
        created_by=user.id,
        created_by_name=user.first_name or user.username or "Utente",
    )
    context.user_data.clear()

    await query.edit_message_text(
        f"🎉 *Sondaggio #{quiz_id} pubblicato!*\n\nUsa /gioca per votare o crearne un altro.",
        parse_mode="Markdown",
    )
    logger.info(f"✅ Sondaggio #{quiz_id} pubblicato da {user.first_name} (ID:{user.id})")
    return ConversationHandler.END


# ============================================================
# Annullamento
# ============================================================

async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Sondaggio annullato.\n\nUsa /gioca per ricominciare.")
    return ConversationHandler.END


# ============================================================
# Callback voto (bottoni A / B sul sondaggio attivo)
# ============================================================

async def risposta_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    try:
        cb_type, quiz_id_str = data.rsplit(":", 1)
        quiz_id = int(quiz_id_str)
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Errore nella risposta. Riprova.")
        return

    quiz = get_quiz_by_id(quiz_id)
    if quiz is None:
        await query.edit_message_text("⚠️ Sondaggio non trovato.")
        return

    if cb_type == CB_RISPOSTA_A:
        scelta, testo_scelta, steps = "A", quiz["risposta_a"], get_steps("A")
    else:
        scelta, testo_scelta, steps = "B", quiz["risposta_b"], get_steps("B")

    # Calcoliamo quanti step totali (netti) avrà effettuato il motore DOPO questo voto
    voti_a_attuali = quiz.get("voti_a", 0)
    voti_b_attuali = quiz.get("voti_b", 0)
    if scelta == "A":
        voti_a_attuali += 1
    else:
        voti_b_attuali += 1
        
    net_steps = (voti_a_attuali * get_steps("A")) + (voti_b_attuali * get_steps("B"))
    tot_voti = voti_a_attuali + voti_b_attuali
    
    force_rotate = False
    return_steps = 0
    if tot_voti >= 30:
        force_rotate = True
        return_steps = -net_steps

    saved = save_answer(
        quiz_id=quiz_id,
        scelta=scelta,
        testo_scelta=testo_scelta,
        user_id=user.id,
    )
    
    if force_rotate:
        # Recuperiamo il quiz per avere i risultati aggiornati con l'ultimo voto
        updated_quiz = get_quiz_by_id(quiz_id)
        if updated_quiz:
            voti_a_tot = updated_quiz.get("voti_a", 0)
            voti_b_tot = updated_quiz.get("voti_b", 0)
            
            # Troviamo gli user_id unici che hanno partecipato
            participating_users = set()
            for r in updated_quiz.get("risposte", []):
                uid = r.get("user_id")
                if uid is not None:
                    participating_users.add(uid)
                    
            notification_text = (
                f"📊 *Il sondaggio #{quiz_id} è concluso!*\n\n"
                f"❓ *{updated_quiz['domanda']}*\n"
                f"🅰️ {updated_quiz['risposta_a']}: *{voti_a_tot}* voti\n"
                f"🅱️ {updated_quiz['risposta_b']}: *{voti_b_tot}* voti\n\n"
                "Grazie mille per aver partecipato! Usa /gioca per scoprire il nuovo sondaggio attivo."
            )
            
            # Inviamo i messaggi a tutti i partecipanti in background
            async def notify_all_participants(users_set: set, testo: str):
                for uid in users_set:
                    try:
                        await context.bot.send_message(chat_id=uid, text=testo, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning(f"Impossibile inviare notifica risultato sondaggio a utente {uid}: {e}")
            
            asyncio.create_task(notify_all_participants(participating_users, notification_text))
            
        force_rotate_quiz()

    async def motor_sequence(st: int, ret_st: int):
        await trigger_motor(steps=st)
        if ret_st != 0:
            await asyncio.sleep(4)  # Assicuriamo che la prima mossa abbia tempo di partire e completarsi (circa)
            await trigger_motor(steps=ret_st)

    asyncio.create_task(motor_sequence(steps, return_steps))

    extra_msg = ""
    if force_rotate:
        extra_msg = "\n\n⚠️ *30 voti totali raggiunti! La domanda è stata cambiata e il motore tornerà alla posizione iniziale.*"

    await query.edit_message_text(
        f"✅ *Voto registrato!*\n\n"
        f"❓ {quiz['domanda']}\n"
        f"👉 Hai scelto: *{scelta} — {testo_scelta}*\n\n"
        f"_Grazie per aver partecipato al sondaggio #{quiz_id}!_{extra_msg}",
        parse_mode="Markdown",
    )
    logger.info(f"🎯 Risposta #{quiz_id}: {user.first_name} → {scelta} steps={steps} (net={net_steps})")


# ============================================================
# Builder handlers
# ============================================================

def build_gioco_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("gioca", cmd_gioco),
            CallbackQueryHandler(cmd_gioco_da_bottone, pattern=f"^{CB_CREA_NUOVO}$"),
        ],
        states={
            STEP_DOMANDA:    [MessageHandler(filters.TEXT & ~filters.COMMAND, step_domanda)],
            STEP_RISPOSTA_A: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_risposta_a)],
            STEP_RISPOSTA_B: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_risposta_b)],
            STEP_CONFERMA:   [CallbackQueryHandler(step_conferma_callback, pattern=f"^{CB_PUBBLICA}$|^{CB_ANNULLA}$")],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
        name="gioco_wizard",
        persistent=False,
    )


def build_answer_handler() -> CallbackQueryHandler:
    """Handler per i voti A/B sul sondaggio attivo."""
    return CallbackQueryHandler(
        risposta_quiz_callback,
        pattern=f"^({CB_RISPOSTA_A}|{CB_RISPOSTA_B}):\\d+$"
    )
