import argparse
import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONTEXT_FILE = ROOT / "ContextWindow"
INCOMING_FILE = ROOT / "IncomingText"
DATABASE_FILE = ROOT / "vibez_csm.sqlite3"
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b-base")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


def read_text_file(path: Path) -> str:
    """Read a text file safely and return the contents."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


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
    """Send a prompt to the local Ollama server and return parsed JSON."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
        },
    }

    request = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
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
    """Create a prompt that asks the model for structured JSON output."""
    return f"""Extract data and return ONLY this JSON (no explanation, no markdown):

{{"name": "Elena Rostova", "motivation_score": 0.9, "motivation_reasoning": "high urgency, distressed tone, needs solution in 30-60 days", "entities": {{"property_address": "1984 Sequoia Court", "locations": ["out of state"], "organizations": []}}, "key_details": {{"tenant_status": "non-paying for 2 months", "timeframe": "30-60 days", "condition": "needs cosmetic updates", "willingness": "cash buyer negotiation"}}, "tags": ["property sale", "urgent", "tenant issues"]}}

INSTRUCTION: Read the incoming text and extract similar JSON. Find:
- name: person's name
- motivation_score: 0-1 (0=low, 1=high urgency)  
- property_address: address mentioned
- key_details: important facts

INCOMING TEXT:
{incoming_text}

Return valid JSON only:
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the text inputs, ask Ollama for structured JSON, and store it in SQLite.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name to use (default: %(default)s)")
    parser.add_argument("--host", default=OLLAMA_HOST, help="Ollama base URL (default: %(default)s)")
    args = parser.parse_args()

    model_name = args.model
    host_url = args.host

    context_text = read_text_file(CONTEXT_FILE)
    incoming_text = read_text_file(INCOMING_FILE)

    print(f"Reading inputs from: {CONTEXT_FILE.name} and {INCOMING_FILE.name}")
    print(f"Using Ollama model: {model_name}")

    prompt = build_prompt(context_text, incoming_text)
    structured_output = call_ollama(prompt, model_name, host_url, context_text, incoming_text)

    connection = create_database(DATABASE_FILE)
    try:
        save_result(connection, structured_output)
    finally:
        connection.close()

    print(f"Structured JSON saved to: {DATABASE_FILE}")
    print(json.dumps(structured_output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
