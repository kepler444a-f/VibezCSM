## Message Isolation Architecture

This document explains how VibezCSM ensures each message is processed completely independently with no memory or state carryover.

### How It Works

#### 1. **Fresh Context Every Time**
```python
# ✅ NOT cached
# ✅ Read fresh from disk on every process_message() call
context_text = CONTEXT_FILE.read_text(encoding="utf-8").strip()
```
- Context is read fresh each time, not cached in memory
- No conversation history accumulates
- Each message sees only the current instructions

#### 2. **Isolated Prompt Engineering**
The prompt explicitly instructs the AI to forget previous context:
```
"IMPORTANT: This is a STANDALONE message. Process ONLY this message independently.
Forget any previous messages or context. This is a NEW, ISOLATED analysis."
```

#### 3. **Fresh Ollama Connection**
```python
# ✅ Fresh HTTP connection for each message
# ✅ Connection closed after response
headers = {
    "Connection": "close"  # Force connection close
}

# ✅ Fresh context window for each call
"num_ctx": 2048  # Clean context window
```
- Each `process_message()` call opens a brand new HTTP connection
- Connection is explicitly closed after the response
- Ollama's context window is fresh for each message
- No session tokens or conversation history preserved

#### 4. **Independent Database Records**
```python
# ✅ Each message creates a NEW database record
# ✅ No merging or updating of previous records
connection.execute(INSERT ...)  # New INSERT, never UPDATE
```
- Every message creates a completely new database entry
- Records are timestamped independently
- Each has its own ID and extraction results

#### 5. **No Global State**
```python
# ❌ NOT used - no global state
# ✅ USED - fresh reading for each call
```
- No module-level variables holding conversation state
- No class instances maintaining history
- Everything is function-based and stateless

---

## Forcing Complete Isolation

### If You Want to Force Ollama to Forget Memory:

**Option 1: Restart Ollama Service**
```powershell
# Stop and restart Ollama to clear ALL memory
Get-Process ollama | Stop-Process -Force
Start-Service ollama  # or run ollama serve
```

**Option 2: Use a Different Model Instance**
```python
# In UI, use --model parameter:
result = process_message(text, model="qwen2.5-coder:1.5b-base")
```

**Option 3: Explicit State Reset (Optional Enhancement)**
Add this function if you want to explicitly clear Ollama state:
```python
def reset_ollama_context(host: str = OLLAMA_HOST) -> bool:
    """
    Optional: Explicitly reset Ollama's context.
    May not be necessary since each message uses fresh connection.
    """
    try:
        request = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps({
                "model": "llama2",  # Any model
                "prompt": "\n\n",  # Empty prompt
                "stream": False
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            pass
        return True
    except:
        return False
```

---

## Architecture Summary

```
User Types Message in UI
    ↓
process_message(incoming_text) called
    ↓
✅ Fresh context read from file (not cached)
✅ Isolated prompt created (tells AI to forget)
✅ Fresh HTTP connection to Ollama (no session)
✅ Ollama processes with fresh context window
✅ Response is isolated to this message
    ↓
✅ New independent database record created
    ↓
Next message: repeat from step 1 with NO memory
```

---

## Verification

Each message processed shows:
```json
{
  "message_isolation": "✅ Complete - message treated as independent instance",
  "db_status": "saved"
}
```

---

## Why This Works

1. **Ollama is stateless for API calls** - Each `/api/generate` call is independent
2. **Fresh connections** - HTTP connection is closed after each response
3. **Context window reset** - Each call gets `num_ctx: 2048` fresh window
4. **Prompt isolation** - AI explicitly told to forget previous context
5. **Database isolation** - Each message = new INSERT, never UPDATE/merge
6. **No Python state** - All functions are pure/stateless

---

## Testing Isolation

To verify messages are truly independent:

1. Submit Message 1: "John Smith owns 123 Main St"
   - Result: name=John Smith, address=123 Main St

2. Submit Message 2: "Jane Doe needs help" (no address)
   - Result: name=Jane Doe, address="" (NOT carrying over 123 Main St)
   - ✅ Proves isolation works

3. Submit Message 3: Same as Message 1 again
   - Result: name=John Smith, address=123 Main St (identical)
   - ✅ Proves repeatability
