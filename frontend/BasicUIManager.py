import tkinter as tk
from tkinter import ttk, messagebox

class UIManager:
    def __init__(self, root, selected_model, submit_callback, refresh_callback):
        self.root = root
        self.root.title("Real Estate Lead AI Processor")
        self.root.geometry("1200x600") # Made slightly wider for the new columns
        
        self.selected_model = selected_model
        self.submit_callback = submit_callback
        self.refresh_callback = refresh_callback

        self._build_ui()

    def _build_ui(self):
        input_frame = tk.Frame(self.root, padx=10, pady=10, width=400)
        input_frame.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(input_frame, text=f"Active AI Model: {self.selected_model}", fg="green", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 15))

        tk.Label(input_frame, text="1. Additional Context (Optional rules):").pack(anchor=tk.W)
        self.context_text = tk.Text(input_frame, height=4, width=40)
        self.context_text.pack(fill=tk.X, pady=(0, 10))

        tk.Label(input_frame, text="2. Paste Lead Message/Email Here:").pack(anchor=tk.W)
        self.prompt_text = tk.Text(input_frame, height=12, width=40)
        self.prompt_text.pack(fill=tk.X, pady=(0, 10))

        self.submit_btn = tk.Button(input_frame, text="Process Lead", bg="lightblue", command=self.on_submit)
        self.submit_btn.pack(fill=tk.X, pady=(10, 0))

        db_frame = tk.Frame(self.root, padx=10, pady=10)
        db_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(db_frame, text="Extracted Lead Database").pack(anchor=tk.W)
        
        # Updated columns for the new schema
        columns = ("ID", "Name", "Date", "Urgency & Intent", "Motivation (1-10)", "Timeline", "Location", "Contact")
        self.tree = ttk.Treeview(db_frame, columns=columns, show="headings")
        
        widths = [30, 80, 110, 150, 110, 100, 130, 100]
        for col, w in zip(columns, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w)
            
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        tk.Button(db_frame, text="Refresh Database", command=self.refresh_callback).pack(anchor=tk.E)

    def on_submit(self):
        context = self.context_text.get("1.0", tk.END).strip()
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        
        if not prompt:
            messagebox.showwarning("Error", "Message cannot be empty.")
            return

        self.submit_btn.config(state=tk.DISABLED, text="Analyzing...")
        self.submit_callback(context, prompt)

    def reset_submit_button(self):
        self.submit_btn.config(state=tk.NORMAL, text="Process Lead")

    def update_db_view(self, records):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for record in records:
            self.tree.insert("", tk.END, values=record)