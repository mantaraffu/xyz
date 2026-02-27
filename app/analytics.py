"""
Sistema di analytics e logging delle conversazioni.

Traccia:
- Tutte le conversazioni (anonimizzate)
- Tempi di risposta
- Categorie piu' richieste
- Domande senza risposta
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from collections import Counter

from app.models import ConversationTurn, BotMetrics

logger = logging.getLogger(__name__)

ANALYTICS_DIR = Path("./analytics_data")
CONVERSATIONS_FILE = ANALYTICS_DIR / "conversations.jsonl"
METRICS_FILE = ANALYTICS_DIR / "metrics.json"


class AnalyticsTracker:
    """Traccia conversazioni e calcola metriche."""

    def __init__(self):
        ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
        self._start_time = datetime.now()

    def log_conversation(
        self,
        user_id: str,
        user_message: str,
        bot_response: str,
        sources: List[dict],
        response_time_ms: float,
    ):
        """Registra un turno di conversazione."""
        # Anonimizza user_id (mantieni solo hash parziale)
        anon_id = f"user_{hash(user_id) % 100000:05d}"

        record = {
            "timestamp": datetime.now().isoformat(),
            "user_id": anon_id,
            "message_length": len(user_message),
            "response_length": len(bot_response),
            "categories_used": [s.get("categoria", "") for s in sources],
            "num_sources": len(sources),
            "avg_similarity": (
                round(sum(s.get("similarita", 0) for s in sources) / len(sources), 3)
                if sources else 0
            ),
            "response_time_ms": round(response_time_ms, 1),
            "had_sources": len(sources) > 0,
        }

        try:
            with open(CONVERSATIONS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Errore salvando analytics: {e}")

    def get_metrics(self) -> BotMetrics:
        """Calcola le metriche aggregate."""
        records = self._load_records()

        if not records:
            return BotMetrics(
                uptime_hours=self._uptime_hours(),
                last_updated=datetime.now(),
            )

        total = len(records)
        avg_time = sum(r.get("response_time_ms", 0) for r in records) / total
        unanswered = sum(1 for r in records if not r.get("had_sources", True))

        # Top categorie
        all_cats = []
        for r in records:
            all_cats.extend(r.get("categories_used", []))
        top_cats = dict(Counter(all_cats).most_common(10))

        # Utenti unici
        unique_users = len(set(r.get("user_id", "") for r in records))

        return BotMetrics(
            total_messages=total,
            total_conversations=unique_users,
            avg_response_time_ms=round(avg_time, 1),
            top_categories=top_cats,
            unanswered_count=unanswered,
            uptime_hours=self._uptime_hours(),
            last_updated=datetime.now(),
        )

    def get_recent_conversations(self, limit: int = 20) -> List[dict]:
        """Ultime N conversazioni (anonimizzate)."""
        records = self._load_records()
        return records[-limit:] if records else []

    def get_daily_stats(self, days: int = 30) -> List[dict]:
        """Statistiche giornaliere."""
        records = self._load_records()
        if not records:
            return []

        daily = {}
        for r in records:
            try:
                date = r["timestamp"][:10]
                if date not in daily:
                    daily[date] = {"date": date, "count": 0, "avg_time": 0, "times": []}
                daily[date]["count"] += 1
                daily[date]["times"].append(r.get("response_time_ms", 0))
            except (KeyError, IndexError):
                continue

        result = []
        for date, data in sorted(daily.items()):
            data["avg_time"] = round(sum(data["times"]) / len(data["times"]), 1)
            del data["times"]
            result.append(data)

        return result[-days:]

    def _load_records(self) -> List[dict]:
        """Carica tutti i record dal file JSONL."""
        if not CONVERSATIONS_FILE.exists():
            return []

        records = []
        try:
            with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as e:
            logger.error(f"Errore caricando analytics: {e}")

        return records

    def _uptime_hours(self) -> float:
        return round((datetime.now() - self._start_time).total_seconds() / 3600, 2)


# Singleton
analytics = AnalyticsTracker()
