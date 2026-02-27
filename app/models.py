"""
Modelli Pydantic per la validazione dei dati.
Coprono: messaggi Telegram, entries del knowledge base, metriche.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ============================================================
# Knowledge Base Models
# ============================================================

class Categoria(str, Enum):
    """Categorie del knowledge base."""
    INFORMAZIONI_GENERALI = "informazioni_generali"
    SPAZI = "spazi"
    CORSI_ATTIVITA = "corsi_attivita"
    COSTI_TARIFFE = "costi_tariffe"
    CONTATTI = "contatti"
    PRENOTAZIONI = "prenotazioni"
    REGOLAMENTO = "regolamento"
    EVENTI = "eventi"
    VOLONTARIATO = "volontariato"
    COLLABORAZIONI = "collaborazioni"
    FAQ_TECNICHE = "faq_tecniche"


class Priorita(str, Enum):
    """Priorita' dell'entry."""
    ALTA = "alta"
    MEDIA = "media"
    BASSA = "bassa"


class KBEntry(BaseModel):
    """Singola entry del knowledge base in formato Q&A."""
    id: Optional[str] = Field(default=None, description="ID univoco generato automaticamente")
    categoria: Categoria = Field(..., description="Categoria tematica")
    priorita: Priorita = Field(default=Priorita.ALTA, description="Livello di priorita'")
    domanda: str = Field(..., description="Domanda frequente del cittadino")
    risposta: str = Field(..., description="Risposta completa e dettagliata")
    keywords: List[str] = Field(default_factory=list, description="Parole chiave per il retrieval")
    fonte: Optional[str] = Field(default=None, description="Fonte dell'informazione")
    data_aggiornamento: Optional[str] = Field(default=None, description="Data ultimo aggiornamento")
    attiva: bool = Field(default=True, description="Entry attiva o archiviata")
    note_interne: Optional[str] = Field(default=None, description="Note per il personale, non visibili")

    def to_document_text(self) -> str:
        """Converte l'entry in testo per l'embedding."""
        parts = [
            f"Domanda: {self.domanda}",
            f"Risposta: {self.risposta}",
        ]
        if self.keywords:
            parts.append(f"Parole chiave: {', '.join(self.keywords)}")
        return "\n".join(parts)

    def to_metadata(self) -> dict:
        """Genera metadata per ChromaDB."""
        return {
            "categoria": self.categoria.value,
            "priorita": self.priorita.value,
            "domanda": self.domanda,
            "attiva": self.attiva,
            "data_aggiornamento": self.data_aggiornamento or "",
            "fonte": self.fonte or "",
        }


class KBFile(BaseModel):
    """File contenente piu' entries di una categoria."""
    categoria: Categoria
    descrizione: str
    entries: List[KBEntry]


# ============================================================
# Telegram Message Models
# ============================================================

class TelegramIncomingMessage(BaseModel):
    """Messaggio ricevuto da Telegram."""
    chat_id: int
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    message_text: str
    message_id: int
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================
# Conversation & Analytics Models
# ============================================================

class ConversationTurn(BaseModel):
    """Singolo turno di conversazione."""
    timestamp: datetime = Field(default_factory=datetime.now)
    user_message: str
    bot_response: str
    sources_used: List[str] = Field(default_factory=list)
    response_time_ms: float = 0.0
    similarity_scores: List[float] = Field(default_factory=list)


class ConversationSession(BaseModel):
    """Sessione di conversazione con un utente."""
    session_id: str
    user_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    turns: List[ConversationTurn] = Field(default_factory=list)
    is_active: bool = True


class BotMetrics(BaseModel):
    """Metriche operative del bot."""
    total_messages: int = 0
    total_conversations: int = 0
    avg_response_time_ms: float = 0.0
    top_categories: dict = Field(default_factory=dict)
    unanswered_count: int = 0
    uptime_hours: float = 0.0
    kb_entry_count: int = 0
    last_updated: Optional[datetime] = None


class DashboardStats(BaseModel):
    """Statistiche per la dashboard."""
    metrics: BotMetrics
    recent_conversations: List[dict] = Field(default_factory=list)
    system_status: dict = Field(default_factory=dict)
