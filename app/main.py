"""
Server principale FastAPI + Bot Telegram.

Il sistema funziona in due modalita':
- POLLING (default, consigliato): il bot interroga i server Telegram periodicamente.
  Non richiede URL pubblico, tunnel o certificati SSL. Ideale per installazione locale.
- WEBHOOK: Telegram invia gli aggiornamenti al server via HTTPS.
  Richiede un URL pubblico (es. Cloudflare Tunnel).

Endpoint dashboard (sempre attivi):
- GET  /                  → Dashboard di gestione
- GET  /kb                → Gestione Knowledge Base
- GET  /api/stats         → Statistiche JSON
- GET  /api/kb            → Knowledge base entries
- POST /api/kb            → Aggiungi entry
- DELETE /api/kb/{id}     → Rimuovi entry
- GET  /health            → Health check
"""

import asyncio
import logging
import secrets
import sys
import time
import threading
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Query, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings
from app.models import KBEntry, Categoria, Priorita
from app.rag import rag_pipeline
from app.telegram_bot import create_telegram_app, set_rag_pipeline, setup_bot_commands
from app.analytics import analytics

# WhatsApp — import condizionale (se credenziali configurate)
_whatsapp_enabled = False
try:
    from app.whatsapp_bot import handle_whatsapp_message as _wa_handle
    _whatsapp_enabled = True
except ImportError:
    pass

# ============================================================
# Logging Setup
# ============================================================

def setup_logging():
    """Configura logging con output su file e console."""
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_path), encoding="utf-8"),
        ],
    )

setup_logging()
logger = logging.getLogger(__name__)

# Riferimento globale per il bot Telegram
telegram_app = None


