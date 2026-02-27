"""
Configurazione centralizzata del sistema.
Carica variabili da .env e fornisce valori di default sicuri.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    """Configurazione globale dell'assistente AI."""

    # --- Telegram Bot ---
    telegram_bot_token: str = Field(default="", description="Token del bot Telegram da @BotFather")
    telegram_mode: str = Field(default="polling", description="Modalita' bot: 'polling' o 'webhook'")
    telegram_webhook_url: str = Field(default="", description="URL webhook (solo per modalita' webhook)")

    # --- WhatsApp Cloud API (Meta) ---
    whatsapp_token: str = Field(default="", description="Access Token Meta WhatsApp Cloud API")
    whatsapp_phone_number_id: str = Field(default="", description="Phone Number ID Meta Business")
    whatsapp_verify_token: str = Field(default="", description="Token segreto verifica webhook Meta")

    # --- Ollama ---
    ollama_base_url: str = Field(default="http://localhost:11434", description="URL base di Ollama")
    ollama_model: str = Field(default="gemma3:12b", description="Modello LLM da utilizzare")

    # --- ESP32 Motor ---
    esp32_motor_url: str = Field(default="", description="URL per l'endpoint ESP32 per muovere il motore")

    # --- ChromaDB ---
    chroma_persist_dir: str = Field(default="./chroma_data", description="Directory persistenza ChromaDB")
    chroma_collection_name: str = Field(default="casa_quartiere_kb", description="Nome collezione ChromaDB")

    # --- Embedding ---
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="Modello di embedding multilingue"
    )

    # --- RAG ---
    rag_top_k: int = Field(default=5, description="Numero documenti da recuperare")
    rag_similarity_threshold: float = Field(default=0.5, description="Soglia minima di similarita'")
    # --- Server ---
    server_host: str = Field(default="0.0.0.0", description="Host del server")
    server_port: int = Field(default=8000, description="Porta del server")
    debug: bool = Field(default=False, description="Modalita' debug")

    # --- Dashboard ---
    dashboard_username: str = Field(default="admin", description="Username dashboard")
    dashboard_password: str = Field(default="changeme", description="Password dashboard")

    # --- Logging ---
    log_level: str = Field(default="INFO", description="Livello di logging")
    log_file: str = Field(default="./logs/bot.log", description="File di log")

    # --- Paths ---
    knowledge_base_dir: str = Field(
        default="./knowledge_base/entries",
        description="Directory dei file del knowledge base"
    )

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)

    @property
    def kb_path(self) -> Path:
        return Path(self.knowledge_base_dir)

    @property
    def log_path(self) -> Path:
        return Path(self.log_file)

    @property
    def is_webhook_mode(self) -> bool:
        return self.telegram_mode.lower() == "webhook"

    @property
    def is_whatsapp_enabled(self) -> bool:
        """True se le credenziali WhatsApp sono tutte configurate."""
        return bool(
            self.whatsapp_token
            and self.whatsapp_phone_number_id
            and self.whatsapp_verify_token
        )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",   # ignora variabili .env non dichiarate (es. modulo quiz)
    }


# Singleton
settings = Settings()
