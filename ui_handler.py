#!/usr/bin/env python
"""Interactive GUI for VibezCSM AIHandler with live database viewer."""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Import the process_message function from AIHandler
import sys
sys.path.insert(0, str(Path(__file__).parent))
from AIHandler import process_message, reset_ollama_context

ROOT_DIR = Path(__file__).parent
DB_PATH = ROOT_DIR / "vibez_csm.sqlite3"
CONTEXT_FILE = ROOT_DIR / "ContextWindow"

class AIHandlerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VibezCSM - AI Handler Interactive")
        self.root.geometry("1400x800")
        self.root.configure(bg="#f0f0f0")
        
        self.db_data = []
        self.setup_ui()
        self.refresh_database()
        
    def setup_ui(self):
        """Create the main UI layout."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel: Input
        left_frame = ttk.LabelFrame(main_frame, text="Input Data", padding=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Context Window (read-only)
        ttk.Label(left_frame, text="ContextWindow (Instructions):", font=("Arial", 9, "bold")).pack(anchor="w")
        self.context_text = scrolledtext.ScrolledText(left_frame, height=6, width=50, state=tk.DISABLED)
        self.context_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Incoming Text (editable)
        ttk.Label(left_frame, text="IncomingText (Editable):", font=("Arial", 9, "bold")).pack(anchor="w")
        self.incoming_text = scrolledtext.ScrolledText(left_frame, height=12, width=50)
        self.incoming_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Load initial data
        self.load_context_and_incoming()
        
        # Submit button
        submit_btn = ttk.Button(left_frame, text="Submit to AI Handler", command=self.submit_to_ai)
        submit_btn.pack(fill=tk.X, pady=5)
        
        # Reset button
        reset_btn = ttk.Button(left_frame, text="🔄 Force Reset Ollama Context", command=self.force_reset_ollama)
        reset_btn.pack(fill=tk.X, pady=2)
        
        # Right panel: Output
        right_frame = ttk.LabelFrame(main_frame, text="AI Output & Extraction", padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Output display (read-only)
        self.output_text = scrolledtext.ScrolledText(right_frame, height=30, width=50)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid weights
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Bottom panel: Database view
        db_frame = ttk.LabelFrame(self.root, text="Database Records (Latest First)", padding=10)
        db_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Database display
        self.db_text = scrolledtext.ScrolledText(db_frame, height=10, width=150)
        self.db_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        # Refresh button
        refresh_btn = ttk.Button(db_frame, text="🔄 Refresh DB", command=self.refresh_database)
        refresh_btn.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)
    
    def load_context_and_incoming(self):
        """Load the context from file. IncomingText is editable in the GUI."""
        try:
            context = CONTEXT_FILE.read_text() if CONTEXT_FILE.exists() else "No context file found"
            
            self.context_text.config(state=tk.NORMAL)
            self.context_text.delete(1.0, tk.END)
            self.context_text.insert(1.0, context)
            self.context_text.config(state=tk.DISABLED)
            
            # Clear the incoming text field for fresh input
            self.incoming_text.delete(1.0, tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load context: {e}")
    
    def submit_to_ai(self):
        """Submit the incoming text to the AI handler."""
        incoming_text = self.incoming_text.get(1.0, tk.END).strip()
        
        if not incoming_text:
            messagebox.showwarning("Warning", "Please enter some text in IncomingText")
            return
        
        # Run in background thread
        thread = threading.Thread(target=self._run_handler, args=(incoming_text,), daemon=True)
        thread.start()
    
    def _run_handler(self, incoming_text: str):
        """Process the message with AI in background."""
        try:
            self.status_var.set("⏳ Processing with AI...")
            self.root.update()
            
            # Process the message
            result = process_message(incoming_text)
            
            self.root.after(0, self._display_output, result)
            self.root.after(500, self.refresh_database)
            self.status_var.set("✅ Processing complete")
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to process: {str(e)}"))
            self.status_var.set("❌ Error")
    
    def _display_output(self, result: dict):
        """Display the AI output and extraction."""
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        
        output = "=== AI Extraction Results ===\n"
        
        # Show isolation status
        isolation = result.get('message_isolation', 'Unknown')
        output += f"{isolation}\n\n"
        
        # Display key fields
        output += f"Name: {result.get('name', 'N/A')}\n"
        output += f"Motivation Score: {result.get('motivation_score', 0)} (0-1 scale)\n"
        output += f"Reasoning: {result.get('motivation_reasoning', 'N/A')}\n"
        output += f"Property Address: {result.get('entities', {}).get('property_address', 'N/A')}\n\n"
        
        # Display extracted details
        key_details = result.get('key_details', {})
        if key_details:
            output += "Key Details:\n"
            for key, val in key_details.items():
                output += f"  • {key}: {val}\n"
            output += "\n"
        
        # Display tags
        tags = result.get('tags', [])
        if tags:
            output += f"Tags: {', '.join(tags)}\n\n"
        
        # Database status
        db_status = result.get('db_status', 'unknown')
        output += f"Database Status: {db_status}\n\n"
        
        # Full JSON
        output += "=== Full JSON Output ===\n"
        output += json.dumps(result, indent=2, ensure_ascii=False)
        
        self.output_text.insert(1.0, output)
        self.output_text.config(state=tk.DISABLED)
    
    def force_reset_ollama(self):
        """Force reset Ollama's context explicitly."""
        try:
            self.status_var.set("⏳ Resetting Ollama context...")
            self.root.update()
            
            success = reset_ollama_context()
            
            if success:
                self.status_var.set("✅ Ollama context reset successfully")
                messagebox.showinfo("Success", "Ollama context has been reset.\n\nNext message will use completely fresh context.")
            else:
                self.status_var.set("⚠️  Ollama reset may have failed (Ollama may not be responding)")
                messagebox.showwarning("Warning", "Could not reset Ollama context.\nMake sure Ollama is running.")
        except Exception as e:
            self.status_var.set("❌ Error resetting Ollama")
            messagebox.showerror("Error", f"Failed to reset Ollama: {str(e)}")
    
    def refresh_database(self):
        """Refresh the database view."""
        thread = threading.Thread(target=self._load_database, daemon=True)
        thread.start()
    
    def _load_database(self):
        """Load database records in background."""
        try:
            if not DB_PATH.exists():
                self.root.after(0, lambda: self._display_database_records([]))
                return
            
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            rows = cur.execute(
                "SELECT * FROM ai_structured_output ORDER BY id DESC LIMIT 10"
            ).fetchall()
            
            self.db_data = [dict(row) for row in rows]
            conn.close()
            
            self.root.after(0, self._display_database_records, self.db_data)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Database Error", str(e)))
    
    def _display_database_records(self, records):
        """Display database records in the text widget."""
        self.db_text.config(state=tk.NORMAL)
        self.db_text.delete(1.0, tk.END)
        
        if not records:
            self.db_text.insert(1.0, "No records in database yet.\n")
            self.db_text.config(state=tk.DISABLED)
            return
        
        output = ""
        for idx, record in enumerate(records, 1):
            output += f"\n{'='*150}\n"
            output += f"Record #{idx} (ID: {record.get('id', 'N/A')}) - {record.get('created_at', 'N/A')}\n"
            output += f"{'='*150}\n"
            
            output += f"Name: {record.get('name', '')}\n"
            output += f"Motivation Score: {record.get('motivation_score', 0)}\n"
            output += f"Reasoning: {record.get('motivation_reasoning', '')}\n"
            output += f"Property Address: {record.get('property_address', '')}\n"
            
            # Parse JSON fields
            locations = record.get('locations', '[]')
            if isinstance(locations, str):
                try:
                    locations = json.loads(locations)
                except:
                    locations = []
            output += f"Locations: {', '.join(locations) if locations else 'None'}\n"
            
            key_details = record.get('key_details', '{}')
            if isinstance(key_details, str):
                try:
                    key_details = json.loads(key_details)
                except:
                    key_details = {}
            if key_details:
                output += "Key Details:\n"
                for key, val in key_details.items():
                    output += f"  • {key}: {val}\n"
            
            tags = record.get('tags', '[]')
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except:
                    tags = []
            output += f"Tags: {', '.join(tags) if tags else 'None'}\n"
        
        self.db_text.insert(1.0, output)
        self.db_text.config(state=tk.DISABLED)
        self.status_var.set(f"✅ Database view updated - {len(records)} records")


def main():
    root = tk.Tk()
    app = AIHandlerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
