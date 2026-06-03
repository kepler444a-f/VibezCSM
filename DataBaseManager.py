import sqlite3

class DataBaseManager:
    def __init__(self, db_name="local_ai_memory.db"):
        self.db_name = db_name
        self._initialize_db()

    def _initialize_db(self):
        """Creates the database and table with the specific variables."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    date_submitted TEXT,
                    urgency_intent TEXT,
                    motivation_score TEXT,
                    timeline TEXT,
                    location TEXT,
                    contact_number TEXT,
                    raw_message TEXT
                )
            """)
            conn.commit()

    def save_interaction(self, name, date, urgency_intent, motivation, timeline, location, contact, raw_message):
        """Writes the parsed JSON data into the specific columns."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO leads 
                (name, date_submitted, urgency_intent, motivation_score, timeline, location, contact_number, raw_message) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, date, urgency_intent, motivation, timeline, location, contact, raw_message)
            )
            conn.commit()

    def get_all_interactions(self):
        """Reads the data to display in the UI."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, date_submitted, urgency_intent, motivation_score, timeline, location, contact_number FROM leads ORDER BY id DESC")
            return cursor.fetchall()