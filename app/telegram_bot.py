"""
Bot Telegram per la Casa di Quartiere di Tuturano.

Gestisce:
- Ricezione messaggi con python-telegram-bot
- Invio risposte con formattazione Markdown
- Comandi: /start, /aiuto, /info, /corsi, /contatti, /orari
- Indicatore di digitazione mentre il bot elabora
"""

import logging
import time
import asyncio
from typing import Optional

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

# --- Modulo Gioco — Sondaggi comunitari Tuturano ---
from gioco.wizard import (
    build_gioco_conversation_handler,
    build_answer_handler,
)

from app.config import settings
from app.analytics import analytics

logger = logging.getLogger(__name__)

# Riferimento globale al pipeline RAG (iniettato da main.py)
_rag_pipeline = None


def set_rag_pipeline(pipeline):
    """Imposta il riferimento al pipeline RAG."""
    global _rag_pipeline
    _rag_pipeline = pipeline

import json
import os
from datetime import datetime

USERS_CACHE_FILE = "users_cache.json"
_users_last_interaction = {}

def load_users_cache():
    global _users_last_interaction
    if os.path.exists(USERS_CACHE_FILE):
        try:
            with open(USERS_CACHE_FILE, "r") as f:
                _users_last_interaction = json.load(f)
        except Exception as e:
            logger.error(f"Errore lettura cache utenti: {e}")
            _users_last_interaction = {}

def save_users_cache():
    try:
        with open(USERS_CACHE_FILE, "w") as f:
            json.dump(_users_last_interaction, f)
    except Exception as e:
        logger.error(f"Errore scrittura cache utenti: {e}")

load_users_cache()

async def _check_and_send_daily_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verifica se è la prima interazione del giorno per l'utente e invia il saluto. Ritorna True se ha salutato."""
    user = update.effective_user
    if not user:
        return False
        
    user_id = str(user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    last_date = _users_last_interaction.get(user_id)
    
    if last_date != today:
        _users_last_interaction[user_id] = today
        save_users_cache()
        
        name = user.first_name or ""
        greeting_response = (
            f"Ciao{(' ' + name) if name else ''}! 👋\n\n"
            "Sono tutulacchi, il custode della Casa di Quartiere di Tuturano.\n"
            "Per interagire con me nel modo migliore, ti invito a cliccare sul bottone del menu "
            "in basso a sinistra e scegliere una delle opzioni."
        )
        await update.message.reply_text(greeting_response)
        return True
        
    return False


# ============================================================
# Messaggi di benvenuto e aiuto
# ============================================================

WELCOME_MESSAGE = """🏠 *Benvenuto alla Casa di Quartiere di Tuturano\\!*

Sono tutulacchi, il custode della casa di quartiere di Tuturano. 
Per scoprire cosa posso fare per te, clicca sul menu in basso a sinistra vicino all'area dove scrivi i messaggi\\!
Seleziona una delle opzioni disponibili per iniziare\\.👇"""

HELP_MESSAGE = """📋 *Comandi disponibili:*

/start \\- Messaggio di benvenuto
/aiuto \\- Mostra questo elenco
/info \\- Info
/gioca \\- Giochiamo
/radio \\- Radio

Oppure scrivi direttamente la tua domanda\\! 💬"""


# ============================================================
# Handler per i comandi
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start."""
    logger.info(f"👋 /start da {update.effective_user.first_name} (ID: {update.effective_user.id})")
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_aiuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /aiuto."""
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.MARKDOWN_V2)


