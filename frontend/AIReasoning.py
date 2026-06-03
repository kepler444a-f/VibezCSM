import requests
import json
import threading
from datetime import datetime
from tkinter import messagebox 

class AIHandler:
    def __init__(self, host="http://127.0.0.1:11434"):
        self.host = host

    def get_local_models(self):
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=2) # Left this 2s timeout so the app boots fast if Ollama is off
            if response.status_code == 200:
                return [model["name"] for model in response.json().get("models", [])]
        except requests.exceptions.RequestException:
            return []
        return []

    def process_and_route(self, model, context, prompt, db_manager, ui_manager):
        def task():
            system_instructions = (
                "You are an expert real estate data extraction and lead qualification assistant. "
                "Evaluate the user's message and extract the requested details. "
                "CRITICAL: If a detail is missing, you MUST output 'Not provided'.\n\n"
                "SCORING RULES:\n"
                "- Motivation Score: Rate from '1/10' to '10/10'. 10/10 means immediate distress (foreclosure, desperate to sell). 1/10 means just browsing or asking a casual question. If there is no context to gauge motivation, output 'Not provided'."
            )
            
            user_message = f"Additional Context/Rules: {context}\n\nMessage to parse: {prompt}"
            
            json_schema = {
                "type": "object",
                "properties": {
                    "Name": {
                        "type": "string", 
                        "description": "The sender's name."
                    },
                    "Urgency & Intent": {
                        "type": "string", 
                        "description": "Summarize their urgency level and their specific goal (e.g., 'High - Needs to stop foreclosure')."
                    },
                    "Motivation Score": {
                        "type": "string", 
                        "description": "A score from 1/10 to 10/10 based on their distress or eagerness."
                    },
                    "Timeline": {
                        "type": "string", 
                        "description": "When they need to move or close the deal."
                    },
                    "Location": {
                        "type": "string", 
                        "description": "Property address, city, or state."
                    },
                    "Contact Number": {
                        "type": "string", 
                        "description": "Phone number."
                    }
                },
                "required": ["Name", "Urgency & Intent", "Motivation Score", "Timeline", "Location", "Contact Number"]
            }

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_message}
                ],
                "stream": False,
                "format": json_schema
            }

            print("\n" + "="*50)
            print("🚀 DEBUG: SENDING SCHEMA PAYLOAD TO OLLAMA")
            print(f"Target URL : {self.host}/api/chat")
            print(f"Model      : {model}")
            print("-" * 50)
            print("⏳ Waiting for AI response (Timeout removed. It will wait forever if needed)...\n")

            success = False
            error_message = ""

            try:
                # REMOVED timeout=90 from this line
                response = requests.post(f"{self.host}/api/chat", json=payload)
                
                print("\n" + "="*50)
                print(f"📥 DEBUG: RECEIVED HTTP STATUS {response.status_code}")
                print(f"RAW RESPONSE TEXT: \n{response.text}")
                print("="*50 + "\n")

                if response.status_code == 200:
                    ai_response = response.json().get("message", {}).get("content", "{}")
                    
                    try:
                        data = json.loads(ai_response)
                        name = data.get("Name", "Not provided")
                        urgency_intent = data.get("Urgency & Intent", "Not provided")
                        motivation = data.get("Motivation Score", "Not provided")
                        timeline = data.get("Timeline", "Not provided")
                        location = data.get("Location", "Not provided")
                        contact = data.get("Contact Number", "Not provided")
                        success = True
                    except json.JSONDecodeError:
                        name, urgency_intent, motivation, timeline, location, contact = "Error", "Error", "Error", "Error", "Error", "Error"
                        error_message = f"AI sent invalid JSON data: {ai_response}"

                    date_submitted = datetime.now().strftime("%Y-%m-%d %H:%M")
                    db_manager.save_interaction(name, date_submitted, urgency_intent, motivation, timeline, location, contact, prompt)
                else:
                    error_message = f"Ollama returned HTTP Error Status: {response.status_code}\nDetails: {response.text}"
            
            # The Timeout exception block has been entirely removed here
            except requests.exceptions.ConnectionError:
                error_message = f"Could not connect to Ollama at {self.host}.\n\nEnsure 'ollama serve' is running."
                print("❌ ERROR: Connection Refused.")
            except Exception as e:
                error_message = f"An unexpected system error occurred:\n{str(e)}"
                print(f"❌ ERROR: {str(e)}")

            def update_ui_elements():
                if not success and error_message:
                    messagebox.showerror("AI Processing Error", error_message)
                
                records = db_manager.get_all_interactions()
                ui_manager.update_db_view(records)
                ui_manager.reset_submit_button()

            ui_manager.root.after(0, update_ui_elements)

        threading.Thread(target=task, daemon=True).start()