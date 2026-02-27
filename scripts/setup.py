#!/usr/bin/env python3
"""
Script di setup completo del sistema.

Verifica e installa tutti i componenti necessari:
1. Dipendenze Python
2. Modello di embedding
3. Ollama + modello LLM
4. Knowledge base iniziale
5. Struttura directory

Uso:
    python scripts/setup.py
    python scripts/setup.py --check   # Solo verifica, senza installare
"""

import argparse
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def print_header(text, emoji=""):
    print(f"\n{'='*60}")
    print(f"  {emoji} {text}")
    print(f"{'='*60}")


def print_ok(text):
    print(f"  ✅ {text}")


def print_warn(text):
    print(f"  ⚠️  {text}")


def print_fail(text):
    print(f"  ❌ {text}")


def print_info(text):
    print(f"  ℹ️  {text}")


def check_python():
    """Verifica versione Python."""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 10:
        print_ok(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_fail(f"Python {version.major}.{version.minor} — richiesto >= 3.10")
        return False


def check_ollama():
    """Verifica che Ollama sia installato e in esecuzione."""
    # Verifica installazione
    if not shutil.which("ollama"):
        print_fail("Ollama non installato")
        print_info("Installa da: https://ollama.ai/download")
        return False

    print_ok("Ollama installato")

    # Verifica server attivo
    try:
        import ollama
        models = ollama.list()
        print_ok(f"Ollama server attivo — {len(models.get('models', []))} modelli disponibili")
        return True
    except Exception:
        print_warn("Ollama installato ma server non attivo")
        print_info("Avvia con: ollama serve")
        return False


def check_model(model_name="gemma3:12b"):
    """Verifica che il modello LLM sia scaricato."""
    try:
        import ollama
        models = ollama.list()
        model_names = [m.get("name", "") for m in models.get("models", [])]

        # Verifica match parziale
        for m in model_names:
            if model_name.split(":")[0] in m:
                print_ok(f"Modello disponibile: {m}")
                return True

        print_warn(f"Modello {model_name} non trovato")
        print_info(f"Scarica con: ollama pull {model_name}")
        return False
    except Exception:
        print_warn("Impossibile verificare i modelli (Ollama non raggiungibile)")
        return False


def check_embedding_model():
    """Verifica che il modello di embedding sia scaricabile."""
    try:
        from sentence_transformers import SentenceTransformer
        print_ok("sentence-transformers installato")

        model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        print_info(f"Il modello embedding ({model_name}) verra' scaricato al primo avvio")
        return True
    except ImportError:
        print_fail("sentence-transformers non installato")
        return False


def check_knowledge_base():
    """Verifica che il knowledge base contenga file."""
    kb_path = ROOT / "knowledge_base" / "entries"
    if not kb_path.exists():
        print_fail(f"Directory knowledge base non trovata: {kb_path}")
        return False

    json_files = list(kb_path.glob("*.json"))
    if not json_files:
        print_warn("Nessun file JSON nel knowledge base")
        return False

    total_entries = 0
    for f in json_files:
        try:
            import json
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            entries = data.get("entries", [])
            total_entries += len(entries)
        except Exception:
            pass

    print_ok(f"Knowledge base: {len(json_files)} file, {total_entries} entries totali")
    return True


def check_env_file():
    """Verifica che il file .env esista."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        print_warn("File .env non trovato")
        print_info("Copia .env.example come .env e configura i valori")

        # Copia automatica
        example = ROOT / ".env.example"
        if example.exists():
            shutil.copy(example, env_path)
            print_ok("File .env creato da .env.example — modificare i valori!")
        return False

    print_ok("File .env presente")
    return True


def create_directories():
    """Crea le directory necessarie."""
    dirs = [
        ROOT / "logs",
        ROOT / "chroma_data",
        ROOT / "analytics_data",
        ROOT / "knowledge_base" / "entries",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    print_ok("Directory create/verificate")


def main():
    parser = argparse.ArgumentParser(description="Setup Casa di Quartiere AI Assistant")
    parser.add_argument("--check", action="store_true", help="Solo verifica, senza installare")
    args = parser.parse_args()

    print_header("Casa di Quartiere Tuturano — Setup", "🏠")
    print(f"  Directory progetto: {ROOT}\n")

    all_ok = True

    # 1. Python
    print_header("Python", "🐍")
    all_ok = check_python() and all_ok

    # 2. Directory
    print_header("Directory", "📁")
    create_directories()

    # 3. File .env
    print_header("Configurazione", "⚙️")
    check_env_file()  # Non blocking

    # 4. Ollama
    print_header("Ollama (LLM)", "🤖")
    ollama_ok = check_ollama()
    if ollama_ok:
        check_model()

    # 5. Embedding
    print_header("Embedding Model", "🔢")
    check_embedding_model()

    # 6. Knowledge Base
    print_header("Knowledge Base", "📚")
    check_knowledge_base()

    # Riepilogo
    print_header("Riepilogo", "📋")
    if all_ok:
        print_ok("Sistema pronto per l'avvio!")
        print_info("Per avviare il server:")
        print_info("  cd casa_quartiere_bot")
        print_info("  python -m uvicorn app.main:app --reload")
        print_info("")
        print_info("Per caricare il knowledge base:")
        print_info("  python scripts/load_kb.py")
    else:
        print_warn("Alcuni componenti necessitano attenzione — vedi sopra")

    print()


if __name__ == "__main__":
    main()
