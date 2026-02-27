"""
Pipeline RAG (Retrieval-Augmented Generation).

Flusso:
1. La domanda dell'utente viene convertita in embedding
2. ChromaDB trova i documenti piu' rilevanti
3. I documenti vengono passati al LLM come contesto
4. Il LLM genera una risposta in italiano naturale
"""

import logging
import time
import json
from pathlib import Path
from typing import List, Tuple, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
import ollama

from app.config import settings
from app.models import KBEntry, KBFile, Categoria

logger = logging.getLogger(__name__)


# ============================================================
# System Prompt per l'assistente
# ============================================================

SYSTEM_PROMPT = """Sei tutulacchi, l'assistente virtuale della Casa di Quartiere di Tuturano, una frazione di Brindisi in Puglia.

Il tuo compito e' rispondere alle domande dei cittadini in modo:
- PRECISO: usa solo le informazioni fornite nel contesto. Non inventare mai dati, orari, prezzi o contatti.
- CORTESE: usa un tono amichevole e accogliente, come un vicino di casa disponibile.
- CONCISO: rispondi in modo chiaro e diretto. Evita risposte troppo lunghe su WhatsApp.
- IN ITALIANO: rispondi sempre in italiano standard, comprensibile a tutti.

REGOLE IMPORTANTI:
1. Se la risposta e' nelle informazioni fornite, rispondi con sicurezza citando i dettagli.
2. Se la risposta NON e' nelle informazioni fornite, dì chiaramente: "Mi dispiace, non ho questa informazione al momento. Ti consiglio di contattare direttamente la Casa di Quartiere al [numero/email se disponibile]."
3. NON inventare mai orari, numeri di telefono, prezzi o nomi di persone.
4. Se la domanda e' ambigua, chiedi gentilmente un chiarimento.
5. Per le prenotazioni, guida il cittadino passo per passo.
6. Usa emoji con moderazione (1-2 per messaggio al massimo) per rendere il testo più leggibile su WhatsApp.
7. Se salutano, rispondi al saluto e presenta brevemente il servizio.

FORMATO RISPOSTE:
- Usa frasi brevi e paragrafi separati (WhatsApp non supporta HTML/Markdown complesso)
- Per elenchi, usa • o numeri
- Mantieni le risposte sotto i 500 caratteri quando possibile
"""

QUERY_PROMPT_TEMPLATE = """Contesto - Informazioni dalla Casa di Quartiere di Tuturano:
---
{context}
---

Domanda del cittadino: {question}

Rispondi basandoti ESCLUSIVAMENTE sulle informazioni nel contesto sopra. Se il contesto non contiene la risposta, dillo chiaramente."""


