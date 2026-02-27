"""
Storage per gioco — lettura/scrittura su gioco/quiz_data.json.
"""

import json
import logging
import os
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List

logger = logging.getLogger(__name__)

_QUIZ_DATA_FILE = os.path.join(os.path.dirname(__file__), "quiz_data.json")

# Esempi per creazione automatica bot
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
    "Dell'unico insonne",
    "La difenderemo all'UNESCO",
    "Nonna Maria ha colpito ancora",
    "Di chi ha lavato l'auto oggi",
    "Ottima cura per l'insonnia",
    "Un trafficante di cancelleria",
    "I criceti sul server sono cotti",
]
_ESEMPI_B = [
    "Di un demone in incognito",
    "Ci pianteremo dei gerani finti",
    "Lobby delle melanzane fritte",
    "Dei poteri forti, palesemente",
    "Peggio di un calcio sugli stinchi",
    "È palesemente scappata da sola",
    "I marziani ci stanno spiando",
]


def _load_db() -> dict:
    if not os.path.exists(_QUIZ_DATA_FILE):
        return {"quizzes": []}
    try:
        with open(_QUIZ_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"❌ Errore lettura gioco/quiz_data.json: {e}")
        return {"quizzes": []}


def _cleanup_old_quizzes(db: dict) -> dict:
    """Rimuove i quiz più vecchi di 5 anni (1825 giorni)."""
    if "quizzes" not in db:
        return db

    now = datetime.now(timezone.utc)
    valid_quizzes = []
    removed_count = 0

    for q in db["quizzes"]:
        try:
            # creato_il formato: "%Y-%m-%dT%H:%M:%SZ"
            dt_str = q.get("creato_il")
            if not dt_str:
                valid_quizzes.append(q)
                continue
            
            created_dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            days_old = (now - created_dt).days
            
            if days_old <= 1825:  # 5 anni
                valid_quizzes.append(q)
            else:
                removed_count += 1
        except Exception as e:
            # in caso di parse error, lo teniamo per sicurezza
            valid_quizzes.append(q)

    if removed_count > 0:
        logger.info(f"🧹 Pulizia dati: rimossi {removed_count} sondaggi più vecchi di 5 anni")
        
    db["quizzes"] = valid_quizzes
    return db


