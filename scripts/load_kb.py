#!/usr/bin/env python3
"""
Script per caricare/ricaricare il Knowledge Base in ChromaDB.

Uso:
    python scripts/load_kb.py                    # Carica tutti i file
    python scripts/load_kb.py --file spazi.json  # Carica un file specifico
    python scripts/load_kb.py --stats            # Mostra statistiche
    python scripts/load_kb.py --reset            # Svuota e ricarica tutto
"""

import argparse
import json
import sys
from pathlib import Path

# Aggiungi la root del progetto al path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.config import settings
from app.rag import rag_pipeline

console = Console()


def show_stats():
    """Mostra statistiche del knowledge base."""
    stats = rag_pipeline.get_kb_stats()

    console.print(Panel.fit(
        f"[bold cyan]📊 Knowledge Base Statistics[/bold cyan]\n\n"
        f"Totale entries: [bold]{stats['totale_entries']}[/bold]",
        border_style="cyan",
    ))

    if stats['per_categoria']:
        table = Table(title="Entries per Categoria")
        table.add_column("Categoria", style="cyan")
        table.add_column("Entries", justify="right", style="green")

        for cat, count in sorted(stats['per_categoria'].items()):
            table.add_row(cat.replace("_", " ").title(), str(count))

        console.print(table)
    else:
        console.print("[yellow]Il knowledge base e' vuoto.[/yellow]")


def load_all():
    """Carica tutti i file JSON dal knowledge base."""
    console.print("[bold]📂 Caricamento knowledge base completo...[/bold]\n")
    count = rag_pipeline.load_knowledge_base()
    console.print(f"\n[bold green]✅ Caricate {count} entries in totale![/bold green]")
    return count


def load_file(filename: str):
    """Carica un singolo file JSON."""
    filepath = settings.kb_path / filename
    if not filepath.exists():
        console.print(f"[red]❌ File non trovato: {filepath}[/red]")
        return 0

    console.print(f"[bold]📄 Caricamento: {filename}[/bold]")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    from app.models import KBFile
    kb_file = KBFile(**data)
    count = rag_pipeline._index_entries(kb_file.entries, kb_file.categoria)

    console.print(f"[green]✅ Caricate {count} entries da {filename}[/green]")
    return count


def reset_and_reload():
    """Svuota il knowledge base e ricarica tutto."""
    console.print("[bold yellow]⚠️  Reset completo del knowledge base...[/bold yellow]")

    # Elimina la collezione e ricreala
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=str(settings.chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False)
    )

    try:
        client.delete_collection(settings.chroma_collection_name)
        console.print("[yellow]🗑️  Collezione eliminata[/yellow]")
    except Exception:
        pass

    # Reinizializza
    rag_pipeline._initialized = False
    rag_pipeline.initialize()

    count = load_all()
    console.print(f"\n[bold green]🎉 Reset completato! {count} entries caricate.[/bold green]")


def validate_files():
    """Valida tutti i file JSON del knowledge base."""
    kb_path = settings.kb_path
    if not kb_path.exists():
        console.print(f"[red]Directory non trovata: {kb_path}[/red]")
        return

    console.print("[bold]🔍 Validazione file knowledge base...[/bold]\n")

    from app.models import KBFile

    json_files = list(kb_path.glob("*.json"))
    if not json_files:
        console.print("[yellow]Nessun file JSON trovato.[/yellow]")
        return

    total_entries = 0
    errors = 0

    for filepath in sorted(json_files):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            kb_file = KBFile(**data)
            active = sum(1 for e in kb_file.entries if e.attiva)
            total_entries += active
            console.print(f"  [green]✅[/green] {filepath.name}: {active} entries attive")
        except json.JSONDecodeError as e:
            console.print(f"  [red]❌[/red] {filepath.name}: JSON non valido — {e}")
            errors += 1
        except Exception as e:
            console.print(f"  [red]❌[/red] {filepath.name}: {e}")
            errors += 1

    console.print(f"\n📊 Totale: {total_entries} entries valide, {errors} errori")


def main():
    parser = argparse.ArgumentParser(description="Gestione Knowledge Base Casa di Quartiere")
    parser.add_argument("--file", "-f", help="Carica un file specifico (es: spazi.json)")
    parser.add_argument("--stats", "-s", action="store_true", help="Mostra statistiche")
    parser.add_argument("--reset", "-r", action="store_true", help="Svuota e ricarica tutto")
    parser.add_argument("--validate", "-v", action="store_true", help="Valida i file senza caricare")

    args = parser.parse_args()

    # Inizializza il pipeline
    if not args.validate:
        console.print("[dim]Inizializzazione pipeline RAG...[/dim]")
        rag_pipeline.initialize()

    if args.validate:
        validate_files()
    elif args.stats:
        show_stats()
    elif args.reset:
        reset_and_reload()
    elif args.file:
        load_file(args.file)
    else:
        load_all()

    if not args.validate:
        console.print()
        show_stats()


if __name__ == "__main__":
    main()