class RAGPipeline:
    """Pipeline RAG completa: embedding → retrieval → generation."""

    def __init__(self):
        self._embedding_model: Optional[SentenceTransformer] = None
        self._chroma_client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._initialized = False

    def initialize(self):
        """Inizializza tutti i componenti del pipeline."""
        if self._initialized:
            return

        logger.info("🚀 Inizializzazione pipeline RAG...")

        # 1. Carica modello di embedding
        logger.info(f"📦 Caricamento modello embedding: {settings.embedding_model}")
        self._embedding_model = SentenceTransformer(settings.embedding_model)
        logger.info("✅ Modello embedding caricato")

        # 2. Inizializza ChromaDB
        chroma_path = Path(settings.chroma_persist_dir)
        chroma_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"📦 Inizializzazione ChromaDB in: {chroma_path}")
        self._chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False)
        )

        self._collection = self._chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"description": "Knowledge base Casa di Quartiere Tuturano", "hnsw:space": "cosine"}
        )
        logger.info(f"✅ ChromaDB pronto — {self._collection.count()} documenti in collezione")

        # 3. Verifica connessione Ollama
        try:
            ollama.list()
            logger.info(f"✅ Ollama connesso — modello: {settings.ollama_model}")
        except Exception as e:
            logger.warning(f"⚠️ Ollama non raggiungibile: {e}. Il bot funzionera' solo per il retrieval.")

        self._initialized = True
        logger.info("🎉 Pipeline RAG inizializzato con successo!")

    # --------------------------------------------------------
    # Knowledge Base Management
    # --------------------------------------------------------

    def load_knowledge_base(self, kb_dir: Optional[str] = None):
        """Carica tutti i file JSON dal knowledge base in ChromaDB."""
        kb_path = Path(kb_dir) if kb_dir else settings.kb_path
        if not kb_path.exists():
            logger.warning(f"Directory knowledge base non trovata: {kb_path}")
            return 0

        total_loaded = 0
        json_files = list(kb_path.glob("*.json"))

        if not json_files:
            logger.warning(f"Nessun file JSON trovato in: {kb_path}")
            return 0

        logger.info(f"📂 Trovati {len(json_files)} file nel knowledge base")

        for filepath in json_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                kb_file = KBFile(**data)
                count = self._index_entries(kb_file.entries, kb_file.categoria)
                total_loaded += count
                logger.info(f"  ✅ {filepath.name}: {count} entries caricate")

            except Exception as e:
                logger.error(f"  ❌ Errore caricando {filepath.name}: {e}")

        logger.info(f"📊 Totale entries caricate: {total_loaded}")
        return total_loaded

    def _index_entries(self, entries: List[KBEntry], categoria: Categoria) -> int:
        """Indicizza una lista di entries in ChromaDB."""
        if not entries:
            return 0

        documents = []
        metadatas = []
        ids = []

        for i, entry in enumerate(entries):
            if not entry.attiva:
                continue

            entry_id = entry.id or f"{categoria.value}_{i}"
            doc_text = entry.to_document_text()
            metadata = entry.to_metadata()

            documents.append(doc_text)
            metadatas.append(metadata)
            ids.append(entry_id)

        if not documents:
            return 0

        # Genera embeddings
        embeddings = self._embedding_model.encode(documents).tolist()

        # Upsert in ChromaDB (aggiorna se esiste, inserisce se nuovo)
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        return len(documents)

    def add_entry(self, entry: KBEntry) -> str:
        """Aggiunge una singola entry al knowledge base."""
        entry_id = entry.id or f"{entry.categoria.value}_{int(time.time())}"
        doc_text = entry.to_document_text()
        metadata = entry.to_metadata()

        embedding = self._embedding_model.encode([doc_text]).tolist()

        self._collection.upsert(
            ids=[entry_id],
            documents=[doc_text],
            metadatas=[metadata],
            embeddings=embedding,
        )

        logger.info(f"✅ Entry aggiunta: {entry_id}")
        return entry_id

    def delete_entry(self, entry_id: str) -> bool:
        """Rimuove una entry dal knowledge base."""
        try:
            self._collection.delete(ids=[entry_id])
            logger.info(f"🗑️ Entry rimossa: {entry_id}")
            return True
        except Exception as e:
            logger.error(f"Errore rimuovendo entry {entry_id}: {e}")
            return False

    def get_all_entries(self) -> dict:
        """Restituisce tutte le entries dal knowledge base."""
        result = self._collection.get(include=["documents", "metadatas"])
        return result

    def get_kb_stats(self) -> dict:
        """Statistiche del knowledge base."""
        total = self._collection.count()
        all_data = self._collection.get(include=["metadatas"])

        categories = {}
        for meta in all_data.get("metadatas", []):
            cat = meta.get("categoria", "sconosciuta")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "totale_entries": total,
            "per_categoria": categories,
        }

    # --------------------------------------------------------
    # Retrieval
    # --------------------------------------------------------

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Tuple[str, dict, float]]:
        """
        Cerca i documenti piu' rilevanti per la query.
        Ritorna: lista di (documento, metadata, score)
        """
        k = top_k or settings.rag_top_k

        if self._collection.count() == 0:
            logger.warning("Knowledge base vuoto — nessun risultato")
            return []

        query_embedding = self._embedding_model.encode([query]).tolist()

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=min(k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        retrieved = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB restituisce distanza (piu' bassa = piu' simile)
            similarity = 1.0 - dist  # Converti in similarita'
            if similarity >= settings.rag_similarity_threshold:
                retrieved.append((doc, meta, similarity))

        logger.info(f"🔍 Retrieval: {len(retrieved)} documenti rilevanti per: '{query[:50]}...'")
        return retrieved

    # --------------------------------------------------------
    # Generation
    # --------------------------------------------------------

    def generate_response(self, question: str, context_docs: List[Tuple[str, dict, float]]) -> str:
        """Genera una risposta usando il LLM con il contesto recuperato."""

        if not context_docs:
            return (
                "Mi dispiace, non ho trovato informazioni specifiche su questo argomento. 😊\n\n"
                "Ti consiglio di contattare direttamente la Casa di Quartiere per avere una risposta precisa."
            )

        # Prepara il contesto
        context_parts = []
        for i, (doc, meta, score) in enumerate(context_docs, 1):
            cat = meta.get("categoria", "")
            context_parts.append(f"[Fonte {i} - {cat}]\n{doc}")

        context = "\n\n".join(context_parts)

        prompt = QUERY_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
        )

        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": 500,
                },
            )
            return response["message"]["content"].strip()

        except Exception as e:
            logger.error(f"Errore generazione LLM: {e}")
            return (
                "Mi scuso, al momento ho un problema tecnico nel generare la risposta. 🔧\n\n"
                "Per favore riprova tra qualche minuto oppure contatta direttamente la Casa di Quartiere."
            )

    # --------------------------------------------------------
    # Pipeline Completo
    # --------------------------------------------------------

    def answer(self, question: str) -> dict:
        """
        Pipeline completo: retrieval → generation.
        Ritorna un dizionario con risposta, fonti e metriche.
        """
        start_time = time.time()

        # 1. Retrieval
        docs = self.retrieve(question)

        # 2. Generation
        response = self.generate_response(question, docs)

        elapsed_ms = (time.time() - start_time) * 1000

        # 3. Prepara risultato
        sources = [
            {
                "categoria": meta.get("categoria", ""),
                "domanda_fonte": meta.get("domanda", ""),
                "similarita": round(score, 3),
            }
            for _, meta, score in docs
        ]

        result = {
            "risposta": response,
            "fonti": sources,
            "tempo_risposta_ms": round(elapsed_ms, 1),
            "documenti_trovati": len(docs),
        }

        logger.info(
            f"💬 Risposta generata in {elapsed_ms:.0f}ms "
            f"({len(docs)} documenti usati)"
        )

        return result


# Singleton globale
rag_pipeline = RAGPipeline()
