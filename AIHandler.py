import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONTEXT_FILE = ROOT / "ContextWindow"
DATABASE_FILE = ROOT / "vibez_csm.sqlite3"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b-base")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


def reset_ollama_context(host: str = OLLAMA_HOST) -> bool:
    """
    Optional: Explicitly reset Ollama's context by sending an empty prompt.
    This ensures any cached conversation state is cleared.
    
    Use this between message batches if you want absolute certainty of isolation.
    """
    try:
        payload = {
            "model": DEFAULT_MODEL,
            "prompt": "",  # Empty prompt to reset
            "stream": False,
        }
        request = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
        return True
    except Exception:
        return False


def normalize_json(raw_text: str, context_text: str = "", incoming_text: str = "") -> dict[str, Any]:
    """Extract a JSON object from Ollama output and sanitize placeholder output."""
    text = raw_text.strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = sanitize_structured_output(parsed, context_text, incoming_text)
            return parsed
    except json.JSONDecodeError:
        pass

    fallback = {
        "name": "",
        "motivation_score": 0.0,
        "motivation_reasoning": text or "No response",
        "entities": {"property_address": "", "locations": [], "organizations": []},
        "tags": [],
        "key_details": {},
        "raw_text_preview": text[:500],
    }
    return sanitize_structured_output(fallback, context_text, incoming_text)


def sanitize_structured_output(output: dict[str, Any], context_text: str, incoming_text: str) -> dict[str, Any]:
    """Ensure all required fields are present and properly formatted."""
    combined_text = "\n\n".join(part for part in (context_text, incoming_text) if part and part.strip())

    name = output.get("name", "") or ""
    
    motivation_score = output.get("motivation_score", 0.0)
    if not isinstance(motivation_score, (int, float)):
        motivation_score = 0.0
    motivation_score = max(0.0, min(1.0, float(motivation_score)))
    
    motivation_reasoning = output.get("motivation_reasoning", "") or "No reasoning provided"
    
    entities = output.get("entities", {})
    if not isinstance(entities, dict):
        entities = {"property_address": "", "locations": [], "organizations": []}
    else:
        entities = {
            "property_address": entities.get("property_address", "") or "",
            "locations": entities.get("locations", []) if isinstance(entities.get("locations"), list) else [],
            "organizations": entities.get("organizations", []) if isinstance(entities.get("organizations"), list) else [],
        }

    tags = output.get("tags", [])
    if not isinstance(tags, list) or not tags:
        tags = ["untagged"]

    key_details = output.get("key_details", {})
    if not isinstance(key_details, dict):
        key_details = {}

    preview = combined_text[:500] if combined_text else "No content available."

    return {
        "name": name,
        "motivation_score": motivation_score,
        "motivation_reasoning": motivation_reasoning,
        "entities": entities,
        "tags": tags,
        "key_details": key_details,
        "raw_text_preview": preview,
    }


def call_ollama(prompt: str, model: str, host: str = OLLAMA_HOST, context_text: str = "", incoming_text: str = "") -> dict[str, Any]:
    """
    Send a FRESH, STATELESS prompt to the local Ollama server.
    Each call is completely independent with no session/memory.
    """
    # Create a fresh payload for this isolated message
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
            "top_k": 40,
            "top_p": 0.9,
            "repeat_penalty": 1.0,
            "num_ctx": 2048,  # Fresh context window for each message
        },
    }

    # Create a fresh HTTP request (no session reuse)
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Connection": "close",  # Force close connection after response
        },
        method="POST",
    )

    try:
        # Fresh connection - no reuse
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
            # The response is completely fresh for this message
            return normalize_json(data.get("response", "{}"), context_text, incoming_text)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Unable to reach Ollama at {host}. Details: {exc}") from exc