def _save_db(db: dict) -> None:
    try:
        db = _cleanup_old_quizzes(db)
        with open(_QUIZ_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error(f"❌ Errore scrittura gioco/quiz_data.json: {e}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_quiz(
    domanda: str,
    risposta_a: str,
    risposta_b: str,
    created_by: int,
    created_by_name: str,
) -> int:
    db = _load_db()
    
    # Trova il sondaggio attualmente attivo
    active_quiz = None
    for q in db["quizzes"]:
        if q.get("attivo", False):
            active_quiz = q
            break

    next_id = max((q["id"] for q in db["quizzes"]), default=0) + 1
    
    new_quiz = {
        "id": next_id,
        "domanda": domanda,
        "risposta_a": risposta_a,
        "risposta_b": risposta_b,
        "created_by": created_by,
        "created_by_name": created_by_name,
        "creato_il": _now_iso(),
        "attivo_dal": None,
        "attivo": False,
        "voti_a": 0,
        "voti_b": 0,
        "totale_risposte": 0,
        "risposte": [],
    }

    # Logica di stato e priorità
    if active_quiz is None:
        # Nessun sondaggio attivo -> diventa attivo subito
        new_quiz["attivo"] = True
        new_quiz["attivo_dal"] = _now_iso()
        logger.info(f"✅ Sondaggio #{next_id} attivo (nessun altro attivo)")
        from gioco.motor import update_quiz_display
        update_quiz_display(domanda, risposta_a, risposta_b)
        
    elif active_quiz.get("created_by") == 0 and created_by != 0:
        # Il bot era attivo, ma un umano ha creato un sondaggio -> priorità all'umano
        active_quiz["attivo"] = False
        new_quiz["attivo"] = True
        new_quiz["attivo_dal"] = _now_iso()
        logger.info(f"✅ Sondaggio #{next_id} attivo (priorità: scalza il sondaggio del bot #{active_quiz['id']})")
        from gioco.motor import update_quiz_display
        update_quiz_display(domanda, risposta_a, risposta_b)
        
    else:
        # C'è già un sondaggio umano attivo (o è il bot che sta generando) -> finisce in coda
        logger.info(f"⏳ Sondaggio #{next_id} messo in coda (c'è già un sondaggio attivo)")

    db["quizzes"].append(new_quiz)
    _save_db(db)
    return next_id


def _create_bot_quiz_if_needed(db: dict) -> None:
    """Se non c'è nessun sondaggio in coda/attivo, il bot ne crea uno."""
    if any(q.get("attivo", False) for q in db["quizzes"]):
        return  # C'è già qualcosa di attivo
        
    # Verifica se c'è qualcosa in coda
    if any(not q.get("attivo", False) for q in db["quizzes"] if q.get("voti_a",0)==0 and q.get("voti_b",0)==0 and q.get("attivo_dal") is None):
        return # c'è qualcosa in coda

    idx = random.randrange(len(_ESEMPI_DOMANDE))
    next_id = max((q["id"] for q in db["quizzes"]), default=0) + 1
    new_quiz = {
        "id": next_id,
        "domanda": _ESEMPI_DOMANDE[idx],
        "risposta_a": _ESEMPI_A[idx],
        "risposta_b": _ESEMPI_B[idx],
        "created_by": 0,
        "created_by_name": "Bot (Automatico)",
        "creato_il": _now_iso(),
        "attivo_dal": _now_iso(),
        "attivo": True,
        "voti_a": 0,
        "voti_b": 0,
        "totale_risposte": 0,
        "risposte": [],
    }
    db["quizzes"].append(new_quiz)
    logger.info(f"🤖 Bot ha creato automaticamente il sondaggio #{next_id} perché la coda era vuota")
    from gioco.motor import update_quiz_display
    update_quiz_display(new_quiz["domanda"], new_quiz["risposta_a"], new_quiz["risposta_b"])


def check_and_rotate_quizzes() -> None:
    """
    Controlla se c'è un sondaggio attivo. Se non ce n'è nessuno,
    attiva il primo in coda. Se la coda è vuota, il bot ne crea uno.
    Nota: La chiusura del sondaggio avviene ora SOLO per limite di step (force_rotate_quiz).
    """
    db = _load_db()
    changed = False

    # 1. Trova il sondaggio attivo
    active_quiz = None
    for q in db["quizzes"]:
        if q.get("attivo", False):
            active_quiz = q
            break

    # Se c'è un active_quiz valido, non c'è nulla da ruotare automaticamente qui.
    if active_quiz is not None:
        return

    # 2. Nessun quiz attivo, cerchiamo il prossimo nella coda
    # (Quiz non ancora avviato = attivo=False e attivo_dal=None)
    coda = [q for q in db["quizzes"] if not q.get("attivo", False) and q.get("attivo_dal") is None]
    
    if coda:
        # Prendi il più vecchio in coda (ordinati per ID/inserimento)
        next_quiz = coda[0]
        next_quiz["attivo"] = True
        next_quiz["attivo_dal"] = _now_iso()
        logger.info(f"▶️ Sondaggio in coda #{next_quiz['id']} è diventato attivo")
        from gioco.motor import update_quiz_display
        update_quiz_display(next_quiz["domanda"], next_quiz["risposta_a"], next_quiz["risposta_b"])
        changed = True
    else:
        # 3. Coda vuota -> crea quiz da bot
        _create_bot_quiz_if_needed(db)
        changed = True

    if changed:
        _save_db(db)


def force_rotate_quiz() -> None:
    """Disattiva forzatamente il sondaggio attivo e attiva il prossimo in coda."""
    db = _load_db()
    changed = False
    for q in db["quizzes"]:
        if q.get("attivo", False):
            q["attivo"] = False
            logger.info(f"🔄 Sondaggio #{q['id']} disattivato forzatamente (raggiunti i 2040 step)")
            changed = True
            break
    if changed:
        _save_db(db)
    check_and_rotate_quizzes()


def get_active_quiz() -> Optional[dict]:
    db = _load_db()
    for q in reversed(db["quizzes"]):
        if q.get("attivo", False):
            return q
    return None


def get_quiz_by_id(quiz_id: int) -> Optional[dict]:
    db = _load_db()
    for q in db["quizzes"]:
        if q["id"] == quiz_id:
            return q
    return None


def load_all_quizzes() -> list:
    db = _load_db()
    return [{k: v for k, v in q.items() if k != "risposte"} for q in db["quizzes"]]


def save_answer(
    quiz_id: int,
    scelta: str,
    testo_scelta: str,
    user_id: Optional[int] = None,
) -> bool:
    db = _load_db()
    for q in db["quizzes"]:
        if q["id"] != quiz_id:
            continue
            
        risposta = {
            "scelta": scelta,
            "testo_scelta": testo_scelta,
            "timestamp": _now_iso(),
            "user_id": user_id,
        }
        q.setdefault("risposte", []).append(risposta)
        if scelta == "A":
            q["voti_a"] = q.get("voti_a", 0) + 1
        else:
            q["voti_b"] = q.get("voti_b", 0) + 1
        q["totale_risposte"] = q.get("totale_risposte", 0) + 1
        _save_db(db)
        logger.info(f"✅ Risposta anonima salvata: domanda#{quiz_id} | scelta={scelta}")
        return True
    logger.warning(f"⚠️ Domanda #{quiz_id} non trovata nel DB")
    return False