# ============================================================
# App Lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestisce avvio e chiusura dell'applicazione."""
    global telegram_app

    logger.info("=" * 60)
    logger.info("🏠 Casa di Quartiere Tuturano — AI Assistant (Telegram)")
    logger.info("=" * 60)

    # Avvia loop di rotazione sondaggi
    from gioco.storage import check_and_rotate_quizzes, get_active_quiz

    # Sincronizza subito con l'ESP32 se c'è un sondaggio già attivo
    active = get_active_quiz()
    if active:
        from gioco.motor import update_quiz_display
        logger.info(f"📤 Sincronizzazione ESP32 con sondaggio attivo #{active['id']}")
        update_quiz_display(active['domanda'], active['risposta_a'], active['risposta_b'])
    
    async def _survey_rotation_loop():
        while True:
            try:
                check_and_rotate_quizzes()
            except Exception as e:
                logger.error(f"❌ Errore durante la rotazione dei sondaggi: {e}")
            await asyncio.sleep(60)  # Controlla scadenze ogni minuto

    rotation_task = asyncio.create_task(_survey_rotation_loop())

    # Avvia loop polling ESP32
    import httpx
    import os
    async def _esp32_polling_loop():
        esp32_url = os.environ.get("ESP32_QUIZ_URL", "").strip() or settings.esp32_motor_url.strip()
        if not esp32_url:
            return
            
        esp32_base = esp32_url.rsplit('/', 1)[0] if '/step' in esp32_url else esp32_url
        if esp32_base.endswith('/'): 
            esp32_base = esp32_base[:-1]

        while True:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{esp32_base}/poll_votes")
                    if resp.status_code == 200:
                        data = resp.json()
                        voti_a = data.get("A", 0)
                        voti_b = data.get("B", 0)
                        
                        if voti_a > 0 or voti_b > 0:
                            from gioco.storage import get_active_quiz, save_answer, force_rotate_quiz, get_quiz_by_id
                            from gioco.motor import get_steps, trigger_motor
                            quiz = get_active_quiz()
                            if quiz:
                                for _ in range(voti_a):
                                    save_answer(quiz["id"], "A", quiz["risposta_a"])
                                    logger.info(f"👉 Voto fisico ESP32 (A) registrato per sondaggio #{quiz['id']}")
                                for _ in range(voti_b):
                                    save_answer(quiz["id"], "B", quiz["risposta_b"])
                                    logger.info(f"👉 Voto fisico ESP32 (B) registrato per sondaggio #{quiz['id']}")
                                
                                # Verifica per il reset fisico automatico (30 voti totali)
                                updated_quiz = get_quiz_by_id(quiz["id"])
                                if updated_quiz:
                                    va = updated_quiz.get("voti_a", 0)
                                    vb = updated_quiz.get("voti_b", 0)
                                    tot_voti = va + vb
                                    net_steps = (va * get_steps("A")) + (vb * get_steps("B"))
                                    
                                    if tot_voti >= 30:
                                        logger.info(f"🚨 Limite 30 voti raggiunto: forzatura reset sondaggio e motore")
                                        try:
                                            bot = telegram_app.bot
                                            participating_users = {r.get("user_id") for r in updated_quiz.get("risposte", []) if r.get("user_id")}
                                            notification_text = (
                                                f"📊 *Il sondaggio #{updated_quiz['id']} è concluso!*\n\n"
                                                f"❓ *{updated_quiz['domanda']}*\n"
                                                f"🅰️ {updated_quiz['risposta_a']}: *{va}* voti\n"
                                                f"🅱️ {updated_quiz['risposta_b']}: *{vb}* voti\n\n"
                                                "Grazie mille per aver partecipato! Usa /gioca per scoprire il nuovo sondaggio attivo."
                                            )
                                            async def notify_all(users, msg, bot_inst):
                                                for uid in users:
                                                    try: await bot_inst.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
                                                    except Exception: pass
                                            asyncio.create_task(notify_all(participating_users, notification_text, bot))
                                        except Exception as e:
                                            pass
                                            
                                        force_rotate_quiz()
                                        
                                        async def revert(ret_steps):
                                            await asyncio.sleep(2)
                                            await trigger_motor(steps=ret_steps)
                                        asyncio.create_task(revert(-net_steps))
            except Exception:
                pass  # Ignora silenziosamente errori se l'ESP32 è offline
            await asyncio.sleep(2)

    polling_task = asyncio.create_task(_esp32_polling_loop())

    # 1. Inizializza RAG
    rag_pipeline.initialize()
    loaded = rag_pipeline.load_knowledge_base()
    logger.info(f"📚 Knowledge base: {loaded} entries caricate")

    # 2. Inietta RAG nel bot Telegram
    set_rag_pipeline(rag_pipeline)

    # 3. Avvia bot Telegram
    try:
        telegram_app = create_telegram_app()

        if settings.is_webhook_mode:
            # Modalita' webhook — Telegram inviera' aggiornamenti al nostro server
            logger.info(f"🔗 Modalita' WEBHOOK — URL: {settings.telegram_webhook_url}")
            await telegram_app.initialize()
            await setup_bot_commands(telegram_app)
            webhook_url = f"{settings.telegram_webhook_url}/telegram/webhook"
            await telegram_app.bot.set_webhook(url=webhook_url)
            await telegram_app.start()
            logger.info(f"✅ Webhook Telegram impostato: {webhook_url}")
        else:
            # Modalita' polling — il bot interroga Telegram periodicamente
            logger.info("🔄 Modalita' POLLING — nessun URL pubblico necessario")
            await telegram_app.initialize()
            await setup_bot_commands(telegram_app)
            await telegram_app.start()
            await telegram_app.updater.start_polling(drop_pending_updates=True)
            logger.info("✅ Bot Telegram in polling — in attesa di messaggi...")

        bot_info = await telegram_app.bot.get_me()
        logger.info(f"🤖 Bot attivo: @{bot_info.username} ({bot_info.first_name})")

    except Exception as e:
        logger.error(f"❌ Errore avvio bot Telegram: {e}")
        logger.info("ℹ️  La dashboard resta attiva. Verifica il TELEGRAM_BOT_TOKEN nel .env")

    logger.info("🟢 Sistema pronto!")
    if settings.is_whatsapp_enabled:
        logger.info("📱 WhatsApp Cloud API attivo — webhook: /whatsapp/webhook")
    else:
        logger.info("📱 WhatsApp non configurato (WHATSAPP_TOKEN vuoto) — solo Telegram")

    yield

    # Chiusura
    rotation_task.cancel()
    polling_task.cancel()
    if telegram_app:
        try:
            if not settings.is_webhook_mode and telegram_app.updater:
                await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
        except Exception as e:
            logger.warning(f"Errore chiusura bot: {e}")

    logger.info("🔴 Sistema arrestato")


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="Casa di Quartiere Tuturano — AI Assistant",
    description="Assistente AI su Telegram per la Casa di Quartiere di Tuturano (BR)",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files e templates
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Security per la dashboard
security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verifica credenziali per l'accesso alla dashboard."""
    correct_user = secrets.compare_digest(credentials.username, settings.dashboard_username)
    correct_pass = secrets.compare_digest(credentials.password, settings.dashboard_password)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Accesso non autorizzato",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username


