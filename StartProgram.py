import tkinter as tk
from tkinter import ttk, messagebox
from DataBaseManager import DataBaseManager
from BasicUIManager import UIManager
from AIReasoning import AIHandler

class Launcher:
    def __init__(self, root, ai_handler):
        self.root = root
        self.root.title("Ollama Connection Setup")
        self.root.geometry("350x150")
        self.ai_handler = ai_handler

        tk.Label(self.root, text="Connecting to local Ollama server...", font=("Arial", 10, "bold")).pack(pady=(15, 5))
        
        # Fetch models immediately on boot
        self.models = self.ai_handler.get_local_models()

        if not self.models:
            messagebox.showerror(
                "Connection Failed", 
                "Could not detect any Ollama models.\n\nPlease make sure Ollama is running (open the desktop app or type 'ollama serve' in your terminal) and restart this program."
            )
            self.root.destroy()
            return

        tk.Label(self.root, text="Select your AI Model:").pack()
        
        self.model_var = tk.StringVar(value=self.models[0])
        self.dropdown = ttk.Combobox(self.root, textvariable=self.model_var, values=self.models, state="readonly", width=30)
        self.dropdown.pack(pady=5)

        tk.Button(self.root, text="Launch Application", bg="lightgreen", command=self.launch_main).pack(pady=10)

    def launch_main(self):
        selected_model = self.model_var.get()
        self.root.destroy()  # Close the launcher window
        start_main_app(selected_model) # Boot the main app

def start_main_app(selected_model):
    # 1. Initialize the foundational managers
    db_manager = DataBaseManager()
    ai_handler = AIHandler()

    # 2. Setup Tkinter main root
    root = tk.Tk()

    # 3. Define the routing functions
    def handle_submit(context, prompt):
        # Passes the pre-selected model directly to the AI Handler
        ai_handler.process_and_route(selected_model, context, prompt, db_manager, ui)

    def handle_db_refresh():
        records = db_manager.get_all_interactions()
        ui.update_db_view(records)

    # 4. Initialize the UI with the pre-selected model
    ui = UIManager(
        root=root,
        selected_model=selected_model,
        submit_callback=handle_submit,
        refresh_callback=handle_db_refresh
    )

    # 5. Populate initial database view on startup
    handle_db_refresh()

    # 6. Start the program loop
    root.mainloop()

if __name__ == "__main__":
    # Boot the Launcher first
    launch_root = tk.Tk()
    handler = AIHandler()
    app = Launcher(launch_root, handler)
    launch_root.mainloop()