def create_database(path: Path) -> sqlite3.Connection:
    """Create or open the SQLite database used to store the structured result."""
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_structured_output (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            motivation_score REAL,
            motivation_reasoning TEXT,
            property_address TEXT,
            locations TEXT,
            organizations TEXT,
            key_details TEXT,
            tags TEXT,
            raw_input_preview TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def save_result(connection: sqlite3.Connection, structured_output: dict[str, Any]) -> None:
    """Store the structured JSON in the SQLite database."""
    entities = structured_output.get("entities", {})
    tags = json.dumps(structured_output.get("tags", []), ensure_ascii=False)
    key_details = json.dumps(structured_output.get("key_details", {}), ensure_ascii=False)
    
    connection.execute(
        """
        INSERT INTO ai_structured_output 
        (name, motivation_score, motivation_reasoning, property_address, locations, organizations, 
         key_details, tags, raw_input_preview)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            structured_output.get("name", ""),
            structured_output.get("motivation_score", 0.0),
            structured_output.get("motivation_reasoning", ""),
            entities.get("property_address", ""),
            json.dumps(entities.get("locations", []), ensure_ascii=False),
            json.dumps(entities.get("organizations", []), ensure_ascii=False),
            key_details,
            tags,
            structured_output.get("raw_text_preview", ""),
        ),
    )
    connection.commit()


def build_prompt(context_text: str, incoming_text: str) -> str:
    """
    Create an isolated prompt for a single message.
    Explicitly instructs AI to ignore any previous context/memory.
    """
    return f"""IMPORTANT: This is a STANDALONE message. Process ONLY this message independently.
Forget any previous messages or context. This is a NEW, ISOLATED analysis.

SYSTEM INSTRUCTION (from ContextWindow):
{context_text}

CURRENT MESSAGE TO ANALYZE (treat as completely independent):
{incoming_text}

Your task: Extract structured data from ONLY the current message above.
Do NOT reference, remember, or use any previous messages.
Do NOT maintain conversation history.

Return ONLY valid JSON (no explanation, no code fence, no markdown):

{{
  "name": "extracted name or empty",
  "motivation_score": 0.0,
  "motivation_reasoning": "brief reason",
  "entities": {{
    "property_address": "address if mentioned",
    "locations": [],
    "organizations": []
  }},
  "key_details": {{}},
  "tags": []
}}

RULES:
- Analyze ONLY the current message
- Score 0-1: 0=low interest, 1=high urgency
- If information missing, use empty values
- Return JSON only
"""


def process_message(incoming_text: str, model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST) -> dict[str, Any]:
    """
    Process a SINGLE, INDEPENDENT message with NO memory or state carryover.
    
    Each call:
    - Reads context fresh from file (no cached context)
    - Creates a new Ollama connection
    - Treats the message as completely isolated
    - Saves to database as a new, independent record
    
    Args:
        incoming_text: The message to process (completely independent of all other messages)
        model: The Ollama model to use
        host: The Ollama host URL
    
    Returns:
        Dictionary with extraction data (completely independent result)
    """
    # ✅ FRESH context read - not cached, not preserved from previous calls
    context_text = CONTEXT_FILE.read_text(encoding="utf-8").strip() if CONTEXT_FILE.exists() else ""
    
    # ✅ ISOLATED prompt - explicitly tells AI to forget previous context
    prompt = build_prompt(context_text, incoming_text)
    
    # ✅ FRESH Ollama connection - no session reuse, complete isolation
    structured_output = call_ollama(prompt, model, host, context_text, incoming_text)
    
    # ✅ NEW database record - completely independent entry with timestamp
    connection = create_database(DATABASE_FILE)
    try:
        save_result(connection, structured_output)
        structured_output["db_status"] = "saved"
        structured_output["message_isolation"] = "✅ Complete - message treated as independent instance"
    except Exception as e:
        structured_output["db_status"] = f"error: {str(e)}"
    finally:
        connection.close()
    
    return structured_output


def main() -> None:
    """Legacy CLI interface - reads from ContextWindow and processes."""
    context_text = CONTEXT_FILE.read_text(encoding="utf-8").strip() if CONTEXT_FILE.exists() else ""
    
    # Read incoming text from stdin or file
    import sys
    print("Enter incoming text (end with Ctrl+D on Unix or Ctrl+Z on Windows):")
    incoming_text = sys.stdin.read().strip()
    
    if not incoming_text:
        print("No input provided. Use process_message() function instead.")
        return
    
    result = process_message(incoming_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
