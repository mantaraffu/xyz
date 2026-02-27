import sqlite3
import shutil
import sys
import time

print("STEP 1: Starting script", flush=True)

try:
    print("STEP 2: Connecting to DB in read-only mode using URI", flush=True)
    # Using the standard uri approach to open in read-only mode
    # This prevents sqlite from blocking if another process is writing
    conn = sqlite3.connect('file:/home/xyz/.gemini/antigravity/scratch/casa_quartiere_bot/chroma_data/chroma.sqlite3?mode=ro', uri=True)
    cursor = conn.cursor()
    
    print("STEP 3: Checking tables", flush=True)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tabelle nel database:", flush=True)
    for table in tables:
        print(f"- {table[0]}", flush=True)

    if ('collections',) in tables:
        print("STEP 4: Reading collections", flush=True)
        cursor.execute("SELECT id, name FROM collections;")
        collections = cursor.fetchall()
        print("\nCollezioni:", flush=True)
        for col in collections:
            print(f"  - [{col[0]}] {col[1]}", flush=True)
            
    if ('embeddings',) in tables:
        print("STEP 5: Reading a few embeddings", flush=True)
        cursor.execute("SELECT collection_id, string_value FROM embeddings LIMIT 3;")
        rows = cursor.fetchall()
        print("\nPrimi 3 embeddings ID/Data (Raw):", flush=True)
        for r in rows:
            rep = str(r)
            print(rep[:200] + ('...' if len(rep) > 200 else ''), flush=True)
            
except Exception as e:
    print(f"Errore durante l'accesso al database: {e}", flush=True)

print("STEP 6: Script completato", flush=True)
