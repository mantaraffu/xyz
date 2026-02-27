"""
Motor per gioco — Comunicazione HTTP con l'ESP32 per il motore 28BYJ-48.

Variabili .env:
  ESP32_QUIZ_URL      → URL base ESP32, es: http://192.168.0.39
  ESP32_MOTOR_URL     → fallback
  QUIZ_STEPS_A        → passi risposta A (default 68)
  QUIZ_STEPS_B        → passi risposta B (default -68)
  QUIZ_MOTOR_TIMEOUT  → timeout HTTP in secondi (default 3.0)
"""

import logging
import os
import httpx

logger = logging.getLogger(__name__)


def _build_base_url() -> str:
    from app.config import settings
    quiz_url = os.environ.get("ESP32_QUIZ_URL", "").strip()
    if quiz_url:
        return quiz_url.rstrip("/")
    motor_url = settings.esp32_motor_url.strip()
    if motor_url:
        base = motor_url.rstrip("/")
        if base.endswith("/step"):
            base = base[:-5]
        return base.rstrip("/")
    return ""


def _get_timeout() -> float:
    try:
        return float(os.environ.get("QUIZ_MOTOR_TIMEOUT", "3.0"))
    except ValueError:
        return 3.0


def get_steps(scelta: str) -> int:
    try:
        steps_a = int(os.environ.get("QUIZ_STEPS_A", "68"))
        steps_b = int(os.environ.get("QUIZ_STEPS_B", "-68"))
    except ValueError:
        steps_a, steps_b = 68, -68
    return steps_a if scelta.upper() == "A" else steps_b


async def trigger_motor(steps: int) -> bool:
    base_url = _build_base_url()
    if not base_url:
        logger.warning("⚠️ [Gioco Motor] Nessun URL ESP32. Controlla ESP32_QUIZ_URL nel .env")
        return False
    url = f"{base_url}/move"
    params = {"steps": steps}
    timeout = _get_timeout()
    logger.info(f"🔌 [Gioco Motor] → {url}?steps={steps}")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            logger.info(f"✅ [Gioco Motor] HTTP {response.status_code} — {response.text.strip()}")
            return True
    except httpx.TimeoutException:
        logger.warning(f"⏱️ [Gioco Motor] Timeout ({timeout}s) → {url}")
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ [Gioco Motor] HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        logger.error(f"❌ [Gioco Motor] Errore: {e}")
    return False


def _sanitize_lcd_text(text: str) -> str:
    replacements = {
        'à': "a'", 'è': "e'", 'é': "e'", 'ì': "i'", 'ò': "o'", 'ù': "u'",
        'À': "A'", 'È': "E'", 'É': "E'", 'Ì': "I'", 'Ò': "O'", 'Ù': "U'"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def update_quiz_display(domanda: str, risposta_a: str, risposta_b: str) -> None:
    """Aggiorna in background il display LCD dell'ESP32 con il quiz attivo."""
    base_url = _build_base_url()
    if not base_url:
        return

    url = f"{base_url}/quiz"
    params = {
        "q": _sanitize_lcd_text(domanda), 
        "a1": _sanitize_lcd_text(f"1: {risposta_a}"), 
        "a2": _sanitize_lcd_text(f"2: {risposta_b}")
    }
    timeout = _get_timeout()

    def _do_update():
        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.get(url, params=params)
                res.raise_for_status()
                logger.info("✅ [Gioco Motor] Display LCD ESP32 aggiornato con nuovo sondaggio")
        except Exception as e:
            logger.warning(f"⚠️ [Gioco Motor] Impossibile aggiornare display LCD: {e}")

    import threading
    threading.Thread(target=_do_update, daemon=True).start()
