#!/usr/bin/env python
"""Simple SQLite database viewer for the VibezCSM project."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "vibez_csm.sqlite3"

def print_separator(char="=", width=100):
    print(char * width)

def view_database():
    if not DB_PATH.exists():
        print("❌ Database file not found:", DB_PATH)
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get table names
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()
    
    if not tables:
        print("❌ No tables found in database")
        conn.close()
        return
    
    print_separator("=")
    print(f"📊 VibezCSM Database: {DB_PATH.name}")
    print_separator("=")
    
    for table_row in tables:
        table_name = table_row[0]
        
        # Get column info
        columns = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        col_names = [col[1] for col in columns]
        
        # Get row count
        count = cur.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        
        print(f"\n📋 Table: {table_name}")
        print(f"   Columns: {', '.join(col_names)}")
        print(f"   Records: {count}")
        print_separator("-", 100)
        
        # Get all rows
        rows = cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC").fetchall()
        
        if not rows:
            print("   (no records)")
            continue
        
        for idx, row in enumerate(rows, 1):
            print(f"\n   Record #{idx}:")
            for col_name, col_value in zip(col_names, row):
                # Try to parse JSON fields
                display_value = col_value
                if col_value and isinstance(col_value, str) and col_value.startswith('['):
                    try:
                        display_value = json.loads(col_value)
                    except:
                        pass
                elif col_value and isinstance(col_value, str) and col_value.startswith('{'):
                    try:
                        display_value = json.loads(col_value)
                    except:
                        pass
                
                if isinstance(display_value, (dict, list)):
                    print(f"   • {col_name}:")
                    print(f"     {json.dumps(display_value, indent=6, ensure_ascii=False)}")
                else:
                    print(f"   • {col_name}: {display_value}")
    
    conn.close()
    print_separator("=")
    print("✅ End of database view")

if __name__ == "__main__":
    view_database()