async def _quick_query(update: Update, query: str):
    """Esegue una query rapida dal RAG e risponde."""
    if not _rag_pipeline:
        await update.message.reply_text("⚠️ Il sistema non e' ancora pronto. Riprova tra qualche secondo.")
        return

    # Mostra indicatore "sta scrivendo..."
    await update.message.chat.send_action(ChatAction.TYPING)

    start_time = time.time()
    result = await asyncio.to_thread(_rag_pipeline.answer, query)
    elapsed_ms = (time.time() - start_time) * 1000

    response_text = result["risposta"]
    await update.message.reply_text(response_text)

    # Analytics
    analytics.log_conversation(
        user_id=str(update.effective_user.id),
        user_message=query,
        bot_response=response_text,
        sources=result["fonti"],
        response_time_ms=elapsed_ms,
    )


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /info — informazioni generali, orari e contatti in un unico messaggio."""
    msg = (
        "ℹ️ *Informazioni generali*\n"
        "La Casa di Quartiere di Tuturano è gestita dall'Associazione IL CURRO-APS. È uno spazio dedicato all'aggregazione, alla cultura e al supporto della comunità.\n\n"
        "🕐 *Orari di apertura*\n"
        "Siamo attivi principalmente nel pomeriggio, dal lunedì al venerdì. Gli orari possono variare in base ai corsi e agli eventi.\n\n"
        "📞 *Contatti*\n"
        "Email: ilcurro.aps@gmail.com\n"
        "E puoi seguirci sulle nostre pagine social (Facebook e Instagram)!\n\n"
        "🗺️ *Come raggiungere*\n"
        "Siamo a Tuturano (Brindisi). Cerca 'Casa di Quartiere Tuturano' sulle mappe per trovarci facilmente."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_radio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /radio — sezione radio."""
    msg = "Aiutami a creare l'archivio dei Detti di Tuturano, mandami un breve vocale e nci pensu iu a condividerlo cu tutti! Addoni? Ti dau n'indiziu: mi le dittu nu \"uccellinu\"... :)"
    keyboard = [
        [InlineKeyboardButton("Vai al bot TuturAudio", url="https://t.me/tuturaudiobot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(msg, reply_markup=reply_markup)


# ============================================================
# Handler per messaggi liberi
# ============================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gestisce tutti i messaggi di testo liberi.
    Pipeline: saluto check → RAG retrieval → LLM generation → risposta.
    """
    if not update.message or not update.message.text:
        return

    # Check interazione giornaliera
    await _check_and_send_daily_greeting(update, context)

    user_text = update.message.text.strip()
    user = update.effective_user


    logger.info(
        f"📩 Messaggio da {user.first_name} (@{user.username or '?'}, ID:{user.id}): "
        f"'{user_text[:80]}'"
    )

    if not _rag_pipeline:
        await update.message.reply_text(
            "⚠️ Il sistema si sta avviando. Riprova tra qualche secondo."
        )
        return

    # Mostra "sta scrivendo..."
    await update.message.chat.send_action(ChatAction.TYPING)

    # Pipeline RAG completo
    start_time = time.time()
    result = await asyncio.to_thread(_rag_pipeline.answer, user_text)
    elapsed_ms = (time.time() - start_time) * 1000

    response_text = result["risposta"]

    # Telegram ha un limite di 4096 caratteri per messaggio
    if len(response_text) > 4000:
        chunks = _split_message(response_text, 4000)
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(response_text)

    logger.info(f"✅ Risposta inviata in {elapsed_ms:.0f}ms ({result['documenti_trovati']} fonti)")

    # Analytics
    analytics.log_conversation(
        user_id=str(user.id),
        user_message=user_text,
        bot_response=response_text,
        sources=result["fonti"],
        response_time_ms=elapsed_ms,
    )


async def handle_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce messaggi non testuali (foto, audio, ecc.)."""
    # Check interazione giornaliera
    await _check_and_send_daily_greeting(update, context)
    
    await update.message.reply_text(
        "Mi dispiace, al momento posso rispondere solo a messaggi di testo. ✍️\n\n"
        "Scrivi la tua domanda e cerchero' di aiutarti!"
    )


# ============================================================
# Utility
# ============================================================

def _split_message(text: str, max_length: int) -> list:
    """Divide un messaggio lungo rispettando i paragrafi."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""

    paragraphs = text.split("\n\n")
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_length:
            if current:
                chunks.append(current.strip())
                current = para
            else:
                while len(para) > max_length:
                    cut_point = para.rfind(". ", 0, max_length)
                    if cut_point == -1:
                        cut_point = max_length
                    chunks.append(para[:cut_point + 1].strip())
                    para = para[cut_point + 1:].strip()
                current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ============================================================
# Creazione e configurazione del bot
# ============================================================

def create_telegram_app() -> Application:
    """
    Crea e configura l'Application di python-telegram-bot.
    Registra tutti gli handler.
    """
    if not settings.telegram_bot_token or settings.telegram_bot_token == "your_bot_token_from_botfather":
        raise ValueError(
            "❌ Token Telegram non configurato!\n"
            "   1. Parla con @BotFather su Telegram\n"
            "   2. Crea un nuovo bot con /newbot\n"
            "   3. Copia il token nel file .env come TELEGRAM_BOT_TOKEN"
        )

    app = Application.builder().token(settings.telegram_bot_token).build()

    # Comandi
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("aiuto", cmd_aiuto))
    app.add_handler(CommandHandler("help", cmd_aiuto))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("radio", cmd_radio))

    # --- Gioco: Sondaggi comunitari (unico comando /gioco) ---
    # Il ConversationHandler deve stare PRIMA del MessageHandler generico
    app.add_handler(build_gioco_conversation_handler())
    app.add_handler(build_answer_handler())

    # Messaggi di testo liberi
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Messaggi non testuali
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, handle_non_text))

    logger.info("✅ Bot Telegram configurato con tutti gli handler")
    return app


async def setup_bot_commands(app: Application):
    """Imposta il menu dei comandi visibile su Telegram."""
    commands = [
        BotCommand("start",   "🏠 Benvenuto"),
        BotCommand("info",    "ℹ️ Info"),
        BotCommand("gioca",   "🎯 Giochiamo"),
        BotCommand("radio",   "📻 Radio"),
    ]

    try:
        await app.bot.set_my_commands(commands)
        logger.info("✅ Menu comandi Telegram impostato")
    except Exception as e:
        logger.warning(f"⚠️ Impossibile impostare comandi Telegram: {e}")