# ============================================================
# Telegram Webhook Endpoint (solo per modalita' webhook)
# ============================================================

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Riceve aggiornamenti da Telegram in modalita' webhook.
    Attivo solo se TELEGRAM_MODE=webhook nel .env.
    """
    if not settings.is_webhook_mode:
        raise HTTPException(status_code=404, detail="Webhook non attivo (modalita' polling)")

    if not telegram_app:
        raise HTTPException(status_code=503, detail="Bot non inizializzato")

    try:
        data = await request.json()
        from telegram import Update as TGUpdate
        update = TGUpdate.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Errore processing webhook Telegram: {e}")
        return JSONResponse(content={"status": "error"}, status_code=200)


# ============================================================
# WhatsApp Webhook Endpoints
# ============================================================

@app.get("/whatsapp/webhook")
async def whatsapp_verify(request: Request):
    """
    Verifica del webhook richiesta da Meta durante la configurazione.
    Meta invia: hub.mode, hub.verify_token, hub.challenge
    Se il verify_token corrisponde, rispondiamo con hub.challenge.
    """
    params = request.query_params
    mode      = params.get("hub.mode", "")
    token     = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("✅ WhatsApp webhook verificato da Meta")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(challenge)

    logger.warning(f"⚠️ WhatsApp webhook verifica fallita (token: '{token}')")
    raise HTTPException(status_code=403, detail="Token di verifica non valido")


@app.post("/whatsapp/webhook")
async def whatsapp_incoming(request: Request):
    """
    Riceve messaggi WhatsApp in arrivo da Meta Cloud API.
    Attivo solo se WHATSAPP_TOKEN è configurato nel .env.
    """
    if not settings.is_whatsapp_enabled:
        raise HTTPException(status_code=404, detail="WhatsApp non configurato")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload non valido")

    # Risponde subito 200 a Meta (obbligatorio entro 20s)
    # poi processa il messaggio in background
    import asyncio
    asyncio.create_task(_wa_handle(data, rag_pipeline))
    return JSONResponse(content={"status": "ok"})


# ============================================================
# Dashboard Endpoints
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(verify_credentials)):
    """Dashboard di gestione principale."""
    metrics = analytics.get_metrics()
    kb_stats = rag_pipeline.get_kb_stats()
    recent = analytics.get_recent_conversations(limit=15)
    daily = analytics.get_daily_stats(days=30)

    # Info bot Telegram
    bot_info = {}
    if telegram_app:
        try:
            me = await telegram_app.bot.get_me()
            bot_info = {
                "username": me.username,
                "name": me.first_name,
                "link": f"https://t.me/{me.username}",
            }
        except Exception:
            pass

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": username,
        "metrics": metrics,
        "kb_stats": kb_stats,
        "recent": recent,
        "daily_stats": daily,
        "categories": [c.value for c in Categoria],
        "bot_info": bot_info,
    })


@app.get("/kb", response_class=HTMLResponse)
async def kb_manager(request: Request, username: str = Depends(verify_credentials)):
    """Pagina gestione Knowledge Base."""
    kb_data = rag_pipeline.get_all_entries()
    kb_stats = rag_pipeline.get_kb_stats()

    entries = []
    if kb_data.get("ids"):
        for i, entry_id in enumerate(kb_data["ids"]):
            entries.append({
                "id": entry_id,
                "document": kb_data["documents"][i] if kb_data.get("documents") else "",
                "metadata": kb_data["metadatas"][i] if kb_data.get("metadatas") else {},
            })

    return templates.TemplateResponse("kb_manager.html", {
        "request": request,
        "username": username,
        "entries": entries,
        "kb_stats": kb_stats,
        "categories": [c.value for c in Categoria],
        "priorities": [p.value for p in Priorita],
    })


# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/stats")
async def api_stats(username: str = Depends(verify_credentials)):
    """Statistiche del sistema in formato JSON."""
    metrics = analytics.get_metrics()
    kb_stats = rag_pipeline.get_kb_stats()
    return {
        "metrics": metrics.model_dump(),
        "kb_stats": kb_stats,
    }


@app.get("/api/kb")
async def api_get_kb(username: str = Depends(verify_credentials)):
    """Lista tutte le entries del knowledge base."""
    return rag_pipeline.get_all_entries()


@app.post("/api/kb")
async def api_add_entry(
    categoria: str = Form(...),
    priorita: str = Form("alta"),
    domanda: str = Form(...),
    risposta: str = Form(...),
    keywords: str = Form(""),
    fonte: str = Form(""),
    username: str = Depends(verify_credentials),
):
    """Aggiunge una nuova entry al knowledge base."""
    entry = KBEntry(
        categoria=Categoria(categoria),
        priorita=Priorita(priorita),
        domanda=domanda,
        risposta=risposta,
        keywords=[k.strip() for k in keywords.split(",") if k.strip()],
        fonte=fonte or None,
        data_aggiornamento=time.strftime("%Y-%m-%d"),
    )

    entry_id = rag_pipeline.add_entry(entry)
    return {"status": "ok", "entry_id": entry_id}


@app.delete("/api/kb/{entry_id}")
async def api_delete_entry(entry_id: str, username: str = Depends(verify_credentials)):
    """Rimuove una entry dal knowledge base."""
    success = rag_pipeline.delete_entry(entry_id)
    if success:
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Entry non trovata")


@app.get("/api/search")
async def api_search(
    q: str = Query(..., description="Domanda da cercare"),
    username: str = Depends(verify_credentials),
):
    """Testa il retrieval senza generare una risposta LLM."""
    docs = rag_pipeline.retrieve(q)
    return {
        "query": q,
        "results": [
            {
                "document": doc,
                "metadata": meta,
                "similarity": round(score, 3),
            }
            for doc, meta, score in docs
        ],
    }


@app.post("/api/test")
async def api_test(
    q: str = Form(...),
    username: str = Depends(verify_credentials),
):
    """Testa il pipeline completo (retrieval + generation)."""
    result = await asyncio.to_thread(rag_pipeline.answer, q)
    return result


@app.get("/health")
async def health_check():
    """Health check per monitoraggio."""
    kb_count = 0
    try:
        kb_stats = rag_pipeline.get_kb_stats()
        kb_count = kb_stats.get("totale_entries", 0)
    except Exception:
        pass

    ollama_ok = False
    try:
        import ollama as ol
        ol.list()
        ollama_ok = True
    except Exception:
        pass

    bot_ok = False
    bot_username = None
    if telegram_app:
        try:
            me = await telegram_app.bot.get_me()
            bot_ok = True
            bot_username = f"@{me.username}"
        except Exception:
            pass

    return {
        "status": "healthy",
        "version": "1.0.0",
        "platform": "telegram",
        "bot_active": bot_ok,
        "bot_username": bot_username,
        "mode": settings.telegram_mode,
        "knowledge_base_entries": kb_count,
        "ollama_connected": ollama_ok,
        "model": settings.ollama_model,
    }


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
